"""Validacoes do arquivo Cielo ja lido em modo somente leitura."""

from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from conciliacao.domain.enums import Modalidade, Operadora, SeveridadeAlerta
from conciliacao.domain.models import AlertaValidacao, TransacaoOperadora
from conciliacao.readers.cielo_reader import ler_cielo
from conciliacao.readers.models import ResultadoLeitura
from conciliacao.utils.currency import quantize_money, sum_money
from conciliacao.utils.text import normalize_text
from conciliacao.validators.common_validator import (
    agrupar_quantidade_por_chave,
    agrupar_total_por_chave,
    alerta,
    alerta_de_excecao_leitura,
    alerta_transacao,
    montar_resultado,
    totais_basicos,
    validar_comum,
    valor_original,
)
from conciliacao.validators.models import ResultadoValidacao

TIPOS_CIELO = {
    "venda credito": Modalidade.CREDITO,
    "venda debito": Modalidade.DEBITO,
    "venda pix": Modalidade.PIX,
}
BANDEIRAS_CONHECIDAS = {
    "visa",
    "master",
    "mastercard",
    "elo",
    "amex",
    "american express",
    "hipercard",
    "pix",
}


class CieloValidator:
    def validar(
        self,
        resultado: ResultadoLeitura,
        *,
        data_inicio: date | None = None,
        data_fim: date | None = None,
    ) -> ResultadoValidacao:
        erros, avisos, periodo = validar_comum(
            resultado,
            operadora=Operadora.CIELO,
            data_inicio=data_inicio,
            data_fim=data_fim,
        )
        erros.extend(self._validar_estrutura(resultado))
        for transacao in resultado.transacoes:
            erros.extend(self._validar_transacao(resultado, transacao))
            avisos.extend(self._avisos_transacao(resultado, transacao))
        erros.extend(self._validar_duplicidades_identificador(resultado))
        avisos.extend(self._validar_duplicidades_combinacao(resultado))
        totais = self._totais(resultado)
        erros.extend(self._validar_totalizador(resultado, totais))
        return montar_resultado(
            resultado,
            operadora=Operadora.CIELO,
            erros=erros,
            avisos=avisos,
            totais=totais,
            periodo=periodo,
            metadados={"validacao": "cielo"},
        )

    def _validar_estrutura(self, resultado: ResultadoLeitura) -> list[AlertaValidacao]:
        required = {
            "Data de pagamento": "CIELO_DATA_PAGAMENTO_AUSENTE",
            "Data da venda": "CIELO_DATA_VENDA_AUSENTE",
            "Tipo de lançamento": "CIELO_TIPO_LANCAMENTO_AUSENTE",
            "Forma de pagamento": "CIELO_FORMA_PAGAMENTO_AUSENTE",
            "Valor bruto": "CIELO_VALOR_BRUTO_AUSENTE",
            "Taxa/tarifa": "CIELO_TAXA_AUSENTE",
            "Valor líquido": "CIELO_VALOR_LIQUIDO_AUSENTE",
        }
        headers = set(resultado.cabecalhos_normalizados)
        erros = []
        for header, codigo in required.items():
            if normalize_text(header).comparavel not in headers:
                erros.append(
                    alerta(
                        codigo=codigo,
                        mensagem=f"Campo essencial ausente: {header}.",
                        severidade=SeveridadeAlerta.CRITICO,
                        arquivo=resultado.caminho_arquivo,
                        aba=resultado.nome_aba_ou_tabela,
                    )
                )
        return erros

    def _validar_transacao(
        self, resultado: ResultadoLeitura, transacao: TransacaoOperadora
    ) -> list[AlertaValidacao]:
        erros = []
        tipo = _texto_normalizado(valor_original(transacao, "Tipo de lançamento"))
        forma = _texto_normalizado(valor_original(transacao, "Forma de pagamento"))
        bandeira = _texto_normalizado(transacao.bandeira)
        modalidade_tipo = TIPOS_CIELO.get(tipo)

        if modalidade_tipo is None:
            erros.append(
                alerta_transacao(
                    resultado,
                    transacao,
                    "tipo_lancamento",
                    codigo="CIELO_TIPO_LANCAMENTO_DESCONHECIDO",
                    mensagem="Tipo de lancamento Cielo desconhecido.",
                    severidade=SeveridadeAlerta.ERRO,
                    valor_recebido=valor_original(transacao, "Tipo de lançamento"),
                )
            )
        elif transacao.modalidade is not None and transacao.modalidade is not modalidade_tipo:
            erros.append(
                alerta_transacao(
                    resultado,
                    transacao,
                    "tipo_lancamento",
                    codigo="CIELO_MODALIDADE_INCONSISTENTE",
                    mensagem="Modalidade inferida nao coincide com o tipo de lancamento.",
                    severidade=SeveridadeAlerta.ERRO,
                    valor_recebido=valor_original(transacao, "Tipo de lançamento"),
                )
            )

        erros.extend(self._validar_forma_pagamento(resultado, transacao, modalidade_tipo, forma))
        erros.extend(self._validar_bandeira(resultado, transacao, modalidade_tipo, bandeira))
        erros.extend(self._validar_valores(resultado, transacao))
        return erros

    def _avisos_transacao(
        self, resultado: ResultadoLeitura, transacao: TransacaoOperadora
    ) -> list[AlertaValidacao]:
        avisos = []
        modalidade_tipo = TIPOS_CIELO.get(
            _texto_normalizado(valor_original(transacao, "Tipo de lançamento"))
        )
        bandeira = _texto_normalizado(transacao.bandeira)
        if transacao.taxa_original > Decimal("0.00"):
            avisos.append(
                alerta_transacao(
                    resultado,
                    transacao,
                    "taxa",
                    codigo="CIELO_TAXA_POSITIVA",
                    mensagem="Taxa positiva no arquivo Cielo foge do padrao observado.",
                    severidade=SeveridadeAlerta.AVISO,
                    valor_recebido=transacao.taxa_original,
                )
            )
        if (
            modalidade_tipo in {Modalidade.CREDITO, Modalidade.DEBITO}
            and bandeira
            and bandeira not in BANDEIRAS_CONHECIDAS
        ):
            avisos.append(
                alerta_transacao(
                    resultado,
                    transacao,
                    "bandeira",
                    codigo="CIELO_BANDEIRA_DESCONHECIDA",
                    mensagem="Bandeira de cartao nao reconhecida no catalogo inicial.",
                    severidade=SeveridadeAlerta.AVISO,
                    valor_recebido=transacao.bandeira,
                )
            )
        return avisos

    def _validar_forma_pagamento(
        self,
        resultado: ResultadoLeitura,
        transacao: TransacaoOperadora,
        modalidade: Modalidade | None,
        forma: str,
    ) -> list[AlertaValidacao]:
        if modalidade is None:
            return []
        expected = {
            Modalidade.CREDITO: "credito",
            Modalidade.DEBITO: "debito",
            Modalidade.PIX: "pix",
        }[modalidade]
        if expected not in forma:
            return [
                alerta_transacao(
                    resultado,
                    transacao,
                    "forma_pagamento",
                    codigo="CIELO_FORMA_PAGAMENTO_INCOERENTE",
                    mensagem="Forma de pagamento incoerente com o tipo de lancamento.",
                    severidade=SeveridadeAlerta.ERRO,
                    valor_recebido=valor_original(transacao, "Forma de pagamento"),
                    contexto={"modalidade_esperada": modalidade.value},
                )
            ]
        return []

    def _validar_bandeira(
        self,
        resultado: ResultadoLeitura,
        transacao: TransacaoOperadora,
        modalidade: Modalidade | None,
        bandeira: str,
    ) -> list[AlertaValidacao]:
        if modalidade is Modalidade.PIX and bandeira != "pix":
            return [
                alerta_transacao(
                    resultado,
                    transacao,
                    "bandeira",
                    codigo="CIELO_PIX_BANDEIRA_INVALIDA",
                    mensagem="Venda Pix deve ter bandeira Pix.",
                    severidade=SeveridadeAlerta.ERRO,
                    valor_recebido=transacao.bandeira,
                )
            ]
        if modalidade in {Modalidade.CREDITO, Modalidade.DEBITO} and not bandeira:
            return [
                alerta_transacao(
                    resultado,
                    transacao,
                    "bandeira",
                    codigo="CIELO_CARTAO_SEM_BANDEIRA",
                    mensagem="Venda de cartao deve informar bandeira.",
                    severidade=SeveridadeAlerta.ERRO,
                    valor_recebido=transacao.bandeira,
                )
            ]
        return []

    def _validar_valores(
        self, resultado: ResultadoLeitura, transacao: TransacaoOperadora
    ) -> list[AlertaValidacao]:
        erros = []
        esperado = quantize_money(transacao.valor_bruto - transacao.taxa_normalizada)
        diferenca = quantize_money(esperado - transacao.valor_liquido)
        if diferenca != Decimal("0.00"):
            erros.append(
                alerta_transacao(
                    resultado,
                    transacao,
                    "valor_liquido",
                    codigo="CIELO_INCONSISTENCIA_FINANCEIRA",
                    mensagem="Valor bruto menos taxa normalizada difere do valor liquido.",
                    severidade=SeveridadeAlerta.ERRO,
                    valor_recebido=transacao.valor_liquido,
                    contexto={
                        "celula_valor_bruto": _celula(transacao, "valor_bruto"),
                        "celula_taxa": _celula(transacao, "taxa"),
                        "celula_valor_liquido": _celula(transacao, "valor_liquido"),
                        "valor_bruto": transacao.valor_bruto,
                        "taxa_original": transacao.taxa_original,
                        "taxa_normalizada": transacao.taxa_normalizada,
                        "valor_liquido": transacao.valor_liquido,
                        "diferenca_calculada": diferenca,
                    },
                )
            )
        if transacao.taxa_normalizada > transacao.valor_bruto:
            erros.append(
                alerta_transacao(
                    resultado,
                    transacao,
                    "taxa",
                    codigo="CIELO_TAXA_MAIOR_QUE_BRUTO",
                    mensagem="Taxa normalizada maior que o valor bruto.",
                    severidade=SeveridadeAlerta.ERRO,
                    valor_recebido=transacao.taxa_normalizada,
                )
            )
        return erros

    def _validar_duplicidades_identificador(
        self, resultado: ResultadoLeitura
    ) -> list[AlertaValidacao]:
        erros = []
        for campo in ("codigo_venda", "tid", "nsu_doc"):
            grupos: dict[str, list[TransacaoOperadora]] = {}
            for transacao in resultado.transacoes:
                valor = _identificador_cielo(transacao, campo)
                if valor:
                    grupos.setdefault(valor, []).append(transacao)
            for valor, grupo in grupos.items():
                if len(grupo) > 1 and not _parcelas_distintas_da_mesma_venda(grupo):
                    linhas = [item.linha_original for item in grupo]
                    erros.append(
                        alerta(
                            codigo=f"CIELO_{campo.upper()}_DUPLICADO",
                            mensagem=f"Identificador Cielo repetido: {valor}. Linhas: {linhas}.",
                            severidade=SeveridadeAlerta.ERRO,
                            arquivo=resultado.caminho_arquivo,
                            aba=resultado.nome_aba_ou_tabela,
                            linha=linhas[0],
                            valor_recebido=valor,
                            contexto={"ocorrencias": len(grupo), "linhas": linhas},
                        )
                    )
        return erros

    def _validar_duplicidades_combinacao(
        self, resultado: ResultadoLeitura
    ) -> list[AlertaValidacao]:
        chaves = [
            (
                transacao.data_venda,
                transacao.hora_venda,
                transacao.valor_bruto,
                _texto_normalizado(transacao.bandeira),
                _texto_normalizado(valor_original(transacao, "Tipo de lançamento")),
                _texto_normalizado(valor_original(transacao, "Forma de pagamento")),
            )
            for transacao in resultado.transacoes
            if not transacao.identificador_origem
        ]
        avisos = []
        for chave, count in Counter(chaves).items():
            if count > 1:
                avisos.append(
                    alerta(
                        codigo="CIELO_POSSIVEL_DUPLICIDADE",
                        mensagem="Combinacao completa repetida sem identificador unico.",
                        severidade=SeveridadeAlerta.AVISO,
                        arquivo=resultado.caminho_arquivo,
                        aba=resultado.nome_aba_ou_tabela,
                        contexto={"chave": [str(item) for item in chave], "ocorrencias": count},
                    )
                )
        return avisos

    def _totais(self, resultado: ResultadoLeitura) -> dict[str, Any]:
        totais = totais_basicos(resultado.transacoes)
        totais["quantidade_por_modalidade"] = agrupar_quantidade_por_chave(
            resultado.transacoes, "modalidade"
        )
        totais["totais_por_modalidade"] = agrupar_total_por_chave(
            resultado.transacoes, "modalidade"
        )
        totais["quantidade_por_data_pagamento"] = agrupar_quantidade_por_chave(
            resultado.transacoes, "data_recebimento"
        )
        totais["totais_por_data_pagamento"] = agrupar_total_por_chave(
            resultado.transacoes, "data_recebimento"
        )
        return totais

    def _validar_totalizador(
        self, resultado: ResultadoLeitura, totais: dict[str, Any]
    ) -> list[AlertaValidacao]:
        totalizador = _totalizador_cielo(resultado)
        if not totalizador:
            return []
        erros = []
        comparisons = {
            "valor_bruto": ("total_bruto", "CIELO_TOTALIZADOR_BRUTO_DIVERGENTE"),
            "taxa_tarifa": ("total_taxas_originais", "CIELO_TOTALIZADOR_TAXA_DIVERGENTE"),
            "valor_liquido": ("total_liquido", "CIELO_TOTALIZADOR_LIQUIDO_DIVERGENTE"),
        }
        for key, (total_key, codigo) in comparisons.items():
            origem = totalizador.get(key)
            if origem is None:
                continue
            diferenca = quantize_money(origem - totais[total_key])
            if diferenca != Decimal("0.00"):
                erros.append(
                    alerta(
                        codigo=codigo,
                        mensagem="Totalizador do relatorio Cielo diverge do total calculado.",
                        severidade=SeveridadeAlerta.ERRO,
                        arquivo=resultado.caminho_arquivo,
                        aba=resultado.nome_aba_ou_tabela,
                        valor_recebido=origem,
                        contexto={
                            "totalizador": origem,
                            "calculado": totais[total_key],
                            "diferenca": diferenca,
                        },
                    )
                )
        quantidade = _quantidade_totalizador(totalizador.get("quantidade_lancamentos"))
        if quantidade is not None and quantidade != len(resultado.transacoes):
            erros.append(
                alerta(
                    codigo="CIELO_TOTALIZADOR_QUANTIDADE_DIVERGENTE",
                    mensagem="Quantidade do totalizador diverge das transacoes lidas.",
                    severidade=SeveridadeAlerta.ERRO,
                    arquivo=resultado.caminho_arquivo,
                    aba=resultado.nome_aba_ou_tabela,
                    valor_recebido=quantidade,
                    contexto={"calculado": len(resultado.transacoes)},
                )
            )
        return erros


