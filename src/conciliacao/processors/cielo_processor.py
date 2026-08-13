"""Processamento Cielo sem API e sem regras de Excel."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from conciliacao.domain.enums import Modalidade, Operadora
from conciliacao.domain.models import TransacaoOperadora
from conciliacao.readers.models import ResultadoLeitura
from conciliacao.utils.currency import fee_percentage, quantize_money, sum_money
from conciliacao.utils.dates import validate_period
from conciliacao.utils.text import normalize_text
from conciliacao.validators.models import ResultadoValidacao


class CieloProcessingError(ValueError):
    """Falha que impede a montagem do relatorio Cielo."""


@dataclass(frozen=True, slots=True)
class CieloBloco:
    tipo: str
    inicio_indice: int
    fim_indice: int
    data_pagamento: date | None
    total_bruto: Decimal
    total_liquido: Decimal


@dataclass(frozen=True, slots=True)
class CieloResumoProcessamento:
    transacoes_lidas: int
    transacoes_incluidas: int
    transacoes_fora_periodo: int
    total_bruto: Decimal
    total_taxa: Decimal
    total_liquido: Decimal
    blocos_cartao: int
    blocos_pix: int
    valor_bruto_zero: int


@dataclass(frozen=True, slots=True)
class CieloRelatorioProcessado:
    arquivo_origem: str
    data_inicio: date
    data_fim: date
    titulo: str
    transacoes: tuple[TransacaoOperadora, ...]
    blocos: tuple[CieloBloco, ...]
    resumo: CieloResumoProcessamento
    hash_origem: str


class CieloProcessor:
    def processar(
        self,
        leitura: ResultadoLeitura,
        validacao: ResultadoValidacao,
        *,
        data_inicio: date,
        data_fim: date,
    ) -> CieloRelatorioProcessado:
        if leitura.transacoes and leitura.transacoes[0].operadora is not Operadora.CIELO:
            raise CieloProcessingError("resultado de leitura nao pertence a Cielo")
        if validacao.operadora is not Operadora.CIELO:
            raise CieloProcessingError("resultado de validacao nao pertence a Cielo")
        if not validacao.valido:
            raise CieloProcessingError("arquivo Cielo invalido; processamento interrompido")

        inicio, fim = validate_period(data_inicio, data_fim)
        selecionadas = [
            transacao for transacao in leitura.transacoes if inicio <= transacao.data_venda <= fim
        ]
        fora_periodo = len(leitura.transacoes) - len(selecionadas)
        if not selecionadas:
            raise CieloProcessingError("nenhuma transacao Cielo dentro do periodo solicitado")

        self._validar_consistencia_financeira(selecionadas)
        ordenadas = tuple(self._ordenar(selecionadas))
        blocos = tuple(self._montar_blocos(ordenadas))
        resumo = CieloResumoProcessamento(
            transacoes_lidas=len(leitura.transacoes),
            transacoes_incluidas=len(ordenadas),
            transacoes_fora_periodo=fora_periodo,
            total_bruto=sum_money(transacao.valor_bruto for transacao in ordenadas),
            total_taxa=sum_money(transacao.taxa_original for transacao in ordenadas),
            total_liquido=sum_money(transacao.valor_liquido for transacao in ordenadas),
            blocos_cartao=sum(1 for bloco in blocos if bloco.tipo == "CARTAO"),
            blocos_pix=sum(1 for bloco in blocos if bloco.tipo == "PIX"),
            valor_bruto_zero=sum(1 for transacao in ordenadas if transacao.valor_bruto == 0),
        )
        return CieloRelatorioProcessado(
            arquivo_origem=str(leitura.caminho_arquivo),
            data_inicio=inicio,
            data_fim=fim,
            titulo=_titulo(ordenadas),
            transacoes=ordenadas,
            blocos=blocos,
            resumo=resumo,
            hash_origem=leitura.hash_sha256,
        )

    def _ordenar(
        self, transacoes: Iterable[TransacaoOperadora]
    ) -> list[TransacaoOperadora]:
        cartoes = [
            transacao for transacao in transacoes if transacao.modalidade is not Modalidade.PIX
        ]
        pix = [transacao for transacao in transacoes if transacao.modalidade is Modalidade.PIX]
        return sorted(cartoes, key=_chave_cartao) + sorted(pix, key=_chave_pix)

    def _montar_blocos(self, transacoes: tuple[TransacaoOperadora, ...]) -> list[CieloBloco]:
        blocos: list[CieloBloco] = []
        card_start: int | None = None
        card_key: tuple[date, Modalidade] | None = None
        pix_start: int | None = None
        for index, transacao in enumerate(transacoes):
            if transacao.modalidade is Modalidade.PIX:
                if card_start is not None:
                    blocos.append(_bloco_cartao(transacoes, card_start, index - 1))
                    card_start = None
                    card_key = None
                if pix_start is None:
                    pix_start = index
                continue

            if pix_start is not None:
                raise CieloProcessingError("cartao encontrado depois do bloco Pix")
            key = (transacao.data_venda, transacao.modalidade)
            if card_start is None:
                card_start = index
                card_key = key
            elif key != card_key:
                blocos.append(_bloco_cartao(transacoes, card_start, index - 1))
                card_start = index
                card_key = key

        if card_start is not None:
            blocos.append(_bloco_cartao(transacoes, card_start, len(transacoes) - 1))
        if pix_start is not None:
            blocos.append(_bloco_pix(transacoes, pix_start, len(transacoes) - 1))
        return blocos

    def _validar_consistencia_financeira(
        self, transacoes: Iterable[TransacaoOperadora]
    ) -> None:
        for transacao in transacoes:
            esperado = quantize_money(transacao.valor_bruto + transacao.taxa_original)
            if esperado != transacao.valor_liquido:
                raise CieloProcessingError(
                    "inconsistencia financeira Cielo impede exportacao: "
                    f"linha {transacao.linha_original}"
                )
            if transacao.valor_bruto != 0:
                fee_percentage(transacao.valor_bruto, transacao.valor_liquido)


def _bloco_cartao(
    transacoes: tuple[TransacaoOperadora, ...],
    inicio: int,
    fim: int,
) -> CieloBloco:
    return CieloBloco(
        tipo="CARTAO",
        inicio_indice=inicio,
        fim_indice=fim,
        data_pagamento=transacoes[inicio].data_recebimento,
        total_bruto=sum_money(transacao.valor_bruto for transacao in transacoes[inicio : fim + 1]),
        total_liquido=sum_money(
            transacao.valor_liquido for transacao in transacoes[inicio : fim + 1]
        ),
    )


def _bloco_pix(
    transacoes: tuple[TransacaoOperadora, ...], inicio: int, fim: int
) -> CieloBloco:
    return CieloBloco(
        tipo="PIX",
        inicio_indice=inicio,
        fim_indice=fim,
        data_pagamento=None,
        total_bruto=sum_money(transacao.valor_bruto for transacao in transacoes[inicio : fim + 1]),
        total_liquido=sum_money(
            transacao.valor_liquido for transacao in transacoes[inicio : fim + 1]
        ),
    )


def _chave_cartao(transacao: TransacaoOperadora) -> tuple[object, ...]:
    return (
        transacao.data_venda,
        0 if transacao.modalidade is Modalidade.CREDITO else 1,
        normalize_text(transacao.bandeira or "").comparavel,
        transacao.hora_venda,
        transacao.data_recebimento or date.min,
    )


def _chave_pix(transacao: TransacaoOperadora) -> tuple[object, ...]:
    return (
        transacao.data_recebimento or date.min,
        transacao.data_venda,
        transacao.hora_venda,
    )


def _titulo(transacoes: tuple[TransacaoOperadora, ...]) -> str:
    datas_venda = sorted({transacao.data_venda for transacao in transacoes})
    datas_pagamento = sorted(
        {transacao.data_recebimento for transacao in transacoes if transacao.data_recebimento}
    )
    return (
        "VENDAS CIELO FRIGORIFICO CANDEIAS "
        f"{_periodo_venda(datas_venda)} "
        f"{_periodo_recebimento(datas_pagamento)}"
    )


def _periodo_venda(datas: list[date]) -> str:
    if len(datas) == 1:
        return f"DIA {_format_date(datas[0])}"
    return "DIA " + _lista_datas(datas)


def _periodo_recebimento(datas: list[date]) -> str:
    if not datas:
        return "RECEBIMENTO NAO INFORMADO"
    if len(datas) == 1:
        return f"RECEBIMENTO {_format_date(datas[0])}"
    return f"RECEBIMENTO {_format_date(datas[0])} A {_format_date(datas[-1])}"


def _lista_datas(datas: list[date]) -> str:
    if len(datas) == 2:
        return f"{_format_date(datas[0])} E {_format_date(datas[1])}"
    return ", ".join(_format_date(data) for data in datas[:-1]) + f" E {_format_date(datas[-1])}"


def _format_date(value: date) -> str:
    return value.strftime("%d/%m/%Y")
