"""Autenticacao Bearer segura para a API Velo."""

import os
from typing import Protocol

from conciliacao.integrations.velo.exceptions import VeloAuthenticationError

VELO_TOKEN_ENV = "VELO_BEARER_TOKEN"


class TokenProvider(Protocol):
    def get_token(self) -> str:
        """Retorna o token apenas para montagem interna do cabecalho."""


class VeloTokenProvider:
    """Busca o token Bearer exclusivamente em variavel de ambiente."""

    def __init__(self, env_var: str = VELO_TOKEN_ENV) -> None:
        self.env_var = env_var

    def get_token(self) -> str:
        value = os.environ.get(self.env_var)
        if value is None or not value.strip():
            raise VeloAuthenticationError(
                "Token Bearer ausente, invalido ou expirado.",
                endpoint="authentication",
            )
        return value.strip()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(env_var={self.env_var!r}, token='<redacted>')"


class StaticTokenProvider:
    """Provider para simulacoes e testes com valor ficticio."""

    def __init__(self, token: str = "simulated-token") -> None:
        self._token = token

    def get_token(self) -> str:
        if not self._token.strip():
            raise VeloAuthenticationError(
                "Token Bearer ausente, invalido ou expirado.",
                endpoint="authentication",
            )
        return self._token

    def __repr__(self) -> str:
        return f"{type(self).__name__}(token='<redacted>')"
