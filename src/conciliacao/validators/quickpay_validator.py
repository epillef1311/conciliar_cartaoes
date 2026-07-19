"""Validacoes do arquivo QuickPay ja lido em modo somente leitura."""

from collections import Counter
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from conciliacao.domain.enums import Operadora, SeveridadeAlerta
from conciliacao.domain.models import AlertaValidacao, TransacaoOperadora
from conciliacao.readers.models import ResultadoLeitura
from conciliacao.readers.quickpay_reader import ler_quickpay
from conciliacao.utils.currency import PERCENTUAL_QUANTUM, quantize_money, sum_money
from conciliacao.utils.text import normalize_text
from conciliacao.validators.common_validator import (
    agrupar_quantidade_por_chave,
    agrupar_total_por_chave,
    alerta,
    alerta_de_excecao_leitura,
    alerta_transacao,
    contagem_cabecalho,
    montar_resultado,
    totais_basicos,
    validar_comum,
    valor_original,
)
from conciliacao.validators.models import ResultadoValidacao

BANCO_HEADER = "RECEBIDO NO BANCO QUICKPAY"


class QuickPayValidator:
    def validar(
        self,
        resultado: ResultadoLeitura,
        *,
        data_inicio: date | None = None,
        data_fim: date | None = None,
    ) -> ResultadoValidacao:
        erros, avisos, periodo = validar_comum(
            resultado,
            operadora=Operadora.QUICKPAY,
            data_inicio=data_inicio,
            data_fim=data_fim,
        )
        erros.extend(self._validar_estrutura(resultado))
        for transacao in resultado.transacoes:
            erros.extend(self._validar_recebido_banco(resultado, transacao))
            for alerta_valor in self._validar_valores(resultado, transacao):
                if alerta_valor.severidade in {SeveridadeAlerta.ERRO, SeveridadeAlerta.CRITICO}:
                    erros.append(alerta_valor)
                else:
                    avisos.append(alerta_valor)
            avisos.extend(self._avisos_transacao(resultado, transacao))
        avisos.extend(self._validar_duplicidade(resultado))
        totais = self._totais(resultado)
        return montar_resultado(
            resultado,
            operadora=Operadora.QUICKPAY,
            erros=erros,
            avisos=avisos,
            totais=totais,
            periodo=periodo,
            metadados={"validacao": "quickpay"},
        )

    def _validar_estrutura(self, resultado: ResultadoLeitura) -> list[AlertaValidacao]:
        required = {
            "Data da venda": "QUICKPAY_DATA_VENDA_AUSENTE",
            "Data de recebimento": "QUICKPAY_DATA_RECEBIMENTO_AUSENTE",
            "Número de Parcelas": "QUICKPAY_PARCELAS_AUSENTE",
            "Tipo de pagamento": "QUICKPAY_TIPO_PAGAMENTO_AUSENTE",
            "Valor da Venda": "QUICKPAY_VALOR_VENDA_AUSENTE",
            "Valor líquido": "QUICKPAY_VALOR_LIQUIDO_AUSENTE",
            "Taxa": "QUICKPAY_TAXA_AUSENTE",
            "Bandeira": "QUICKPAY_BANDEIRA_AUSENTE",
        }
        headers = set(resultado.cabecalhos_normalizados)
        erros = []
        for header, codigo in required.items():
            if normalize_text(header).comparavel not in headers:
                erros.append(
                    alerta(
                        codigo=codigo,
                        mensagem=f"Campo obrigatorio ausente: {header}.",
                        severidade=SeveridadeAlerta.CRITICO,
                        arquivo=resultado.caminho_arquivo,
                        aba=resultado.nome_aba_ou_tabela,
                    )
                )

        bank_count = contagem_cabecalho(resultado, BANCO_HEADER)
        if bank_count == 0:
            erros.append(
                alerta(
                    codigo="QUICKPAY_COLUNA_RECEBIDO_AUSENTE",
                    mensagem="Coluna RECEBIDO NO BANCO QUICKPAY ausente na tabela.",
                    severidade=SeveridadeAlerta.CRITICO,
                    arquivo=resultado.caminho_arquivo,
                    aba=resultado.nome_aba_ou_tabela,
                    contexto={"cabecalho_esperado": BANCO_HEADER},
                )
            )
        elif bank_count > 1:
            erros.append(
                alerta(
                    codigo="QUICKPAY_COLUNA_RECEBIDO_DUPLICADA",
                    mensagem="Coluna RECEBIDO NO BANCO QUICKPAY aparece mais de uma vez.",
                    severidade=SeveridadeAlerta.CRITICO,
                    arquivo=resultado.caminho_arquivo,
                    aba=resultado.nome_aba_ou_tabela,
                    contexto={"ocorrencias": bank_count},
                )
            )
        return erros

    def _validar_recebido_banco(
        self, resultado: ResultadoLeitura, transacao: TransacaoOperadora
    ) -> list[AlertaValidacao]:
        banco = _recebido_banco(transacao)
        raw = valor_original(transacao, BANCO_HEADER)
        if banco is None:
            codigo = (
                "QUICKPAY_RECEBIDO_VAZIO"
                if raw in {None, ""}
                else "QUICKPAY_RECEBIDO_INVALIDO"
            )
            return [
                alerta_transacao(
                    resultado,
                    transacao,
                    "recebido_banco",
                    codigo=codigo,
                    mensagem="Valor recebido no banco QuickPay ausente ou invalido.",
                    severidade=SeveridadeAlerta.ERRO,
                    valor_recebido=raw,
                    contexto={"cabecalho": BANCO_HEADER},
                )
            ]
        if banco < Decimal("0.00"):
            return [
                alerta_transacao(
                    resultado,
                    transacao,
                    "recebido_banco",
                    codigo="QUICKPAY_RECEBIDO_NEGATIVO",
                    mensagem="Valor recebido no banco QuickPay nao pode ser negativo.",
                    severidade=SeveridadeAlerta.ERRO,
                    valor_recebido=banco,
                    contexto={"cabecalho": BANCO_HEADER},
                )
            ]
        return []

    def _validar_valores(
        self, resultado: ResultadoLeitura, transacao: TransacaoOperadora
    ) -> list[AlertaValidacao]:
        erros = []
        bruto_liquido = quantize_money(transacao.valor_bruto - transacao.valor_liquido)
        diferenca_taxa = quantize_money(transacao.taxa_normalizada - bruto_liquido)
        if diferenca_taxa != Decimal("0.00"):
            erros.append(
                alerta_transacao(
                    resultado,
                    transacao,
                    "taxa",
                    codigo="QUICKPAY_DIFERENCA_TAXA",
                    mensagem="Taxa difere de Valor da Venda menos Valor liquido.",
                    severidade=SeveridadeAlerta.AVISO,
                    valor_recebido=transacao.taxa_normalizada,
                    contexto={
                        "valor_venda": transacao.valor_bruto,
                        "valor_liquido": transacao.valor_liquido,
                        "bruto_liquido": bruto_liquido,
                        "diferenca_taxa": diferenca_taxa,
                    },
                )
            )
        if transacao.valor_bruto == Decimal("0.00"):
            erros.append(
                alerta_transacao(
                    resultado,
                    transacao,
                    "valor_bruto",
                    codigo="QUICKPAY_VALOR_BRUTO_ZERO",
                    mensagem="Valor da venda zero impede calculo de porcentagem.",
                    severidade=SeveridadeAlerta.AVISO,
                    valor_recebido=transacao.valor_bruto,
                )
            )
        if transacao.taxa_original < Decimal("0.00"):
            erros.append(
                alerta_transacao(
                    resultado,
                    transacao,
                    "taxa",
                    codigo="QUICKPAY_TAXA_NEGATIVA",
                    mensagem="Taxa QuickPay deve ser positiva.",
                    severidade=SeveridadeAlerta.ERRO,
                    valor_recebido=transacao.taxa_original,
                )
            )
        if transacao.taxa_normalizada > transacao.valor_bruto:
            erros.append(
                alerta_transacao(
                    resultado,
                    transacao,
                    "taxa",
                    codigo="QUICKPAY_TAXA_MAIOR_QUE_VALOR_VENDA",
                    mensagem="Taxa maior que Valor da Venda.",
                    severidade=SeveridadeAlerta.ERRO,
                    valor_recebido=transacao.taxa_normalizada,
                )
            )
        return erros

    def _avisos_transacao(
        self, resultado: ResultadoLeitura, transacao: TransacaoOperadora
    ) -> list[AlertaValidacao]:
        avisos = []
        banco = _recebido_banco(transacao)
        if banco is not None:
            diferenca_banco = quantize_money(banco - transacao.valor_liquido)
            if diferenca_banco != Decimal("0.00"):
                avisos.append(
                    alerta_transacao(
                        resultado,
                        transacao,
                        "recebido_banco",
                        codigo="QUICKPAY_DIFERENCA_BANCO",
                        mensagem="Recebido no banco difere do valor liquido QuickPay.",
                        severidade=SeveridadeAlerta.AVISO,
                        valor_recebido=banco,
                        contexto={
                            "valor_liquido": transacao.valor_liquido,
                            "diferenca_banco": diferenca_banco,
                        },
                    )
                )
        return avisos

    def _validar_duplicidade(self, resultado: ResultadoLeitura) -> list[AlertaValidacao]:
        chaves = [
            (
                transacao.data_venda,
                transacao.hora_venda,
                transacao.data_recebimento,
                transacao.valor_bruto,
                _texto_normalizado(transacao.bandeira),
                _texto_normalizado(valor_original(transacao, "Tipo de pagamento")),
                transacao.numero_parcelas,
            )
            for transacao in resultado.transacoes
        ]
        avisos = []
        for chave, count in Counter(chaves).items():
            if count > 1:
                avisos.append(
                    alerta(
                        codigo="QUICKPAY_POSSIVEL_DUPLICIDADE",
                        mensagem="Combinacao transacional QuickPay repetida.",
                        severidade=SeveridadeAlerta.AVISO,
                        arquivo=resultado.caminho_arquivo,
                        aba=resultado.nome_aba_ou_tabela,
                        contexto={"chave": [str(item) for item in chave], "ocorrencias": count},
                    )
                )
        return avisos

    def _totais(self, resultado: ResultadoLeitura) -> dict[str, Any]:
        totais = totais_basicos(resultado.transacoes)
        totais["total_taxa"] = totais["total_taxas_normalizadas"]
        totais["total_bruto_liquido"] = sum_money(
            transacao.valor_bruto - transacao.valor_liquido
            for transacao in resultado.transacoes
        )
        totais["total_diferenca_taxa"] = sum_money(
            transacao.taxa_normalizada
            - quantize_money(transacao.valor_bruto - transacao.valor_liquido)
            for transacao in resultado.transacoes
        )
        recebidos = [_recebido_banco(transacao) for transacao in resultado.transacoes]
        recebidos_validos = [valor for valor in recebidos if valor is not None]
        totais["total_recebido_banco"] = sum_money(recebidos_validos)
        totais["diferenca_total_banco_liquido"] = quantize_money(
            totais["total_recebido_banco"] - totais["total_liquido"]
        )
        totais["quantidade_por_bandeira"] = agrupar_quantidade_por_chave(
            resultado.transacoes, "bandeira"
        )
        totais["quantidade_por_tipo_pagamento"] = _quantidade_por_tipo(resultado)
        totais["totais_por_data_recebimento"] = agrupar_total_por_chave(
            resultado.transacoes, "data_recebimento"
        )
        totais["percentuais"] = [_percentual(transacao) for transacao in resultado.transacoes]
        return totais


