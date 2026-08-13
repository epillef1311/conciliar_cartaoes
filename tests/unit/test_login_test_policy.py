import importlib.util
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "LoginTest" / "login_test.py"
SPEC = importlib.util.spec_from_file_location("login_test", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
login_test = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(login_test)


def test_login_response_sanitization_and_token_discovery() -> None:
    response = {"accessToken": "segredo", "usuario": {"senha": "oculta"}}

    assert login_test.find_token(response) == "segredo"
    assert login_test.sanitize_data(response) == {
        "accessToken": "[REMOVIDO]",
        "usuario": {"senha": "[REMOVIDO]"},
    }
