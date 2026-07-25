param(
    [string]$PythonExe = "C:\Users\Equipo\AppData\Local\Python\pythoncore-3.14-64\python.exe"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$HealthScript = Join-Path $ProjectRoot "src\health_check.py"

if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
    Write-Error "Global Python executable not found: $PythonExe"
    exit 2
}

Set-Location -LiteralPath $ProjectRoot
& $PythonExe $HealthScript
$ExitCode = $LASTEXITCODE
if ($null -eq $ExitCode) {
    $ExitCode = 2
}
exit $ExitCode
