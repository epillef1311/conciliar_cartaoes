import importlib.util
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "LoginTest" / "validate_token_test.py"
SPEC = importlib.util.spec_from_file_location("validate_token_test", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
validate_token_test = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validate_token_test)


def test_sanitize_data_masks_nested_sensitive_values() -> None:
    data = {"accessToken": "segredo", "nested": [{"Authorization": "outro"}]}

    assert validate_token_test.sanitize_data(data) == {
        "accessToken": "[REMOVIDO]",
        "nested": [{"Authorization": "[REMOVIDO]"}],
    }


def test_classify_distinguishes_authorization_from_authentication() -> None:
    assert validate_token_test.classify(200, {"ok": True}) == 0
    assert validate_token_test.classify(401, {"message": "unauthorized"}) == 2
    assert validate_token_test.classify(403, {"message": "permission denied"}) == 1
    assert validate_token_test.classify(403, {"message": "token expirado"}) == 2


def test_parse_response_never_persists_non_json_body() -> None:
    assert validate_token_test.parse_response(b"token-secreto", "text/html") == {
        "content_type": "text/html",
        "body_is_json": False,
    }


def test_read_token_rejects_missing_or_empty_files(tmp_path: Path) -> None:
    missing_file = tmp_path / "missing.txt"
    empty_file = tmp_path / "empty.txt"
    empty_file.write_text("  ", encoding="utf-8")

    for token_file, expected_error in ((missing_file, "nao encontrado"), (empty_file, "vazio")):
        try:
            validate_token_test.read_token(token_file)
        except RuntimeError as error:
            assert expected_error in str(error)
        else:
            raise AssertionError("Era esperado erro para arquivo de token invalido.")
