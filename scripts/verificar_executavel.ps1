param(
  [string]$Executavel = (Join-Path (Split-Path -Parent $PSScriptRoot) 'dist\ConciliacaoCartoes_FrigorificoCandeias\ConciliacaoCartoes_FrigorificoCandeias.exe'),
  [ValidateSet('windows', 'offscreen')]
  [string]$Plataforma = 'windows'
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $Executavel -PathType Leaf)) {
  throw "Executável não encontrado: $Executavel"
}
$previousPlatform = $env:QT_QPA_PLATFORM
$verificationProcess = $null
try {
  # Inicia a GUI empacotada e encerra automaticamente, sem executar o workflow.
  $env:QT_QPA_PLATFORM = $Plataforma
  $verificationProcess = Start-Process -FilePath $Executavel -ArgumentList '--verificar-interface' -WindowStyle Hidden -PassThru
  if (-not $verificationProcess.WaitForExit(20000)) {
    Stop-Process -Id $verificationProcess.Id -ErrorAction SilentlyContinue
    throw 'O aplicativo empacotado não concluiu o teste de inicialização em 20 segundos.'
  }
  $verificationProcess.Refresh()
  if ($verificationProcess.ExitCode -ne 0) {
    throw "O aplicativo empacotado falhou ao iniciar (código $($verificationProcess.ExitCode))."
  }
  Write-Host 'Inicialização da interface empacotada verificada com sucesso.'
} finally {
  $env:QT_QPA_PLATFORM = $previousPlatform
  if ($null -ne $verificationProcess) { $verificationProcess.Dispose() }
}
