"""Primitivas compartilhadas pelos validadores de operadoras."""

from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from conciliacao.domain.enums import Operadora, SeveridadeAlerta
from conciliacao.domain.models import AlertaValidacao, TransacaoOperadora
from conciliacao.readers.exceptions import LeituraError
from conciliacao.readers.models import FormatoArquivo, ResultadoLeitura
from conciliacao.utils.currency import quantize_money, sum_money
from conciliacao.utils.dates import validate_period
from conciliacao.utils.text import normalize_text
from conciliacao.validators.models import PeriodoEncontrado, ResultadoValidacao, resultado_invalido

SUPPORTED_BY_OPERATOR = {
    Operadora.CIELO: {FormatoArquivo.XLSX},
    Operadora.QUICKPAY: {FormatoArquivo.XLSX, FormatoArquivo.HTML},
}


class PeriodoSolicitadoInvalido(ValueError):
    """Erro de configuracao do periodo solicitado pelo usuario."""


def alerta(
    *,
    codigo: str,
    mensagem: str,
    severidade: SeveridadeAlerta,
    arquivo: str | Path | None = None,
    aba: str | None = None,
    linha: int | None = None,
    coluna: str | None = None,
    celula: str | None = None,
    valor_recebido: Any | None = None,
    contexto: dict[str, Any] | None = None,
) -> AlertaValidacao:
    return AlertaValidacao(
        codigo=codigo,
        mensagem=mensagem,
        severidade=severidade,
        arquivo=str(arquivo) if arquivo is not None else None,
        aba=aba,
        linha=linha,
        coluna=coluna,
        celula=celula,
        valor_recebido=valor_recebido,
        contexto_adicional=contexto or {},
    )


def alerta_de_excecao_leitura(
    exc: Exception, *, arquivo: str | Path, operadora: Operadora
) -> ResultadoValidacao:
    contexto: dict[str, Any] = {"tipo_excecao": type(exc).__name__}
    severidade = SeveridadeAlerta.CRITICO
    if isinstance(exc, LeituraError):
        contexto.update(
            {
                "cabecalho_esperado": exc.cabecalho_esperado,
                "valor_recebido": exc.valor_recebido,
            }
        )
        arquivo_alerta = exc.arquivo or str(arquivo)
        aba = exc.aba
        linha = exc.linha
        coluna = exc.coluna
        celula = exc.celula
        valor = exc.valor_recebido
        codigo = _codigo_excecao(exc)
    else:
        arquivo_alerta = str(arquivo)
        aba = None
        linha = None
        coluna = None
        celula = None
        valor = None
        codigo = "LEITURA_FALHOU"

    return resultado_invalido(
        arquivo=arquivo,
        operadora=operadora,
        alerta=alerta(
            codigo=codigo,
            mensagem=str(exc),
            severidade=severidade,
            arquivo=arquivo_alerta,
            aba=aba,
            linha=linha,
            coluna=coluna,
            celula=celula,
            valor_recebido=valor,
            contexto=contexto,
        ),
    )


def validar_periodo_solicitado(
    data_inicio: date | None, data_fim: date | None
) -> tuple[date, date] | None:
    if (data_inicio is None) != (data_fim is None):
        raise PeriodoSolicitadoInvalido("dataInicio e dataFim devem ser informadas juntas")
    if data_inicio is None or data_fim is None:
        return None
    try:
        return validate_period(data_inicio, data_fim)
    except Exception as exc:
        raise PeriodoSolicitadoInvalido(str(exc)) from exc


