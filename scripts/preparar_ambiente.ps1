param(
    [switch]$NaoInstalarUv
)

$ErrorActionPreference = "Stop"
$MinimumPowerShellMajor = 5
$MinimumPowerShellMinor = 1

function Write-Header {
    Write-Host ""
    Write-Host "PREPARACAO DO AMBIENTE"
    Write-Host ""
}

function Write-Ok {
    param([string]$Message)
    Write-Host "[OK] $Message"
}

function Write-Warn {
    param([string]$Message)
    Write-Host "[AVISO] $Message"
}

function Fail-Step {
    param(
        [string]$Step,
        [string]$Command,
        [string]$Guidance,
        [int]$Code = 1
    )
    Write-Host ""
    Write-Host "[ERRO] $Step"
    if ($Command) {
        Write-Host "Comando: $Command"
    }
    Write-Host "Orientacao: $Guidance"
    Write-Host "Codigo de saida: $Code"
    exit $Code
}

function Invoke-Checked {
    param(
        [string]$Step,
        [string]$CommandLabel,
        [scriptblock]$ScriptBlock,
        [string]$Guidance,
        [int]$Code = 1
    )
    try {
        $global:LASTEXITCODE = 0
        & $ScriptBlock
    } catch {
        Fail-Step -Step $Step -Command $CommandLabel -Guidance $Guidance -Code $Code
    }
    if ($LASTEXITCODE -ne $null -and $LASTEXITCODE -ne 0) {
        Fail-Step -Step $Step -Command $CommandLabel -Guidance $Guidance -Code $Code
    }
}

function Refresh-UvPath {
    $candidates = @(
        (Join-Path $env:USERPROFILE ".local\bin"),
        (Join-Path $env:USERPROFILE ".cargo\bin")
    )
    foreach ($candidate in $candidates) {
        if ((Test-Path $candidate) -and ($env:Path -notlike "*$candidate*")) {
            $env:Path = "$candidate;$env:Path"
        }
    }
}

function Test-CompatiblePython {
    $commands = @(
        @{ Name = "py"; Args = @("-3.12", "-c", "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)") },
        @{ Name = "python"; Args = @("-c", "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)") }
    )
    foreach ($candidate in $commands) {
        $command = Get-Command $candidate.Name -ErrorAction SilentlyContinue
        if (-not $command) {
            continue
        }
        & $candidate.Name @($candidate.Args) *> $null
        if ($LASTEXITCODE -eq 0) {
            return $true
        }
    }
    return $false
}

Write-Header

$projectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $projectRoot
if (
    -not (Test-Path "pyproject.toml") -or
    -not (Test-Path "README.md") -or
    -not (Test-Path "src\conciliacao")
) {
    Fail-Step `
        -Step "Projeto nao localizado" `
        -Command "Resolve-Path scripts\.." `
        -Guidance "Execute este script a partir de um clone completo do projeto." `
        -Code 1
}
Write-Ok "Projeto localizado"