def validar_quickpay_arquivo(
    arquivo: str | Path, *, data_inicio: date | None = None, data_fim: date | None = None
) -> ResultadoValidacao:
    try:
        resultado = ler_quickpay(arquivo)
    except Exception as exc:
        return alerta_de_excecao_leitura(exc, arquivo=arquivo, operadora=Operadora.QUICKPAY)
    return QuickPayValidator().validar(resultado, data_inicio=data_inicio, data_fim=data_fim)


def _recebido_banco(transacao: TransacaoOperadora) -> Decimal | None:
    value = (transacao.dados_originais or {}).get("recebido_no_banco_quickpay_normalizado")
    return value if isinstance(value, Decimal) else None


def _texto_normalizado(value: object | None) -> str:
    if value is None:
        return ""
    return normalize_text(str(value)).comparavel


def _quantidade_por_tipo(resultado: ResultadoLeitura) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for transacao in resultado.transacoes:
        tipo = valor_original(transacao, "Tipo de pagamento")
        counter[str(tipo)] += 1
    return dict(counter)


def _percentual(transacao: TransacaoOperadora) -> Decimal | None:
    if transacao.valor_bruto == Decimal("0.00"):
        return None
    return (Decimal("1") - (transacao.valor_liquido / transacao.valor_bruto)).quantize(
        PERCENTUAL_QUANTUM,
        rounding=ROUND_HALF_UP,
    )
