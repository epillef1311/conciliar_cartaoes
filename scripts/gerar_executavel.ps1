$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

$uv = Get-Command uv -ErrorAction SilentlyContinue
if ($null -ne $uv) {
  uv run --extra build python scripts/recortar_logo.py
  uv run --extra build python scripts/gerar_icone.py
  uv run --extra build pyinstaller --noconfirm --clean --windowed --onedir `
    --name ConciliacaoCartoes_FrigorificoCandeias `
    --icon assets/frigorifico-candeias.ico `
    --add-data 'assets;assets' `
    --add-data 'config;config' `
    --paths src `
    --collect-all playwright `
    --collect-all PySide6 `
    src/conciliacao/gui.py
} else {
  $python = Join-Path $projectRoot '.venv\Scripts\python.exe'
  if (-not (Test-Path $python)) {
    throw 'uv não foi localizado e o ambiente virtual .venv não está disponível.'
  }
  & $python scripts/recortar_logo.py
  & $python scripts/gerar_icone.py
  & $python -m PyInstaller --noconfirm --clean --windowed --onedir `
    --name ConciliacaoCartoes_FrigorificoCandeias `
    --icon assets/frigorifico-candeias.ico `
    --add-data 'assets;assets' `
    --add-data 'config;config' `
    --paths src `
    --collect-all playwright `
    --collect-all PySide6 `
    src/conciliacao/gui.py
}

Write-Host "Executável gerado em: $projectRoot\dist\ConciliacaoCartoes_FrigorificoCandeias\ConciliacaoCartoes_FrigorificoCandeias.exe"