$psVersion = $PSVersionTable.PSVersion
if (
    $psVersion.Major -lt $MinimumPowerShellMajor -or
    ($psVersion.Major -eq $MinimumPowerShellMajor -and $psVersion.Minor -lt $MinimumPowerShellMinor)
) {
    Fail-Step `
        -Step "PowerShell incompativel" `
        -Command '$PSVersionTable.PSVersion' `
        -Guidance "Use PowerShell 5.1 ou superior." `
        -Code 1
}
Write-Ok "PowerShell compativel"

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Fail-Step `
        -Step "Git nao encontrado" `
        -Command "git --version" `
        -Guidance "Instale o Git para Windows e execute novamente." `
        -Code 1
}
Invoke-Checked `
    -Step "Git encontrado" `
    -CommandLabel "git --version" `
    -ScriptBlock { git --version | Out-Null } `
    -Guidance "Verifique a instalacao do Git para Windows." `
    -Code 1
Write-Ok "Git encontrado"

if (-not (Test-CompatiblePython)) {
    Fail-Step `
        -Step "Python compativel nao encontrado" `
        -Command "python --version" `
        -Guidance "Instale Python 3.12 ou superior e marque a opcao de adicionar ao PATH." `
        -Code 1
}
Write-Ok "Python compativel"

Refresh-UvPath
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Warn "uv nao encontrado."
    Write-Host "Metodo oficial para Windows: https://docs.astral.sh/uv/getting-started/installation/"
    if ($NaoInstalarUv) {
        Fail-Step `
            -Step "uv ausente" `
            -Command "uv --version" `
            -Guidance "Instale o uv pelo metodo oficial e execute novamente." `
            -Code 1
    }
    $answer = Read-Host "Deseja instalar o uv agora pelo instalador oficial da Astral? [s/N]"
    if ($answer -notin @("s", "S", "sim", "SIM", "Sim")) {
        Fail-Step `
            -Step "uv ausente" `
            -Command "uv --version" `
            -Guidance "Instale o uv pelo metodo oficial e execute novamente." `
            -Code 1
    }
    Invoke-Checked `
        -Step "Instalacao do uv" `
        -CommandLabel 'powershell -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"' `
        -ScriptBlock {
            powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
        } `
        -Guidance "A instalacao oficial do uv falhou. Verifique sua conexao e permissoes." `
        -Code 1
    Refresh-UvPath
}
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Fail-Step `
        -Step "uv nao ficou disponivel apos instalacao" `
        -Command "uv --version" `
        -Guidance "Abra um novo terminal ou ajuste o PATH conforme a instalacao do uv." `
        -Code 1
}
Invoke-Checked `
    -Step "uv encontrado" `
    -CommandLabel "uv --version" `
    -ScriptBlock { uv --version | Out-Null } `
    -Guidance "Verifique a instalacao do uv." `
    -Code 1
Write-Ok "uv encontrado"

if (Test-Path "uv.lock") {
    $syncCommand = "uv sync --frozen"
    Invoke-Checked `
        -Step "Dependencias instaladas" `
        -CommandLabel $syncCommand `
        -ScriptBlock { uv sync --frozen } `
        -Guidance "Falha ao sincronizar dependencias a partir do uv.lock." `
        -Code 1
} else {
    Write-Warn "uv.lock nao encontrado; uv sync pode criar ou atualizar o lockfile."
    $continueWithoutLock = Read-Host "Deseja continuar mesmo sem uv.lock? [s/N]"
    if ($continueWithoutLock -notin @("s", "S", "sim", "SIM", "Sim")) {
        Fail-Step `
            -Step "uv.lock ausente" `
            -Command "uv sync" `
            -Guidance "Inclua um uv.lock no repositorio ou confirme explicitamente a sincronizacao sem lockfile." `
            -Code 1
    }
    $syncCommand = "uv sync"
    Invoke-Checked `
        -Step "Dependencias instaladas" `
        -CommandLabel $syncCommand `
        -ScriptBlock { uv sync } `
        -Guidance "Falha ao sincronizar dependencias. Verifique pyproject.toml e conexao com o indice de pacotes." `
        -Code 1
}
Write-Ok "Dependencias instaladas"

Invoke-Checked `
    -Step "Python do ambiente" `
    -CommandLabel "uv run python --version" `
    -ScriptBlock { uv run python --version } `
    -Guidance "O ambiente criado pelo uv nao conseguiu executar Python." `
    -Code 1
Write-Ok "Python do ambiente confirmado"

Invoke-Checked `
    -Step "Testes automatizados" `
    -CommandLabel "uv run pytest" `
    -ScriptBlock { uv run pytest } `
    -Guidance "Corrija os testes antes de usar o projeto neste computador." `
    -Code 1
Write-Ok "Testes aprovados"

Invoke-Checked `
    -Step "Ruff" `
    -CommandLabel "uv run ruff check ." `
    -ScriptBlock { uv run ruff check . } `
    -Guidance "Corrija os problemas de lint indicados pelo Ruff." `
    -Code 1
Write-Ok "Ruff aprovado"

Invoke-Checked `
    -Step "Tipagem" `
    -CommandLabel "uv run mypy src" `
    -ScriptBlock { uv run mypy src } `
    -Guidance "Corrija os problemas de tipagem indicados pelo mypy." `
    -Code 1
Write-Ok "Tipagem aprovada"

if (Test-Path "tests\fixtures\api") {
    Invoke-Checked `
        -Step "Teste simulado da Velo" `
        -CommandLabel "uv run conciliacao testar-integracao-velo --fixtures tests\fixtures\api --data-inicio 2026-07-14 --data-fim 2026-07-15 --auditoria-dir data\api_raw\preparar_ambiente" `
        -ScriptBlock {
            uv run conciliacao testar-integracao-velo `
                --fixtures "tests\fixtures\api" `
                --data-inicio 2026-07-14 `
                --data-fim 2026-07-15 `
                --auditoria-dir "data\api_raw\preparar_ambiente"
        } `
        -Guidance "A simulacao local da integracao Velo falhou. Nenhum token real e necessario." `
        -Code 1
    Write-Ok "Teste simulado da Velo aprovado"
} else {
    Write-Warn "Fixtures da API nao encontradas; teste simulado da Velo ignorado."
}

Write-Host ""
Write-Host "AMBIENTE PRONTO"
exit 0
