"""Processamento QuickPay sem API e sem regras de Excel."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, time
from decimal import Decimal

from conciliacao.domain.enums import Modalidade, Operadora
from conciliacao.domain.models import TransacaoOperadora
from conciliacao.quickpay.recebimentos_bancarios import RecebimentoBancarioQuickPay
from conciliacao.readers.models import ResultadoLeitura
from conciliacao.utils.currency import fee_percentage, quantize_money, sum_money
from conciliacao.utils.dates import validate_period
from conciliacao.utils.text import normalize_text
from conciliacao.validators.common_validator import valor_original
from conciliacao.validators.models import ResultadoValidacao


class QuickPayProcessingError(ValueError):
    """Falha que impede a montagem do relatorio QuickPay."""


@dataclass(frozen=True, slots=True)
class QuickPayLinhaProcessada:
    transacao: TransacaoOperadora
    tipo_pagamento: str
    recebido_banco: Decimal | None
    bruto_liquido: Decimal
    diferenca_taxa: Decimal
    porcentagem: Decimal | None
    diferenca_banco: Decimal | None
    grupo_bancario: str | None = None


@dataclass(frozen=True, slots=True)
class QuickPayGrupoBancario:
    data_recebimento: date
    bandeira: str
    modalidade: Modalidade
    quantidade_transacoes: int
    total_liquido_quickpay: Decimal
    valor_recebido_banco: Decimal
    diferenca_banco: Decimal
    status: str


@dataclass(frozen=True, slots=True)
class QuickPayResumoProcessamento:
    transacoes_lidas: int
    transacoes_incluidas: int
    transacoes_fora_periodo: int
    total_bruto: Decimal
    total_taxa: Decimal
    total_liquido: Decimal
    total_bruto_liquido: Decimal
    total_diferenca_taxa: Decimal
    total_recebido_banco: Decimal | None
    diferenca_total_banco_liquido: Decimal | None
    valor_bruto_zero: int
    conferencia_bancaria: str = "REALIZADA"


@dataclass(frozen=True, slots=True)
class QuickPayRelatorioProcessado:
    arquivo_origem: str
    data_inicio: date
    data_fim: date
    titulo: str
    linhas: tuple[QuickPayLinhaProcessada, ...]
    resumo: QuickPayResumoProcessamento
    hash_origem: str
    grupos_bancarios: tuple[QuickPayGrupoBancario, ...]


class QuickPayProcessor:
    def processar(
        self,
        leitura: ResultadoLeitura,
        validacao: ResultadoValidacao,
        *,
        data_inicio: date,
        data_fim: date,
        recebimentos_bancarios: tuple[RecebimentoBancarioQuickPay, ...] | None = None,
    ) -> QuickPayRelatorioProcessado:
        if leitura.transacoes and leitura.transacoes[0].operadora is not Operadora.QUICKPAY:
            raise QuickPayProcessingError("resultado de leitura nao pertence a QuickPay")
        if validacao.operadora is not Operadora.QUICKPAY:
            raise QuickPayProcessingError("resultado de validacao nao pertence a QuickPay")
        if not validacao.valido:
            raise QuickPayProcessingError("arquivo QuickPay invalido; processamento interrompido")

        inicio, fim = validate_period(data_inicio, data_fim)
        selecionadas = [
            transacao for transacao in leitura.transacoes if inicio <= transacao.data_venda <= fim
        ]
        fora_periodo = len(leitura.transacoes) - len(selecionadas)
        if not selecionadas:
            raise QuickPayProcessingError("nenhuma transacao QuickPay dentro do periodo solicitado")

        grupos = (
            _conciliar_recebimentos_bancarios(selecionadas, recebimentos_bancarios)
            if recebimentos_bancarios is not None
            else ()
        )
        linhas = tuple(
            _montar_linha(transacao, usar_recebimentos_agregados=recebimentos_bancarios is not None)
            for transacao in _ordenar(selecionadas)
        )
        total_recebido = (
            sum_money(grupo.valor_recebido_banco for grupo in grupos)
            if recebimentos_bancarios is not None
            else (
                sum_money(
                    linha.recebido_banco for linha in linhas if linha.recebido_banco is not None
                )
                if all(linha.recebido_banco is not None for linha in linhas)
                else None
            )
        )
        resumo = QuickPayResumoProcessamento(
            transacoes_lidas=len(leitura.transacoes),
            transacoes_incluidas=len(linhas),
            transacoes_fora_periodo=fora_periodo,
            total_bruto=sum_money(linha.transacao.valor_bruto for linha in linhas),
            total_taxa=sum_money(linha.transacao.taxa_original for linha in linhas),
            total_liquido=sum_money(linha.transacao.valor_liquido for linha in linhas),
            total_bruto_liquido=sum_money(linha.bruto_liquido for linha in linhas),
            total_diferenca_taxa=sum_money(linha.diferenca_taxa for linha in linhas),
            total_recebido_banco=total_recebido,
            conferencia_bancaria="REALIZADA" if total_recebido is not None else "NAO_REALIZADA",
            diferenca_total_banco_liquido=quantize_money(
                total_recebido - sum_money(linha.transacao.valor_liquido for linha in linhas)
            )
            if total_recebido is not None
            else None,
            valor_bruto_zero=sum(
                1 for linha in linhas if linha.transacao.valor_bruto == Decimal("0.00")
            ),
        )
        return QuickPayRelatorioProcessado(
            arquivo_origem=str(leitura.caminho_arquivo),
            data_inicio=inicio,
            data_fim=fim,
            titulo=_titulo(linhas),
            linhas=linhas,
            resumo=resumo,
            hash_origem=leitura.hash_sha256,
            grupos_bancarios=grupos,
        )


def _ordenar(transacoes: Iterable[TransacaoOperadora]) -> list[TransacaoOperadora]:
    return sorted(transacoes, key=_chave_ordenacao)


def _chave_ordenacao(transacao: TransacaoOperadora) -> tuple[object, ...]:
    return (
        transacao.data_venda,
        0 if transacao.modalidade is Modalidade.CREDITO else 1,
        normalize_text(transacao.bandeira or "").comparavel,
        transacao.hora_venda or time.min,
        transacao.data_recebimento or date.min,
        normalize_text(str(valor_original(transacao, "Tipo de pagamento") or "")).comparavel,
        transacao.valor_bruto,
    )


def _montar_linha(
    transacao: TransacaoOperadora, *, usar_recebimentos_agregados: bool
) -> QuickPayLinhaProcessada:
    recebido_banco = None if usar_recebimentos_agregados else _recebido_banco(transacao)
    if transacao.taxa_original < Decimal("0.00"):
        raise QuickPayProcessingError(
            f"taxa QuickPay negativa impede exportacao: linha {transacao.linha_original}"
        )
    if transacao.taxa_normalizada > transacao.valor_bruto:
        raise QuickPayProcessingError(
            "taxa QuickPay maior que Valor da Venda impede exportacao: "
            f"linha {transacao.linha_original}"
        )

    bruto_liquido = quantize_money(transacao.valor_bruto - transacao.valor_liquido)
    diferenca_taxa = quantize_money(transacao.taxa_original - bruto_liquido)
    return QuickPayLinhaProcessada(
        transacao=transacao,
        tipo_pagamento=str(valor_original(transacao, "Tipo de pagamento") or ""),
        recebido_banco=recebido_banco,
        bruto_liquido=bruto_liquido,
        diferenca_taxa=diferenca_taxa,
        porcentagem=fee_percentage(transacao.valor_bruto, transacao.valor_liquido),
        diferenca_banco=(
            None
            if recebido_banco is None
            else quantize_money(recebido_banco - transacao.valor_liquido)
        ),
        grupo_bancario=(
            _serializar_chave_bancaria(_chave_bancaria_transacao(transacao))
            if usar_recebimentos_agregados
            else None
        ),
    )


def _recebido_banco(transacao: TransacaoOperadora) -> Decimal | None:
    value = (transacao.dados_originais or {}).get("recebido_no_banco_quickpay_normalizado")
    return value if isinstance(value, Decimal) else None


def _conciliar_recebimentos_bancarios(
    transacoes: list[TransacaoOperadora],
    recebimentos: tuple[RecebimentoBancarioQuickPay, ...],
) -> tuple[QuickPayGrupoBancario, ...]:
    por_chave: dict[tuple[date, str, Modalidade], list[TransacaoOperadora]] = {}
    for transacao in transacoes:
        por_chave.setdefault(_chave_bancaria_transacao(transacao), []).append(transacao)
    banco_por_chave = {item.chave: item for item in recebimentos}
    faltantes = set(por_chave) - set(banco_por_chave)
    extras = set(banco_por_chave) - set(por_chave)
    if faltantes:
        raise QuickPayProcessingError(
            "não há recebimento bancário informado para todos os grupos QuickPay"
        )
    if extras:
        raise QuickPayProcessingError(
            "há recebimento bancário sem grupo de vendas QuickPay correspondente"
        )
    grupos = []
    for key in sorted(por_chave):
        itens = por_chave[key]
        recebido = banco_por_chave[key]
        total_liquido = sum_money(item.valor_liquido for item in itens)
        diferenca = quantize_money(recebido.valor_recebido - total_liquido)
        grupos.append(
            QuickPayGrupoBancario(
                data_recebimento=key[0],
                bandeira=recebido.bandeira,
                modalidade=key[2],
                quantidade_transacoes=len(itens),
                total_liquido_quickpay=total_liquido,
                valor_recebido_banco=recebido.valor_recebido,
                diferenca_banco=diferenca,
                status="CONCILIADO BANCO" if diferenca == Decimal("0.00") else "DIVERGENCIA BANCO",
            )
        )
    return tuple(grupos)


def _chave_bancaria_transacao(transacao: TransacaoOperadora) -> tuple[date, str, Modalidade]:
    if transacao.data_recebimento is None or transacao.modalidade is None or not transacao.bandeira:
        raise QuickPayProcessingError(
            f"transação QuickPay sem chave bancária confiável: linha {transacao.linha_original}"
        )
    return (
        transacao.data_recebimento,
        normalize_text(transacao.bandeira).comparavel,
        transacao.modalidade,
    )


def _serializar_chave_bancaria(chave: tuple[date, str, Modalidade]) -> str:
    return f"{chave[0].isoformat()} | {chave[1]} | {chave[2].value}"


def _titulo(linhas: tuple[QuickPayLinhaProcessada, ...]) -> str:
    datas_venda = sorted({linha.transacao.data_venda for linha in linhas})
    datas_recebimento = sorted(
        {linha.transacao.data_recebimento for linha in linhas if linha.transacao.data_recebimento}
    )
    return (
        "VENDAS QUICKPAY FRIGORIFICO CANDEIAS "
        f"{_periodo_venda(datas_venda)} "
        f"{_periodo_recebimento(datas_recebimento)}"
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
