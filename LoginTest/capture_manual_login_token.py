"""Captura o token enviado apos um login Velo feito manualmente pelo usuario."""

import contextlib
import os
import threading
import time
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"


def configured_path(name: str, default: Path) -> Path:
    value = os.getenv(name, str(default)).strip()
    path = Path(value)
    return path if path.is_absolute() else BASE_DIR / path


def extract_token(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    token = payload.get("token")
    if not isinstance(token, str):
        return None
    return token.strip() or None


def main() -> int:
    from dotenv import load_dotenv
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright

    load_dotenv(BASE_DIR / ".env")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    login_url = os.getenv("VELO_LOGIN_URL", "https://app.cicalesesolucoes.com.br/").strip()
    validate_endpoint = os.getenv("VELO_SESSION_VALIDATE_ENDPOINT", "/session/validate").strip()
    timeout_seconds = int(os.getenv("VELO_MANUAL_LOGIN_TIMEOUT_SECONDS", "300"))
    if timeout_seconds <= 0:
        print("Falha no Teste 1B: timeout deve ser maior que zero.")
        return 1

    token_file = configured_path("VELO_TOKEN_FILE", OUTPUT_DIR / "token.txt")
    storage_state_file = configured_path(
        "VELO_STORAGE_STATE_FILE", OUTPUT_DIR / "storage_state.json"
    )
    profile_dir = configured_path("VELO_PROFILE_DIR", OUTPUT_DIR / "chrome_profile")
    trace_file = configured_path("VELO_TRACE_FILE", OUTPUT_DIR / "capture_trace.zip")
    error_screenshot = configured_path("VELO_ERROR_SCREENSHOT", OUTPUT_DIR / "capture_error.png")
    for directory in (token_file.parent, storage_state_file.parent, profile_dir, trace_file.parent):
        directory.mkdir(parents=True, exist_ok=True)

    captured_event = threading.Event()
    captured_token: dict[str, str | None] = {"value": None}
    context = None
    page = None
    trace_started = False

    def inspect_request(request: Any) -> None:
        if request.method != "POST" or validate_endpoint not in request.url:
            return
        try:
            token = extract_token(request.post_data_json)
        except Exception:
            return
        if token is None:
            return
        captured_token["value"] = token
        captured_event.set()
        print("Requisicao de validacao detectada.")
        print("Token capturado: sim")
        print(f"Tamanho do token: {len(token)} caracteres")

    try:
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                channel="chrome",
                headless=False,
                # Remove somente a flag insegura injetada na inicializacao;
                # nao modifica sinais de automacao nem o desafio Turnstile.
                ignore_default_args=["--no-sandbox"],
            )
            context.on("request", inspect_request)
            context.tracing.start(screenshots=True, snapshots=True, sources=False)
            trace_started = True
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(login_url, wait_until="domcontentloaded", timeout=60_000)
            print("Janela aberta.")
            print("Realize o login manualmente.")
            print(f"O script aguardara ate {timeout_seconds} segundos.")

            deadline = time.monotonic() + timeout_seconds
            while not captured_event.is_set() and time.monotonic() < deadline:
                page.wait_for_timeout(250)

            if not captured_event.is_set():
                print("Timeout: nenhuma requisicao /session/validate com token foi capturada.")
                page.screenshot(path=str(error_screenshot), full_page=True)
                return 2

            token = captured_token["value"]
            if token is None:
                print("Falha: evento acionado sem token.")
                return 1
            token_file.write_text(token, encoding="utf-8")
            context.storage_state(path=str(storage_state_file))
            print("Token salvo localmente.")
            print("Estado da sessao salvo localmente.")
            return 0
    except PlaywrightTimeoutError as error:
        print(f"Timeout do Playwright: {error}")
        if page is not None:
            with contextlib.suppress(Exception):
                page.screenshot(path=str(error_screenshot), full_page=True)
        return 1
    except Exception as error:
        print(f"Falha no Teste 1B: {error}")
        if page is not None:
            with contextlib.suppress(Exception):
                page.screenshot(path=str(error_screenshot), full_page=True)
        return 1
    finally:
        if context is not None:
            try:
                if trace_started:
                    context.tracing.stop(path=str(trace_file))
                context.close()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
