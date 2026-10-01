"""Protótipo de login Velo com Selenium, limitado a branches de teste.

Este script nunca grava nem exibe credenciais, cookies, tokens ou respostas de
autenticação. Ele não tenta resolver CAPTCHA, MFA ou qualquer outro desafio de
segurança: quando houver um desafio, a pessoa operadora deve concluí-lo no
Chrome aberto.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOGIN_ENV_FILE = PROJECT_ROOT / "LoginTest" / ".env"


def current_branch() -> str:
    """Retorna a branch atual sem registrar dados sensíveis."""
    result = subprocess.run(
        ["git", "-C", str(PROJECT_ROOT), "branch", "--show-current"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def require_test_branch() -> None:
    branch = current_branch()
    if not branch.startswith("test/"):
        raise RuntimeError(
            "Login automático só pode ser executado em uma branch cujo nome comece com 'test/'."
        )


def required_value(values: dict[str, str | None], *names: str) -> str:
    for name in names:
        value = os.environ.get(name) or values.get(name)
        if value:
            return value
    name_list = " ou ".join(names)
    raise RuntimeError(
        f"Defina {name_list} na sessão ou em {LOGIN_ENV_FILE.relative_to(PROJECT_ROOT)}."
    )


def load_login_values() -> dict[str, str | None]:
    """Lê o .env local sem imprimir, gravar ou alterar o ambiente do processo."""
    if not LOGIN_ENV_FILE.is_file():
        return {}
    try:
        from dotenv import dotenv_values
    except ImportError as error:
        raise RuntimeError(
            "Instale as dependências com: pip install -r login_automatico/requirements.txt"
        ) from error
    return dict(dotenv_values(LOGIN_ENV_FILE))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preenche o formulário de login Velo em Chrome visível."
    )
    parser.add_argument("--url", default=os.environ.get("VELO_LOGIN_URL"))
    parser.add_argument(
        "--usuario-selector",
        default=os.environ.get("VELO_USUARIO_SELECTOR", "#email"),
    )
    parser.add_argument(
        "--senha-selector",
        default=os.environ.get("VELO_SENHA_SELECTOR", "input[type='password']"),
    )
    parser.add_argument(
        "--entrar-selector",
        default=os.environ.get("VELO_ENTRAR_SELECTOR", "button.button-primary"),
    )
    parser.add_argument("--timeout", type=int, default=30)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        require_test_branch()
        login_values = load_login_values()
        url = args.url or required_value(login_values, "VELO_LOGIN_URL")
        usuario_selector = args.usuario_selector or required_value(
            login_values, "VELO_USUARIO_SELECTOR"
        )
        senha_selector = args.senha_selector or required_value(login_values, "VELO_SENHA_SELECTOR")
        entrar_selector = args.entrar_selector or required_value(
            login_values, "VELO_ENTRAR_SELECTOR"
        )
        usuario = required_value(login_values, "VELO_LOGIN_USUARIO", "VELO_USUARIO")
        senha = required_value(login_values, "VELO_LOGIN_SENHA", "VELO_SENHA")
    except (RuntimeError, subprocess.CalledProcessError) as error:
        print(f"Erro: {error}", file=sys.stderr)
        return 2

    try:
        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as conditions
        from selenium.webdriver.support.ui import WebDriverWait
    except ImportError:
        print(
            "Erro: instale as dependências com: pip install -r login_automatico/requirements.txt",
            file=sys.stderr,
        )
        return 2

    options = webdriver.ChromeOptions()
    options.add_experimental_option("detach", True)
    driver = webdriver.Chrome(options=options)
    wait = WebDriverWait(driver, args.timeout)

    try:
        driver.get(url)
        wait.until(
            conditions.visibility_of_element_located((By.CSS_SELECTOR, usuario_selector))
        ).send_keys(usuario)
        wait.until(
            conditions.visibility_of_element_located((By.CSS_SELECTOR, senha_selector))
        ).send_keys(senha)
        wait.until(conditions.element_to_be_clickable((By.CSS_SELECTOR, entrar_selector))).click()
        print(
            "Formulário enviado no Chrome visível. "
            "Conclua manualmente qualquer CAPTCHA, MFA ou desafio."
        )
        input("Depois de concluir ou cancelar o teste, pressione Enter para encerrar o script: ")
        return 0
    finally:
        # O Chrome permanece aberto para a pessoa concluir desafios; o processo não persiste dados.
        del driver


if __name__ == "__main__":
    raise SystemExit(main())
