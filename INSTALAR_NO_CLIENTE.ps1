<#!
.SYNOPSIS
Prepara a cópia distribuída por ZIP da automação de conciliação.

.DESCRIPTION
Instala uv no perfil do usuário quando necessário, sincroniza as dependências
declaradas no projeto e instala o Chromium do Playwright. Não solicita nem
persiste credenciais, tokens ou dados de entrada.
#>

$ErrorActionPreference = "Stop"

function Fail-Step {
    param([string]$Message)
    Write-Host "[ERRO] $Message" -ForegroundColor Red
    exit 1
}

function Refresh-UvPath {
    foreach ($candidate in @(
        (Join-Path $env:USERPROFILE ".local\bin"),
        (Join-Path $env:USERPROFILE ".cargo\bin")
    )) {
        if ((Test-Path $candidate) -and ($env:Path -notlike "*$candidate*")) {
            $env:Path = "$candidate;$env:Path"
        }
    }
}

$projectRoot = Resolve-Path $PSScriptRoot
Set-Location $projectRoot

if (-not (Test-Path "pyproject.toml")) {
    Fail-Step "Execute este arquivo dentro da pasta extraída do pacote."
}

Refresh-UvPath
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "Instalando o gerenciador de dependências uv..."
    try {
        Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    } catch {
        Fail-Step "Não foi possível instalar o uv. Verifique a internet e execute novamente."
    }
    Refresh-UvPath
}

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Fail-Step "uv não está disponível após a instalação. Feche e abra o PowerShell, depois execute este arquivo novamente."
}

Write-Host "Preparando Python 3.12 e bibliotecas do projeto..."
& uv python install 3.12
if ($LASTEXITCODE -ne 0) { Fail-Step "Falha ao instalar ou localizar Python 3.12." }

& uv sync --extra dev
if ($LASTEXITCODE -ne 0) { Fail-Step "Falha ao instalar as bibliotecas do projeto." }

Write-Host "Instalando o Chromium para o login manual assistido..."
& uv run playwright install chromium
if ($LASTEXITCODE -ne 0) { Fail-Step "Falha ao instalar o Chromium do Playwright." }

Write-Host ""
Write-Host "INSTALAÇÃO CONCLUÍDA" -ForegroundColor Green
Write-Host "Para usar a pipeline, consulte README_INSTALACAO_CLIENTE.md."