def validar_comum(
    resultado: ResultadoLeitura,
    *,
    operadora: Operadora,
    data_inicio: date | None,
    data_fim: date | None,
) -> tuple[list[AlertaValidacao], list[AlertaValidacao], PeriodoEncontrado]:
    periodo_solicitado = validar_periodo_solicitado(data_inicio, data_fim)
    erros: list[AlertaValidacao] = []
    avisos: list[AlertaValidacao] = list(resultado.avisos_leitura)

    if resultado.formato_detectado not in SUPPORTED_BY_OPERATOR[operadora]:
        erros.append(
            alerta(
                codigo="FORMATO_NAO_SUPORTADO",
                mensagem=f"Formato {resultado.formato_detectado.value} nao suportado.",
                severidade=SeveridadeAlerta.CRITICO,
                arquivo=resultado.caminho_arquivo,
                aba=resultado.nome_aba_ou_tabela,
            )
        )

    if not resultado.nome_aba_ou_tabela:
        erros.append(
            alerta(
                codigo="TABELA_NAO_LOCALIZADA",
                mensagem="Tabela transacional nao localizada.",
                severidade=SeveridadeAlerta.CRITICO,
                arquivo=resultado.caminho_arquivo,
            )
        )
    if not resultado.cabecalhos_normalizados:
        erros.append(
            alerta(
                codigo="CABECALHO_NAO_LOCALIZADO",
                mensagem="Cabecalho transacional nao localizado.",
                severidade=SeveridadeAlerta.CRITICO,
                arquivo=resultado.caminho_arquivo,
                aba=resultado.nome_aba_ou_tabela,
            )
        )
    if not resultado.hash_sha256:
        erros.append(
            alerta(
                codigo="HASH_AUSENTE",
                mensagem="Hash SHA256 do arquivo nao esta disponivel.",
                severidade=SeveridadeAlerta.CRITICO,
                arquivo=resultado.caminho_arquivo,
                aba=resultado.nome_aba_ou_tabela,
            )
        )
    if not resultado.transacoes:
        erros.append(
            alerta(
                codigo="ARQUIVO_SEM_TRANSACOES",
                mensagem="Nenhuma transacao foi localizada no arquivo.",
                severidade=SeveridadeAlerta.CRITICO,
                arquivo=resultado.caminho_arquivo,
                aba=resultado.nome_aba_ou_tabela,
            )
        )

    periodo = periodo_encontrado(resultado.transacoes, periodo_solicitado)
    if periodo_solicitado is not None:
        fora = periodo.quantidade_fora_periodo
        if fora:
            avisos.append(
                alerta(
                    codigo="TRANSACOES_FORA_DO_PERIODO",
                    mensagem=f"{fora} transacao(oes) fora do periodo solicitado.",
                    severidade=SeveridadeAlerta.AVISO,
                    arquivo=resultado.caminho_arquivo,
                    aba=resultado.nome_aba_ou_tabela,
                    contexto={
                        "data_inicio": periodo_solicitado[0],
                        "data_fim": periodo_solicitado[1],
                        "quantidade_dentro_periodo": periodo.quantidade_dentro_periodo,
                        "quantidade_fora_periodo": periodo.quantidade_fora_periodo,
                    },
                )
            )

    for transacao in resultado.transacoes:
        erros.extend(validar_valores_comuns(transacao, resultado))

    return erros, avisos, periodo


def periodo_encontrado(
    transacoes: Sequence[TransacaoOperadora],
    periodo_solicitado: tuple[date, date] | None,
) -> PeriodoEncontrado:
    if not transacoes:
        return PeriodoEncontrado()
    datas = [transacao.data_venda for transacao in transacoes]
    dentro = 0
    fora = 0
    if periodo_solicitado is not None:
        inicio, fim = periodo_solicitado
        for data_venda in datas:
            if inicio <= data_venda <= fim:
                dentro += 1
            else:
                fora += 1
    return PeriodoEncontrado(
        menor_data_venda=min(datas),
        maior_data_venda=max(datas),
        quantidade_dentro_periodo=dentro,
        quantidade_fora_periodo=fora,
    )


def validar_valores_comuns(
    transacao: TransacaoOperadora, resultado: ResultadoLeitura
) -> list[AlertaValidacao]:
    erros: list[AlertaValidacao] = []
    for campo, codigo in (
        ("valor_bruto", "VALOR_BRUTO_NEGATIVO"),
        ("valor_liquido", "VALOR_LIQUIDO_NEGATIVO"),
    ):
        valor = getattr(transacao, campo)
        if valor < Decimal("0.00"):
            erros.append(
                alerta_transacao(
                    resultado,
                    transacao,
                    campo,
                    codigo=codigo,
                    mensagem=f"{campo} nao pode ser negativo.",
                    severidade=SeveridadeAlerta.ERRO,
                    valor_recebido=valor,
                )
            )
        if valor != quantize_money(valor):
            erros.append(
                alerta_transacao(
                    resultado,
                    transacao,
                    campo,
                    codigo=f"{codigo}_CASAS_DECIMAIS",
                    mensagem=f"{campo} deve ter duas casas decimais.",
                    severidade=SeveridadeAlerta.ERRO,
                    valor_recebido=valor,
                )
            )
    if transacao.taxa_normalizada != quantize_money(transacao.taxa_normalizada):
        erros.append(
            alerta_transacao(
                resultado,
                transacao,
                "taxa",
                codigo="TAXA_CASAS_DECIMAIS",
                mensagem="taxa deve ter duas casas decimais.",
                severidade=SeveridadeAlerta.ERRO,
                valor_recebido=transacao.taxa_normalizada,
            )
        )
    return erros


def alerta_transacao(
    resultado: ResultadoLeitura,
    transacao: TransacaoOperadora,
    campo: str,
    *,
    codigo: str,
    mensagem: str,
    severidade: SeveridadeAlerta,
    valor_recebido: Any | None = None,
    contexto: dict[str, Any] | None = None,
) -> AlertaValidacao:
    celula = celula_por_campo(transacao, campo)
    coluna = "".join(char for char in celula if char.isalpha()) if celula else None
    return alerta(
        codigo=codigo,
        mensagem=mensagem,
        severidade=severidade,
        arquivo=resultado.caminho_arquivo,
        aba=resultado.nome_aba_ou_tabela,
        linha=transacao.linha_original,
        coluna=coluna,
        celula=celula,
        valor_recebido=valor_recebido,
        contexto=contexto,
    )


