"""Valida, em modo somente leitura, o token local produzido pelo Teste 1."""

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"
SANITIZED_RESPONSE_FILE = OUTPUT_DIR / "validate_token_response_sanitized.json"
DEFAULT_TOKEN_FILE = OUTPUT_DIR / "token.txt"

SENSITIVE_KEYS = {
    "token",
    "access_token",
    "accesstoken",
    "jwt",
    "bearertoken",
    "authtoken",
    "refreshtoken",
    "refresh_token",
    "authorization",
    "password",
    "pass",
    "senha",
}
AUTH_ERROR_TERMS = {
    "token invalido",
    "token expirado",
    "sessao expirada",
    "unauthorized",
    "invalid token",
    "expired token",
    "authentication failed",
}


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"A variavel de ambiente obrigatoria {name} nao foi preenchida.")
    return value


def sanitize_data(data: Any) -> Any:
    if isinstance(data, dict):
        return {
            key: "[REMOVIDO]" if key.casefold() in SENSITIVE_KEYS else sanitize_data(value)
            for key, value in data.items()
        }
    if isinstance(data, list):
        return [sanitize_data(item) for item in data]
    return data


def build_auth_header(token: str, header_name: str, scheme: str) -> dict[str, str]:
    value = f"{scheme} {token}".strip()
    return {header_name: value, "Accept": "application/json"}


def read_token(path: Path) -> str:
    if not path.is_file():
        raise RuntimeError(f"Arquivo de token nao encontrado: {path}")
    token = path.read_text(encoding="utf-8").strip()
    if not token:
        raise RuntimeError(f"Arquivo de token esta vazio: {path}")
    return token


def contains_auth_error(data: Any) -> bool:
    serialized = json.dumps(data, ensure_ascii=False).casefold()
    return any(term in serialized for term in AUTH_ERROR_TERMS)


def parse_response(body: bytes, content_type: str) -> Any:
    if "application/json" not in content_type.casefold():
        return {"content_type": content_type, "body_is_json": False}
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"content_type": content_type, "body_is_json": False}


def request_validation(url: str, headers: dict[str, str], timeout: int) -> tuple[int, Any]:
    request = Request(url, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - URL comes from explicit config.
            content_type = response.headers.get_content_type()
            return response.status, parse_response(response.read(), content_type)
    except HTTPError as error:
        return error.code, parse_response(error.read(), error.headers.get_content_type())
    except URLError as error:
        raise RuntimeError("Falha tecnica de conexao ao validar o token.") from error


def write_sanitized_response(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sanitized = json.dumps(sanitize_data(data), ensure_ascii=False, indent=2)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, delete=False
    ) as temporary_file:
        temporary_file.write(sanitized)
        temporary_path = Path(temporary_file.name)
    temporary_path.replace(path)


def classify(status_code: int, response_data: Any) -> int:
    if status_code == 200 and not contains_auth_error(response_data):
        return 0
    if status_code == 401 or (status_code == 403 and contains_auth_error(response_data)):
        return 2
    if contains_auth_error(response_data):
        return 2
    return 1


def main() -> int:
    try:
        from dotenv import load_dotenv

        load_dotenv(BASE_DIR / ".env")
        base_url = require_env("VELO_API_BASE_URL").rstrip("/")
        endpoint = require_env("VELO_VALIDATE_TOKEN_ENDPOINT")
        header_name = os.getenv("VELO_AUTH_HEADER", "Authorization").strip()
        scheme = os.getenv("VELO_AUTH_SCHEME", "Bearer").strip()
        timeout = int(os.getenv("VELO_HTTP_TIMEOUT", "30"))
        token_file = Path(os.getenv("VELO_TOKEN_FILE", str(DEFAULT_TOKEN_FILE)))
        if not token_file.is_absolute():
            token_file = BASE_DIR / token_file
        token = read_token(token_file)
        if timeout <= 0:
            raise RuntimeError("VELO_HTTP_TIMEOUT deve ser maior que zero.")

        url = f"{base_url}{endpoint}"
        started_at = time.perf_counter()
        status_code, response_data = request_validation(
            url, build_auth_header(token, header_name, scheme), timeout
        )
        elapsed = time.perf_counter() - started_at
        write_sanitized_response(SANITIZED_RESPONSE_FILE, response_data)

        result = classify(status_code, response_data)
        print(f"Status HTTP: {status_code}")
        print(f"Endpoint: {url}")
        print(f"Tempo: {elapsed:.2f}s")
        print("Token carregado: sim")
        print(f"Tamanho do token: {len(token)} caracteres")
        token_status = "sim" if result == 0 else "nao" if result == 2 else "indeterminado"
        print(f"Token valido: {token_status}")
        return result
    except (RuntimeError, ValueError) as error:
        print(f"Erro tecnico na validacao: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
