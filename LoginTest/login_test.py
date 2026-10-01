"""Teste manual e autorizado de login Velo via navegador visivel."""

import json
import os
import re
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"
TOKEN_FILE = OUTPUT_DIR / "token.txt"
STATE_FILE = OUTPUT_DIR / "storage_state.json"
SANITIZED_RESPONSE_FILE = OUTPUT_DIR / "login_response_sanitized.json"
ERROR_SCREENSHOT_FILE = OUTPUT_DIR / "login_error.png"
TOKEN_KEYS = {"token", "access_token", "accessToken", "jwt", "bearerToken", "authToken"}
SENSITIVE_KEYS = TOKEN_KEYS | {
    "password",
    "pass",
    "senha",
    "refreshToken",
    "refresh_token",
}


def find_token(data: Any) -> str | None:
    if isinstance(data, dict):
        for key, value in data.items():
            if key in TOKEN_KEYS and isinstance(value, str) and value:
                return value
        for value in data.values():
            token = find_token(value)
            if token:
                return token
    if isinstance(data, list):
        for item in data:
            token = find_token(item)
            if token:
                return token
    return None


def sanitize_data(data: Any) -> Any:
    if isinstance(data, dict):
        return {
            key: "[REMOVIDO]" if key in SENSITIVE_KEYS else sanitize_data(value)
            for key, value in data.items()
        }
    if isinstance(data, list):
        return [sanitize_data(item) for item in data]
    return data


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"A variavel de ambiente obrigatoria {name} nao foi preenchida.")
    return value


def main() -> int:
    from dotenv import load_dotenv
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright

    load_dotenv(BASE_DIR / ".env")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    page = None
    try:
        login_url = os.getenv("VELO_LOGIN_URL", "https://app.velosistema.com.br/").strip()
        login_endpoint = os.getenv("VELO_LOGIN_ENDPOINT", "/login/auth").strip()
        usuario = require_env("VELO_USUARIO")
        senha = require_env("VELO_SENHA")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=False)
            context = browser.new_context()
            try:
                page = context.new_page()
                page.goto(login_url, wait_until="domcontentloaded", timeout=60_000)
                user_input = page.locator(
                    'input[type="email"], input[name="user"], input[name="email"], '
                    'input[formcontrolname="user"], input[formcontrolname="email"]'
                ).first
                password_input = page.locator(
                    'input[type="password"], input[name="pass"], input[name="password"], '
                    'input[formcontrolname="pass"], input[formcontrolname="password"]'
                ).first
                user_input.wait_for(state="visible", timeout=20_000)
                password_input.wait_for(state="visible", timeout=20_000)
                user_input.fill(usuario)
                password_input.fill(senha)
                login_button = page.get_by_role(
                    "button", name=re.compile(r"entrar|login|acessar", re.IGNORECASE)
                ).first
                login_button.wait_for(state="visible", timeout=20_000)
                with page.expect_response(
                    lambda response: login_endpoint in response.url
                    and response.request.method == "POST",
                    timeout=30_000,
                ) as response_info:
                    login_button.click()
                response = response_info.value
                try:
                    response_data = response.json()
                except Exception:
                    response_data = {
                        "content_type": response.headers.get("content-type"),
                        "body_not_json": True,
                    }
                SANITIZED_RESPONSE_FILE.write_text(
                    json.dumps(sanitize_data(response_data), ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                context.storage_state(path=str(STATE_FILE))
                token = find_token(response_data)
                if not token:
                    page.wait_for_timeout(2_000)
                    match = re.search(r"/auth/([^/?#]+)", page.url)
                    token = match.group(1) if match else None
                print(f"Status HTTP: {response.status}")
                print(f"Endpoint: {response.url}")
                if isinstance(response_data, dict):
                    print(f"Chaves principais: {list(response_data.keys())}")
                if token:
                    TOKEN_FILE.write_text(token, encoding="utf-8")
                    print("Token encontrado: sim")
                    print(f"Tamanho do token: {len(token)} caracteres")
                    return 0
                print("Token encontrado: nao")
                return 1
            except PlaywrightTimeoutError as error:
                print(f"Timeout durante o login: {error}")
                if page is not None:
                    try:
                        page.screenshot(path=str(ERROR_SCREENSHOT_FILE), full_page=True)
                        print(f"Screenshot salvo em: {ERROR_SCREENSHOT_FILE}")
                    except Exception as screenshot_error:
                        print(f"Nao foi possivel salvar screenshot: {screenshot_error}")
                return 1
            finally:
                context.close()
                browser.close()
    except Exception as error:
        print(f"Falha no teste de login: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
