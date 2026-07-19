from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PS_SCRIPT = ROOT / "scripts" / "preparar_ambiente.ps1"
BAT_SCRIPT = ROOT / "scripts" / "preparar_ambiente.bat"
README = ROOT / "README.md"


def test_powershell_script_contains_required_checks_and_commands() -> None:
    content = PS_SCRIPT.read_text(encoding="utf-8")

    assert "PREPARACAO DO AMBIENTE" in content
    assert "pyproject.toml" in content
    assert "$MinimumPowerShellMajor = 5" in content
    assert "git --version" in content
    assert "Python 3.12" in content
    assert "uv --version" in content
    assert "uv sync --frozen" in content
    assert "uv sync" in content
    assert "uv run python --version" in content
    assert "uv run pytest" in content
    assert "uv run ruff check ." in content
    assert "uv run mypy src" in content
    assert "testar-integracao-velo" in content
    assert "AMBIENTE PRONTO" in content


def test_powershell_script_uses_official_uv_installation_source() -> None:
    content = PS_SCRIPT.read_text(encoding="utf-8")

    assert "https://docs.astral.sh/uv/getting-started/installation/" in content
    assert "https://astral.sh/uv/install.ps1" in content


def test_powershell_script_does_not_print_sensitive_values() -> None:
    content = PS_SCRIPT.read_text(encoding="utf-8")

    assert "Authorization" not in content
    assert "Bearer" not in content
    assert "VELO_BEARER_TOKEN" not in content
    assert "Write-Host $env:" not in content


def test_bat_delegates_to_powershell_and_preserves_exit_code() -> None:
    content = BAT_SCRIPT.read_text(encoding="utf-8")

    assert "preparar_ambiente.ps1" in content
    assert "powershell -NoProfile -ExecutionPolicy Bypass" in content
    assert "set \"EXIT_CODE=%ERRORLEVEL%\"" in content
    assert "exit /b %EXIT_CODE%" in content
    assert "pause" in content


def test_bat_does_not_duplicate_environment_logic() -> None:
    content = BAT_SCRIPT.read_text(encoding="utf-8")

    assert "uv sync" not in content
    assert "pytest" not in content
    assert "ruff" not in content
    assert "mypy" not in content


def test_readme_documents_minimal_setup_commands() -> None:
    content = README.read_text(encoding="utf-8")
    section = content.split("## Preparação em outro computador", 1)[1].split("## ", 1)[0]

    assert "## Preparação em outro computador" in content
    assert "git clone <REPOSITORIO>" in section
    assert "cd conciliacaoCartoes" in section
    assert r".\scripts\preparar_ambiente.ps1" in section
    assert "VELO_BEARER_TOKEN=" not in section
