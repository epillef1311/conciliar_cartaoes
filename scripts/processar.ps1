param(
    [Parameter(Mandatory = $true)]
    [string]$DataInicio,

    [Parameter(Mandatory = $true)]
    [string]$DataFim,

    [string]$ArquivoCielo,

    [string]$ArquivoQuickpay,

    [string]$Saida = "output",

    [switch]$Sobrescrever,

    [switch]$ModoSimulado,

    [string]$FixturesApi,

    [switch]$SalvarAuditoria,

    [switch]$DryRun
)

if (-not $ModoSimulado -and -not $env:VELO_BEARER_TOKEN) {
    Write-Error "Defina VELO_BEARER_TOKEN no ambiente antes de executar em modo real."
    exit 4
}

$argsList = @(
    "-m", "conciliacao.cli",
    "processar",
    "--data-inicio", $DataInicio,
    "--data-fim", $DataFim,
    "--saida", $Saida
)

if ($ArquivoCielo) {
    $argsList += @("--arquivo-cielo", $ArquivoCielo)
}
if ($ArquivoQuickpay) {
    $argsList += @("--arquivo-quickpay", $ArquivoQuickpay)
}
if ($Sobrescrever) {
    $argsList += "--sobrescrever"
}
if ($ModoSimulado) {
    $argsList += "--modo-simulado"
}
if ($FixturesApi) {
    $argsList += @("--fixtures-api", $FixturesApi)
}
if ($SalvarAuditoria) {
    $argsList += "--salvar-auditoria"
}
if ($DryRun) {
    $argsList += "--dry-run"
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$srcPath = Join-Path $repoRoot "src"
if ($env:PYTHONPATH) {
    $env:PYTHONPATH = "$srcPath;$env:PYTHONPATH"
} else {
    $env:PYTHONPATH = $srcPath
}

$localPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (Test-Path $localPython) {
    & $localPython @argsList
} else {
    python @argsList
}
exit $LASTEXITCODE
