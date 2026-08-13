from pathlib import Path

from conciliacao.integrations.velo.manual_login import (
    ManualLoginTokenProvider,
    _chrome_launch_command,
    extract_token_from_post_data,
)


def test_extract_token_accepts_only_expected_json_field() -> None:
    assert extract_token_from_post_data('{"token":" valor-artificial "}') == (
        "valor-artificial"
    )
    assert extract_token_from_post_data('{"access_token":"outro"}') is None
    assert extract_token_from_post_data("nao-json") is None
    assert extract_token_from_post_data(None) is None


def test_manual_provider_captures_once_and_clears_without_leak() -> None:
    calls = 0

    def capture() -> str:
        nonlocal calls
        calls += 1
        return "token-teste-nao-real"

    provider = ManualLoginTokenProvider(capture)
    assert provider.get_token() == "token-teste-nao-real"
    assert provider.get_token() == "token-teste-nao-real"
    assert calls == 1
    assert "token-teste-nao-real" not in repr(provider)

    provider.clear()
    assert provider.get_token() == "token-teste-nao-real"
    assert calls == 2


def test_manual_login_opens_blank_page_before_navigation() -> None:
    command = _chrome_launch_command(Path("chrome.exe"), 9222, Path("profile"))

    assert "--new-window" in command
    assert command[-1] == "about:blank"
    assert "--remote-debugging-port=9222" in command
