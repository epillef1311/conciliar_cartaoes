"""Formatacao textual resumida dos resultados de validacao."""

from decimal import Decimal
from typing import Any

from conciliacao.domain.models import AlertaValidacao
from conciliacao.validators.models import ResultadoValidacao


def formatar_resumo_validacao(*resultados: ResultadoValidacao) -> str:
    blocos = [_formatar_resultado(resultado) for resultado in resultados]
    return "\n\n".join(blocos)


def _formatar_resultado(resultado: ResultadoValidacao) -> str:
    totais = resultado.totais_calculados
    linhas = [
        resultado.operadora.value,
        f"Arquivo valido: {'sim' if resultado.valido else 'nao'}",
        f"Transacoes: {resultado.quantidade_transacoes}",
    ]
    for chave, rotulo in (
        ("total_bruto", "Total bruto"),
        ("total_taxas_originais", "Total taxa original"),
        ("total_taxa", "Total taxa"),
        ("total_liquido", "Total liquido"),
        ("total_recebido_banco", "Total recebido banco"),
    ):
        if chave in totais:
            linhas.append(f"{rotulo}: {_moeda(totais[chave])}")
    linhas.extend(
        [
            f"Avisos: {resultado.quantidade_avisos}",
            f"Erros: {resultado.quantidade_erros}",
        ]
    )
    if totais.get("conferencia_bancaria") == "NAO_REALIZADA":
        linhas.append(
            "Conferência bancária não realizada: recebimentos não informados ou incompletos."
        )
    for erro in resultado.erros:
        linhas.append(f"Erro: {formatar_alerta(erro)}")
    return "\n".join(linhas)


def _moeda(value: Any) -> str:
    if value is None:
        return "não informado"
    if not isinstance(value, Decimal):
        return str(value)
    sinal = "-" if value < 0 else ""
    absolute = abs(value)
    inteiro, centavos = f"{absolute:.2f}".split(".")
    partes = []
    while inteiro:
        partes.append(inteiro[-3:])
        inteiro = inteiro[:-3]
    return f"{sinal}R$ {'.'.join(reversed(partes))},{centavos}"


def formatar_alerta(alerta: AlertaValidacao) -> str:
    partes = [alerta.mensagem]
    for atributo, rotulo in (
        ("arquivo", "Arquivo"),
        ("aba", "Aba"),
        ("linha", "Linha"),
        ("coluna", "Coluna"),
        ("celula", "Célula"),
    ):
        valor = getattr(alerta, atributo, None)
        if valor is not None:
            partes.append(f"{rotulo}: {valor}")
    partes.append(f"Código: {alerta.codigo}")
    return " | ".join(partes)
