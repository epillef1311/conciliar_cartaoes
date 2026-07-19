"""Processamento QuickPay sem API e sem regras de Excel."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, time
from decimal import Decimal

from conciliacao.domain.enums import Operadora
from conciliacao.domain.models import TransacaoOperadora
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
    recebido_banco: Decimal
    bruto_liquido: Decimal
    diferenca_taxa: Decimal
    porcentagem: Decimal | None
    diferenca_banco: Decimal


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
    total_recebido_banco: Decimal
    diferenca_total_banco_liquido: Decimal
    valor_bruto_zero: int


@dataclass(frozen=True, slots=True)
class QuickPayRelatorioProcessado:
    arquivo_origem: str
    data_inicio: date
    data_fim: date
    titulo: str
    linhas: tuple[QuickPayLinhaProcessada, ...]
    resumo: QuickPayResumoProcessamento
    hash_origem: str


class QuickPayProcessor:
    def processar(
        self,
        leitura: ResultadoLeitura,
        validacao: ResultadoValidacao,
        *,
        data_inicio: date,
        data_fim: date,
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

        linhas = tuple(_montar_linha(transacao) for transacao in _ordenar(selecionadas))
        resumo = QuickPayResumoProcessamento(
            transacoes_lidas=len(leitura.transacoes),
            transacoes_incluidas=len(linhas),
            transacoes_fora_periodo=fora_periodo,
            total_bruto=sum_money(linha.transacao.valor_bruto for linha in linhas),
            total_taxa=sum_money(linha.transacao.taxa_original for linha in linhas),
            total_liquido=sum_money(linha.transacao.valor_liquido for linha in linhas),
            total_bruto_liquido=sum_money(linha.bruto_liquido for linha in linhas),
            total_diferenca_taxa=sum_money(linha.diferenca_taxa for linha in linhas),
            total_recebido_banco=sum_money(linha.recebido_banco for linha in linhas),
            diferenca_total_banco_liquido=quantize_money(
                sum_money(linha.recebido_banco for linha in linhas)
                - sum_money(linha.transacao.valor_liquido for linha in linhas)
            ),
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
        )


def _ordenar(transacoes: Iterable[TransacaoOperadora]) -> list[TransacaoOperadora]:
    return sorted(transacoes, key=_chave_ordenacao)


def _chave_ordenacao(transacao: TransacaoOperadora) -> tuple[object, ...]:
    return (
        transacao.data_recebimento or date.min,
        transacao.data_venda,
        transacao.hora_venda or time.min,
        normalize_text(str(valor_original(transacao, "Tipo de pagamento") or "")).comparavel,
        normalize_text(transacao.bandeira or "").comparavel,
        transacao.valor_bruto,
    )


def _montar_linha(transacao: TransacaoOperadora) -> QuickPayLinhaProcessada:
    recebido_banco = _recebido_banco(transacao)
    if recebido_banco is None:
        raise QuickPayProcessingError(
            "transacao QuickPay sem RECEBIDO NO BANCO QUICKPAY valido: "
            f"linha {transacao.linha_original}"
        )
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
        diferenca_banco=quantize_money(recebido_banco - transacao.valor_liquido),
    )


def _recebido_banco(transacao: TransacaoOperadora) -> Decimal | None:
    value = (transacao.dados_originais or {}).get("recebido_no_banco_quickpay_normalizado")
    return value if isinstance(value, Decimal) else None


def _titulo(linhas: tuple[QuickPayLinhaProcessada, ...]) -> str:
    datas_venda = sorted({linha.transacao.data_venda for linha in linhas})
    datas_recebimento = sorted(
        {
            linha.transacao.data_recebimento
            for linha in linhas
            if linha.transacao.data_recebimento
        }
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
