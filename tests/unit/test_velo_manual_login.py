from pathlib import Path

from conciliacao.integrations.velo.manual_login import (
    ManualLoginTokenProvider,
    _chrome_launch_command,
    extract_token_from_post_data,
)


def test_extract_token_accepts_only_expected_json_field() -> None:
    assert extract_token_from_post_data('{"token":" valor-artificial "}') == ("valor-artificial")
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


def test_capture_returns_while_browser_remains_open(tmp_path, monkeypatch, capsys):
    from types import SimpleNamespace

    import playwright.sync_api

    import conciliacao.integrations.velo.manual_login as login

    calls = []
    token = "sessao-artificial-apenas-em-memoria"

    class Session:
        callback = None

        def send(self, method):
            assert method == "Network.enable"

        def on(self, name, callback):
            assert name == "Network.requestWillBeSent"
            self.callback = callback

        def remove_listener(self, name, callback):
            assert callback == self.callback
            self.callback = None
            calls.append("listener_removed")

        def detach(self):
            raise AssertionError("A captura não deve aguardar detach remoto")

    session = Session()

    class Page:
        def goto(self, url, **kwargs):
            calls.append("navigate")
            assert session.callback is not None

        def wait_for_timeout(self, interval):
            session.callback(
                {
                    "request": {
                        "method": "GET",
                        "url": "https://app.test/session/validate",
                        "postData": '{"token":"ignorar"}',
                    }
                }
            )
            session.callback(
                {
                    "request": {
                        "method": "POST",
                        "url": "https://app.test/outro",
                        "postData": '{"token":"ignorar"}',
                    }
                }
            )
            session.callback(
                {
                    "request": {
                        "method": "POST",
                        "url": "https://app.test/session/validate",
                        "postData": '{"token":"' + token + '"}',
                    }
                }
            )
            # Outra validação sem token não pode apagar a sessão já capturada.
            session.callback(
                {
                    "request": {
                        "method": "POST",
                        "url": "https://app.test/session/validate",
                        "postData": "{}",
                    }
                }
            )

        def close(self, **kwargs):
            raise AssertionError("A captura não deve aguardar fechamento do Chrome")

    page = Page()
    browser = SimpleNamespace(
        contexts=[SimpleNamespace(new_page=lambda: page, new_cdp_session=lambda p: session)]
    )

    class PlaywrightContext:
        def __enter__(self):
            return object()

        def __exit__(self, *args):
            calls.append("disconnected")

    monkeypatch.setenv("VELO_CHROME_PROFILE_DIR", str(tmp_path / "profile"))
    monkeypatch.setattr(playwright.sync_api, "sync_playwright", PlaywrightContext)
    monkeypatch.setattr(login, "_open_login_browser", lambda *args: browser)
    assert login.capture_token_from_visible_chrome() == token
    assert calls == ["navigate", "listener_removed", "disconnected"]
    assert session.callback is None
    assert token not in capsys.readouterr().out
    assert list((tmp_path / "profile").iterdir()) == []


def test_existing_login_chrome_is_reused_without_launching_another(tmp_path, monkeypatch):
    from types import SimpleNamespace

    import conciliacao.integrations.velo.manual_login as login

    (tmp_path / "DevToolsActivePort").write_text("9317\n/devtools/browser/teste", encoding="utf-8")
    connected = []
    browser = object()

    def connect(endpoint, **kwargs):
        connected.append(endpoint)
        return browser

    def unexpected_launch(*args, **kwargs):
        raise AssertionError("Chrome existente deve ser reutilizado")

    monkeypatch.setattr(login.subprocess, "Popen", unexpected_launch)
    playwright = SimpleNamespace(chromium=SimpleNamespace(connect_over_cdp=connect))
    assert login._open_login_browser(playwright, tmp_path, 0, 30) is browser
    assert connected == ["http://127.0.0.1:9317"]


def test_stale_profile_port_relaunches_visible_chrome(tmp_path, monkeypatch):
    from types import SimpleNamespace

    import conciliacao.integrations.velo.manual_login as login

    (tmp_path / "DevToolsActivePort").write_text("9317\n/devtools/browser/teste", encoding="utf-8")
    launched = []

    def disconnected(*args, **kwargs):
        raise RuntimeError("Navegador encerrado")

    monkeypatch.setattr(login, "_chrome_path", lambda: Path("chrome.exe"))
    monkeypatch.setattr(login.subprocess, "Popen", lambda args, **kwargs: launched.append(args))
    browser = object()
    monkeypatch.setattr(login, "_connect_cdp", lambda *args: browser)
    playwright = SimpleNamespace(chromium=SimpleNamespace(connect_over_cdp=disconnected))
    assert login._open_login_browser(playwright, tmp_path, 0, 30) is browser
    assert "--remote-debugging-port=0" in launched[0]
    assert "--new-window" in launched[0]
