"""Login manual visivel e captura efemera do token de sessao Velo."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from conciliacao.integrations.velo.exceptions import VeloAuthenticationError


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


class ManualLoginTokenProvider:
    """Abre Chrome visivel e conserva o token somente durante o processo."""

    def __init__(self, capture: Callable[[], str] | None = None) -> None:
        self._capture = capture or capture_token_from_visible_chrome
        self._token: str | None = None

    def get_token(self) -> str:
        if self._token is None:
            token = self._capture().strip()
            if not token:
                raise VeloAuthenticationError(
                    "Login concluido sem token de sessao valido.",
                    endpoint="authentication",
                )
            self._token = token
        return self._token

    def clear(self) -> None:
        self._token = None

    def __repr__(self) -> str:
        return f"{type(self).__name__}(token='<redacted>')"


def capture_token_from_visible_chrome() -> str:
    """Aguarda o usuario concluir o login e captura somente POST /session/validate."""
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright

    login_url = os.getenv("VELO_LOGIN_URL", "https://app.cicalesesolucoes.com.br/").strip()
    validate_path = os.getenv("VELO_SESSION_VALIDATE_ENDPOINT", "/session/validate").strip()
    timeout_seconds = int(os.getenv("VELO_MANUAL_LOGIN_TIMEOUT_SECONDS", "300"))
    configured_port = os.getenv("VELO_CDP_PORT", "").strip()
    port = int(configured_port) if configured_port else _free_local_port()
    profile_dir = Path(
        os.getenv("VELO_CHROME_PROFILE_DIR", "data/local/velo_chrome_profile")
    ).resolve()
    profile_dir.mkdir(parents=True, exist_ok=True)
    chrome_path = _chrome_path()
    subprocess.Popen(  # noqa: S603
        _chrome_launch_command(chrome_path, port, profile_dir),
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )
    endpoint = f"http://127.0.0.1:{port}"
    print("Chrome aberto. Conclua o login para continuar.", flush=True)

    try:
        with sync_playwright() as playwright:
            browser = _connect_cdp(playwright, endpoint, timeout_seconds)
            contexts = browser.contexts
            if not contexts or not contexts[0].pages:
                raise RuntimeError("Nenhuma pagina de login disponivel no Chrome.")
            page = contexts[0].pages[-1]
            session = contexts[0].new_cdp_session(page)
            captured: dict[str, str | None] = {"token": None}

            def inspect_request(event: dict[str, Any]) -> None:
                request = event.get("request")
                if not isinstance(request, dict) or request.get("method") != "POST":
                    return
                if urlparse(str(request.get("url", ""))).path != validate_path:
                    return
                captured["token"] = extract_token_from_post_data(request.get("postData"))

            try:
                session.send("Network.enable")
                session.on("Network.requestWillBeSent", inspect_request)
                page.goto(login_url, wait_until="commit", timeout=30_000)
                deadline = time.monotonic() + timeout_seconds
                while captured["token"] is None and time.monotonic() < deadline:
                    page.wait_for_timeout(250)
                token = captured["token"]
            finally:
                try:
                    session.detach()
                finally:
                    _close_login_page(page)
            if token is None:
                raise VeloAuthenticationError(
                    "Tempo para login manual excedido.", endpoint="authentication"
                )
            print("Login concluido. Iniciando conciliacao.", flush=True)
            return token
    except (PlaywrightError, RuntimeError, ValueError) as exc:
        raise VeloAuthenticationError(
            "Nao foi possivel concluir o login assistido.",
            endpoint="authentication",
            cause=exc,
        ) from exc


def _connect_cdp(playwright: Any, endpoint: str, timeout_seconds: int) -> Any:
    deadline = time.monotonic() + min(timeout_seconds, 30)
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            return playwright.chromium.connect_over_cdp(endpoint, timeout=2_000)
        except Exception as exc:  # Playwright usa excecao propria carregada sob demanda.
            last_error = exc
            time.sleep(0.25)
    raise RuntimeError("Chrome nao disponibilizou a conexao local.") from last_error


def _chrome_path() -> Path:
    configured = os.getenv("VELO_CHROME_PATH", "").strip()
    candidates = [
        Path(configured) if configured else None,
        Path(os.environ.get("PROGRAMFILES", "")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
    ]
    for candidate in candidates:
        if candidate is not None and candidate.is_file():
            return candidate
    raise VeloAuthenticationError(
        "Google Chrome nao foi localizado.", endpoint="authentication"
    )


def _chrome_launch_command(chrome_path: Path, port: int, profile_dir: Path) -> list[str]:
    """Abre uma aba neutra para o observador CDP ser conectado antes do login."""
    return [
        str(chrome_path),
        "--remote-debugging-address=127.0.0.1",
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile_dir}",
        "--new-window",
        "about:blank",
    ]


def _close_login_page(page: Any) -> None:
    """Fecha somente a pagina criada para o login, sem encerrar o Chrome do usuario."""
    try:
        if not page.is_closed():
            page.close(run_before_unload=False)
    except Exception:  # Playwright pode perder a conexao quando a janela ja fechou.
        return


def _free_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])
