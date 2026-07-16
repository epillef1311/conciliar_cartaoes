"""Excecoes especificas da automacao de conciliacao."""


class ConciliacaoError(Exception):
    """Erro base para falhas previsiveis do dominio."""


class ConfiguracaoError(ConciliacaoError):
    """Configuracao ausente ou invalida."""


class MonetarioError(ConciliacaoError):
    """Valor monetario invalido."""


class DataError(ConciliacaoError):
    """Data ou periodo invalido."""


class ArquivoError(ConciliacaoError):
    """Arquivo indisponivel ou invalido."""


class ValidacaoError(ConciliacaoError):
    """Regra de validacao de negocio nao atendida."""


class IntegracaoError(ConciliacaoError):
    """Falha de comunicacao ou de contrato com integracao externa."""


class AutenticacaoError(IntegracaoError):
    """Credencial ausente, invalida ou expirada."""
