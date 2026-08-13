import importlib.util
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "LoginTest" / "capture_cdp_manual_token.py"
SPEC = importlib.util.spec_from_file_location("capture_cdp_manual_token", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
capture_cdp_manual_token = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(capture_cdp_manual_token)


def test_extract_token_from_post_data_accepts_only_valid_json_token() -> None:
    assert capture_cdp_manual_token.extract_token_from_post_data('{"token": " abc "}') == "abc"
    assert capture_cdp_manual_token.extract_token_from_post_data('{"token": 1}') is None
    assert capture_cdp_manual_token.extract_token_from_post_data("not-json") is None
