"""Erros de leitura com contexto de arquivo e celula."""

from pathlib import Path

from conciliacao.domain.exceptions import ArquivoError, ValidacaoError


class LeituraError(ValidacaoError):
    def __init__(
        self,
        mensagem: str,
        *,
        arquivo: str | Path | None = None,
        aba: str | None = None,
        linha: int | None = None,
        coluna: str | None = None,
        celula: str | None = None,
        cabecalho_esperado: str | None = None,
        valor_recebido: object | None = None,
    ) -> None:
        super().__init__(mensagem)
        self.arquivo = str(arquivo) if arquivo is not None else None
        self.aba = aba
        self.linha = linha
        self.coluna = coluna
        self.celula = celula
        self.cabecalho_esperado = cabecalho_esperado
        self.valor_recebido = valor_recebido


class ArquivoInexistenteError(ArquivoError):
    pass


class ArquivoVazioError(ArquivoError):
    pass


class FormatoNaoSuportadoError(ArquivoError):
    pass


class ArquivoCorrompidoError(ArquivoError):
    pass


class TabelaNaoEncontradaError(LeituraError):
    pass


class CabecalhoNaoEncontradoError(LeituraError):
    pass


class CabecalhoAmbiguoError(LeituraError):
    pass


class LinhaIncompletaError(LeituraError):
    pass


class ValorMonetarioInvalidoError(LeituraError):
    pass


class DataLeituraInvalidaError(LeituraError):
    pass
