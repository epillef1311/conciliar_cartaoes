param(
    [Parameter(Mandatory = $true)]
    [string]$DataInicio,

    [Parameter(Mandatory = $true)]
    [string]$DataFim,

    [Parameter(Mandatory = $true)]
    [string]$ArquivoCielo,

    [Parameter(Mandatory = $true)]
    [string]$ArquivoQuickpay,

    [switch]$DryRun
)

$argsList = @(
    "-m", "conciliacao.cli",
    "processar",
    "--data-inicio", $DataInicio,
    "--data-fim", $DataFim,
    "--arquivo-cielo", $ArquivoCielo,
    "--arquivo-quickpay", $ArquivoQuickpay
)

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
