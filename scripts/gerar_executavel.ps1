$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

$uv = Get-Command uv -ErrorAction SilentlyContinue
if ($null -ne $uv) {
  uv run --extra build python scripts/recortar_logo.py
  if ($LASTEXITCODE -ne 0) { throw 'Falha ao preparar o logo. Compilação interrompida.' }
  uv run --extra build python scripts/gerar_icone.py
  if ($LASTEXITCODE -ne 0) { throw 'Falha ao preparar o ícone. Compilação interrompida.' }
  uv run --extra build pyinstaller --noconfirm --clean --windowed --onedir `
    --name ConciliacaoCartoes_FrigorificoCandeias `
    --icon assets/frigorifico-candeias.ico `
    --add-data 'assets;assets' `
    --add-data 'config;config' `
    --paths src `
    --collect-all playwright `
    --collect-all PySide6 `
    src/conciliacao/gui.py
  if ($LASTEXITCODE -ne 0) { throw 'PyInstaller falhou. O executável não foi atualizado.' }
} else {
  $python = Join-Path $projectRoot '.venv\Scripts\python.exe'
  if (-not (Test-Path $python)) {
    throw 'uv não foi localizado e o ambiente virtual .venv não está disponível.'
  }
  & $python scripts/recortar_logo.py
  if ($LASTEXITCODE -ne 0) { throw 'Falha ao preparar o logo. Compilação interrompida.' }
  & $python scripts/gerar_icone.py
  if ($LASTEXITCODE -ne 0) { throw 'Falha ao preparar o ícone. Compilação interrompida.' }
  & $python -m PyInstaller --noconfirm --clean --windowed --onedir `
    --name ConciliacaoCartoes_FrigorificoCandeias `
    --icon assets/frigorifico-candeias.ico `
    --add-data 'assets;assets' `
    --add-data 'config;config' `
    --paths src `
    --collect-all playwright `
    --collect-all PySide6 `
    src/conciliacao/gui.py
  if ($LASTEXITCODE -ne 0) { throw 'PyInstaller falhou. O executável não foi atualizado.' }
}

Write-Host "Executável gerado em: $projectRoot\dist\ConciliacaoCartoes_FrigorificoCandeias\ConciliacaoCartoes_FrigorificoCandeias.exe"
