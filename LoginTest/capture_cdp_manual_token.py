"""Captura somente o token de validacao apos login manual em Chrome isolado."""

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"
DEFAULT_CDP_ENDPOINT = "http://127.0.0.1:9222"


def extract_token_from_post_data(post_data: object) -> str | None:
    if not isinstance(post_data, str):
        return None
    try:
        payload: Any = json.loads(post_data)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    token = payload.get("token")
    return token.strip() if isinstance(token, str) and token.strip() else None


def configured_path(name: str, default: Path) -> Path:
    value = os.getenv(name, str(default)).strip()
    path = Path(value)
    return path if path.is_absolute() else BASE_DIR / path


def main() -> int:
    from dotenv import load_dotenv
    from playwright.sync_api import Error, sync_playwright

    load_dotenv(BASE_DIR / ".env")
    endpoint = os.getenv("VELO_CDP_ENDPOINT", DEFAULT_CDP_ENDPOINT).strip()
    validate_endpoint = os.getenv("VELO_SESSION_VALIDATE_ENDPOINT", "/session/validate").strip()
    timeout_seconds = int(os.getenv("VELO_MANUAL_LOGIN_TIMEOUT_SECONDS", "300"))
    token_file = configured_path("VELO_TOKEN_FILE", OUTPUT_DIR / "token.txt")
    token_file.parent.mkdir(parents=True, exist_ok=True)

    captured_event = threading.Event()
    captured_token: dict[str, str | None] = {"value": None}

    def inspect_request(event: dict[str, Any]) -> None:
        request = event.get("request")
        if not isinstance(request, dict):
            return
        request_url = str(request.get("url", ""))
        if request.get("method") != "POST" or validate_endpoint not in request_url:
            return
        token = extract_token_from_post_data(request.get("postData"))
        if token is None:
            return
        captured_token["value"] = token
        captured_event.set()
        print("Requisicao de validacao detectada.")
        print("Token capturado: sim")
        print(f"Tamanho do token: {len(token)} caracteres")

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp(endpoint)
            contexts = browser.contexts
            if not contexts:
                raise RuntimeError("Nenhum contexto Chrome disponivel no endpoint CDP.")
            pages = contexts[0].pages
            if not pages:
                raise RuntimeError("Abra a pagina de login no Chrome antes de iniciar a captura.")
            session = contexts[0].new_cdp_session(pages[0])
            session.send("Network.enable")
            session.on("Network.requestWillBeSent", inspect_request)
            print("Chrome conectado. Realize o login manualmente na janela aberta.")
            deadline = time.monotonic() + timeout_seconds
            while not captured_event.is_set() and time.monotonic() < deadline:
                pages[0].wait_for_timeout(250)
            if not captured_event.is_set():
                print("Timeout: nenhuma requisicao /session/validate com token foi capturada.")
                return 2
            token = captured_token["value"]
            if token is None:
                return 1
            temporary_file = token_file.with_suffix(".tmp")
            temporary_file.write_text(token, encoding="utf-8")
            temporary_file.replace(token_file)
            print("Token salvo localmente.")
            return 0
    except (Error, RuntimeError, ValueError) as error:
        print(f"Falha na captura CDP: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
