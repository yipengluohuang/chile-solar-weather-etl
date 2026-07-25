param(
    [string]$PythonExe = "C:\Users\Equipo\AppData\Local\Python\pythoncore-3.14-64\python.exe"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$MainScript = Join-Path $ProjectRoot "src\main.py"
$LogsDirectory = Join-Path $ProjectRoot "logs"
$SchedulerLog = Join-Path $LogsDirectory "scheduler.log"
$StartedAt = Get-Date
$ExitCode = 1

New-Item -ItemType Directory -Path $LogsDirectory -Force | Out-Null
Add-Content -LiteralPath $SchedulerLog -Encoding utf8 -Value (
    "{0:yyyy-MM-dd HH:mm:ss} | START | Python={1}" -f $StartedAt, $PythonExe
)

try {
    if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
        throw "Global Python executable not found: $PythonExe"
    }
    if (-not (Test-Path -LiteralPath $MainScript -PathType Leaf)) {
        throw "Pipeline script not found: $MainScript"
    }

    Set-Location -LiteralPath $ProjectRoot
    & $PythonExe $MainScript
    $ExitCode = $LASTEXITCODE
    if ($null -eq $ExitCode) {
        $ExitCode = 1
    }
}
catch {
    $ExitCode = 1
    Add-Content -LiteralPath $SchedulerLog -Encoding utf8 -Value (
        "{0:yyyy-MM-dd HH:mm:ss} | ERROR | {1}" -f (Get-Date), $_.Exception.Message
    )
    Write-Error $_
}
finally {
    $FinishedAt = Get-Date
    Add-Content -LiteralPath $SchedulerLog -Encoding utf8 -Value (
        "{0:yyyy-MM-dd HH:mm:ss} | END | ExitCode={1} | DurationSeconds={2:N2}" -f `
            $FinishedAt, $ExitCode, ($FinishedAt - $StartedAt).TotalSeconds
    )
}

exit $ExitCode
