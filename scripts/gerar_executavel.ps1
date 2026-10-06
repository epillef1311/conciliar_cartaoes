param(
  [ValidatePattern('^dist([\\/][a-zA-Z0-9_-]+)*$')]
  [string]$DiretorioDistribuicao = 'dist'
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

$previousBuildPath = $env:PATH
try {
  # Priorize bibliotecas do Windows ao resolver DLLs de sistema (como ICU).
  # Ferramentas externas no PATH podem fornecer DLLs de mesmo nome e ABI incompatível.
  $env:PATH = (Join-Path $env:SystemRoot 'System32') + ';' + $env:SystemRoot + ';' + $env:PATH

  $uv = Get-Command uv -ErrorAction SilentlyContinue
  if ($null -ne $uv) {
    uv run --extra build python scripts/recortar_logo.py
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao preparar o logo. Compilação interrompida.' }
    uv run --extra build python scripts/gerar_icone.py
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao preparar o ícone. Compilação interrompida.' }
    uv run --extra build pyinstaller --noconfirm --clean --windowed --onedir `
      --distpath $DiretorioDistribuicao `
      --name ConciliacaoCartoes_FrigorificoCandeias `
      --icon assets/frigorifico-candeias.ico `
      --add-data 'assets;assets' `
      --add-data 'config;config' `
      --paths src `
      --collect-all playwright `
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
      --distpath $DiretorioDistribuicao `
      --name ConciliacaoCartoes_FrigorificoCandeias `
      --icon assets/frigorifico-candeias.ico `
      --add-data 'assets;assets' `
      --add-data 'config;config' `
      --paths src `
      --collect-all playwright `
      src/conciliacao/gui.py
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller falhou. O executável não foi atualizado.' }
  }

  $executavelGerado = Join-Path $projectRoot "$DiretorioDistribuicao\ConciliacaoCartoes_FrigorificoCandeias\ConciliacaoCartoes_FrigorificoCandeias.exe"
  & (Join-Path $PSScriptRoot 'verificar_executavel.ps1') -Executavel $executavelGerado

  Write-Host "Executável gerado em: $executavelGerado"
} finally {
  $env:PATH = $previousBuildPath
}
