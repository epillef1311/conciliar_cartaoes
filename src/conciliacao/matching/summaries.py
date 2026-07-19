"""Formatacao textual de resultados de matching."""

from decimal import Decimal

from conciliacao.domain.enums import Operadora, StatusConciliacao
from conciliacao.matching.models import ResultadoConciliacaoOperadora


def formatar_resultado_matching(resultado: ResultadoConciliacaoOperadora) -> str:
    resumo = resultado.resumo
    linhas = [
        f"CONCILIACAO {resultado.operadora.value}",
        "",
        f"Transacoes da operadora: {resumo.transacoes_operadora}",
        f"Registros do sistema: {resumo.registros_sistema}",
        "",
        f"Conciliadas: {resumo.conciliados}",
        f"Pendentes por categoria nao consultada: {resumo.pendencias_dados}",
        f"Nao encontradas no sistema: {resumo.nao_encontrados_no_sistema}",
        f"Nao encontradas na operadora: {resumo.nao_encontrados_na_operadora}",
        f"Divergencias de quantidade: {resumo.divergencias_quantidade}",
        f"Divergencias de valor: {resumo.divergencias_valor}",
        f"Ambiguas: {resumo.ambiguidades}",
        "",
        f"Valor bruto da operadora: {_moeda(resumo.total_bruto_operadora)}",
        f"Valor disponivel no sistema: {_moeda(resumo.total_sistema)}",
        f"Valor conciliado: {_moeda(resumo.total_conciliado)}",
        f"Diferenca total: {_moeda(resumo.diferenca_total)}",
    ]
    sistema_sem_correspondencia = [
        item
        for item in resultado.individuais
        if item.status is StatusConciliacao.NAO_ENCONTRADO_NA_OPERADORA
        and item.registro_sistema is not None
    ]
    pendentes = [
        item
        for item in resultado.individuais
        if item.status is StatusConciliacao.PENDENTE_DE_DADOS
        and item.transacao_operadora is not None
    ]
    if sistema_sem_correspondencia:
        linhas.extend(["", "Registros do sistema sem correspondencia:"])
        for item in sistema_sem_correspondencia[:10]:
            registro = item.registro_sistema
            assert registro is not None
            linhas.append(
                "- "
                f"{registro.forma_recebimento}, {registro.data_cadastro:%d/%m/%Y}, "
                f"{_moeda(registro.valor)}"
            )
    if pendentes:
        linhas.extend(["", "Categorias nao consultadas:"])
        for item in pendentes[:10]:
            transacao = item.transacao_operadora
            assert transacao is not None
            linhas.append(
                "- "
                f"{_operadora_label(transacao.operadora)} {transacao.modalidade}, "
                f"{transacao.data_venda:%d/%m/%Y}, {_moeda(transacao.valor_bruto)}"
            )
    return "\n".join(linhas)


def _operadora_label(operadora: Operadora) -> str:
    return "Cielo" if operadora is Operadora.CIELO else "QuickPay"


def _moeda(value: Decimal) -> str:
    sinal = "-" if value < 0 else ""
    absolute = abs(value)
    inteiro, centavos = f"{absolute:.2f}".split(".")
    partes = []
    while inteiro:
        partes.append(inteiro[-3:])
        inteiro = inteiro[:-3]
    return f"{sinal}R$ {'.'.join(reversed(partes))},{centavos}"
