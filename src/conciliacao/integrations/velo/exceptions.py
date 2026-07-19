"""Excecoes seguras da integracao Velo."""

from typing import Any

from conciliacao.domain.exceptions import AutenticacaoError, IntegracaoError

SENSITIVE_MARKERS = ("authorization", "bearer", "token", "cookie")


class VeloApiError(IntegracaoError):
    """Erro base com contexto nao sensivel da API Velo."""

    def __init__(
        self,
        message: str,
        *,
        endpoint: str,
        status_code: int | None = None,
        context: dict[str, Any] | None = None,
        cause: BaseException | None = None,
    ) -> None:
        self.endpoint = endpoint
        self.status_code = status_code
        self.context = _sanitize_context(context or {})
        super().__init__(_safe_message(message))
        if cause is not None:
            self.__cause__ = cause

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(endpoint={self.endpoint!r}, "
            f"status_code={self.status_code!r}, context={self.context!r})"
        )


class VeloBadRequestError(VeloApiError):
    """Parametros invalidos na consulta."""


class VeloAuthenticationError(VeloApiError, AutenticacaoError):
    """Token ausente, invalido ou expirado."""


class VeloAuthorizationError(VeloApiError):
    """Acesso negado pela API."""


class VeloEndpointNotFoundError(VeloApiError):
    """Endpoint configurado nao encontrado."""


class VeloRateLimitError(VeloApiError):
    """Limite de requisicoes atingido."""


class VeloServerError(VeloApiError):
    """Erro 5xx retornado pela API."""


class VeloTimeoutError(VeloApiError):
    """Timeout de comunicacao."""


class VeloConnectionError(VeloApiError):
    """Falha de conexao com a API."""


class VeloInvalidResponseError(VeloApiError):
    """Resposta HTTP nao segue o formato JSON esperado."""


class VeloSchemaError(VeloApiError):
    """Contrato JSON invalido ou incompleto."""


class VeloAuditError(VeloApiError):
    """Falha ao salvar resposta bruta de auditoria."""


def _safe_message(message: str) -> str:
    lowered = message.casefold()
    if any(marker in lowered for marker in SENSITIVE_MARKERS):
        return "Erro seguro da integracao Velo."
    return message


def _sanitize_context(context: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in context.items():
        comparable_key = str(key).casefold()
        if any(marker in comparable_key for marker in SENSITIVE_MARKERS):
            sanitized[key] = "<redacted>"
        else:
            sanitized[key] = value
    return sanitized