def validar_cielo_arquivo(
    arquivo: str | Path, *, data_inicio: date | None = None, data_fim: date | None = None
) -> ResultadoValidacao:
    try:
        resultado = ler_cielo(arquivo)
    except Exception as exc:
        return alerta_de_excecao_leitura(exc, arquivo=arquivo, operadora=Operadora.CIELO)
    return CieloValidator().validar(resultado, data_inicio=data_inicio, data_fim=data_fim)


def _texto_normalizado(value: object | None) -> str:
    if value is None:
        return ""
    return normalize_text(str(value)).comparavel


def _celula(transacao: TransacaoOperadora, campo: str) -> str | None:
    from conciliacao.validators.common_validator import celula_por_campo

    return celula_por_campo(transacao, campo)


def _identificador_cielo(transacao: TransacaoOperadora, campo: str) -> str | None:
    campos = (transacao.dados_originais or {}).get("campos_cielo")
    if isinstance(campos, dict) and campos.get(campo):
        return str(campos[campo])
    if campo == "codigo_venda" and transacao.identificador_origem:
        return transacao.identificador_origem
    return None


def _parcelas_distintas_da_mesma_venda(transacoes: list[TransacaoOperadora]) -> bool:
    """Uma venda parcelada pode repetir identificadores, sem repetir a parcela."""
    vendas = {
        (
            _identificador_cielo(item, "codigo_venda"),
            _identificador_cielo(item, "tid"),
            _identificador_cielo(item, "nsu_doc"),
            item.data_venda,
            item.modalidade,
            _texto_normalizado(item.bandeira),
        )
        for item in transacoes
    }
    if len(vendas) != 1 or any(item.modalidade is not Modalidade.CREDITO for item in transacoes):
        return False
    try:
        parcelas = [int(_identificador_cielo(item, "numero_parcela") or "") for item in transacoes]
    except ValueError:
        return False
    return all(numero > 0 for numero in parcelas) and len(set(parcelas)) == len(transacoes)


def _quantidade_totalizador(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except ValueError:
        return None


def _totalizador_cielo(resultado: ResultadoLeitura) -> dict[str, Any] | None:
    for transacao in resultado.transacoes:
        totalizador = (transacao.dados_originais or {}).get("totalizador_cielo")
        if isinstance(totalizador, dict):
            return {
                "quantidade_lancamentos": totalizador.get("quantidade_lancamentos"),
                "valor_bruto": (
                    sum_money([totalizador["valor_bruto"]])
                    if "valor_bruto" in totalizador
                    else None
                ),
                "taxa_tarifa": (
                    sum_money([totalizador["taxa_tarifa"]])
                    if "taxa_tarifa" in totalizador
                    else None
                ),
                "valor_liquido": (
                    sum_money([totalizador["valor_liquido"]])
                    if "valor_liquido" in totalizador
                    else None
                ),
            }
    return None
