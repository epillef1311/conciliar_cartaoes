import importlib.util
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "LoginTest" / "capture_manual_login_token.py"
SPEC = importlib.util.spec_from_file_location("capture_manual_login_token", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
capture_manual_login_token = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(capture_manual_login_token)


def test_extract_token_accepts_only_non_empty_string() -> None:
    assert capture_manual_login_token.extract_token({"token": "  abc  "}) == "abc"
    assert capture_manual_login_token.extract_token({"token": "  "}) is None
    assert capture_manual_login_token.extract_token({"token": 10}) is None
    assert capture_manual_login_token.extract_token(["token"]) is None