def celula_por_campo(transacao: TransacaoOperadora, campo: str) -> str | None:
    aliases = {
        "data_pagamento": ("data de pagamento", "data do pagamento"),
        "data_recebimento": ("data de recebimento", "data de pagamento", "data do pagamento"),
        "data_venda": ("data da venda",),
        "hora_venda": ("hora da venda",),
        "tipo_lancamento": ("tipo de lancamento",),
        "forma_pagamento": ("forma de pagamento",),
        "tipo_pagamento": ("tipo de pagamento",),
        "bandeira": ("bandeira",),
        "valor_bruto": ("valor bruto", "valor da venda"),
        "valor_liquido": ("valor liquido",),
        "taxa": ("taxa/tarifa", "taxa", "tarifa"),
        "recebido_banco": ("recebido no banco quickpay",),
    }.get(campo, (campo,))
    for header, celula in transacao.celulas_origem.items():
        label = header.rsplit(" (", maxsplit=1)[0]
        if normalize_text(label).comparavel in aliases:
            return celula
    return None


def valor_original(transacao: TransacaoOperadora, *aliases: str) -> Any | None:
    valores = (transacao.dados_originais or {}).get("valores")
    if not isinstance(valores, dict):
        return None
    aliases_norm = {normalize_text(alias).comparavel for alias in aliases}
    for header, value in valores.items():
        label = str(header).rsplit(" (", maxsplit=1)[0]
        if normalize_text(label).comparavel in aliases_norm:
            return value
    return None


def contagem_cabecalho(resultado: ResultadoLeitura, cabecalho: str) -> int:
    esperado = normalize_text(cabecalho).comparavel
    return Counter(resultado.cabecalhos_normalizados)[esperado]


def totais_basicos(transacoes: Iterable[TransacaoOperadora]) -> dict[str, Any]:
    items = list(transacoes)
    return {
        "quantidade_transacoes": len(items),
        "total_bruto": sum_money(transacao.valor_bruto for transacao in items),
        "total_taxas_originais": sum_money(transacao.taxa_original for transacao in items),
        "total_taxas_normalizadas": sum_money(
            transacao.taxa_normalizada for transacao in items
        ),
        "total_liquido": sum_money(transacao.valor_liquido for transacao in items),
    }


def agrupar_quantidade_por_chave(
    transacoes: Iterable[TransacaoOperadora], chave: str
) -> dict[str, int]:
    contador: Counter[str] = Counter()
    for transacao in transacoes:
        valor = getattr(transacao, chave)
        contador[str(valor.value if hasattr(valor, "value") else valor)] += 1
    return dict(contador)


def agrupar_total_por_chave(
    transacoes: Iterable[TransacaoOperadora], chave: str
) -> dict[str, dict[str, Any]]:
    grupos: dict[str, list[TransacaoOperadora]] = defaultdict(list)
    for transacao in transacoes:
        valor = getattr(transacao, chave)
        grupos[str(valor.value if hasattr(valor, "value") else valor)].append(transacao)
    return {
        key: {
            "quantidade": len(items),
            "total_bruto": sum_money(item.valor_bruto for item in items),
            "total_liquido": sum_money(item.valor_liquido for item in items),
            "total_taxa": sum_money(item.taxa_original for item in items),
        }
        for key, items in grupos.items()
    }


def montar_resultado(
    resultado: ResultadoLeitura,
    *,
    operadora: Operadora,
    erros: list[AlertaValidacao],
    avisos: list[AlertaValidacao],
    totais: dict[str, Any],
    periodo: PeriodoEncontrado,
    metadados: dict[str, Any] | None = None,
) -> ResultadoValidacao:
    erros_invalidantes = [
        erro
        for erro in erros
        if erro.severidade in {SeveridadeAlerta.ERRO, SeveridadeAlerta.CRITICO}
    ]
    return ResultadoValidacao(
        arquivo_validado=resultado.caminho_arquivo,
        operadora=operadora,
        valido=not erros_invalidantes,
        quantidade_transacoes=len(resultado.transacoes),
        quantidade_erros=len(erros_invalidantes),
        quantidade_avisos=len(avisos),
        erros=erros_invalidantes,
        avisos=avisos,
        totais_calculados=totais,
        periodo_encontrado=periodo,
        metadados_validacao={
            "hash_sha256": resultado.hash_sha256,
            "formato_detectado": resultado.formato_detectado.value,
            "aba_ou_tabela": resultado.nome_aba_ou_tabela,
            **(metadados or {}),
        },
    )


def _codigo_excecao(exc: LeituraError) -> str:
    name = type(exc).__name__.removesuffix("Error")
    codigo = "".join([f"_{char}" if char.isupper() else char for char in name]).upper().strip("_")
    return f"LEITURA_{codigo}"
