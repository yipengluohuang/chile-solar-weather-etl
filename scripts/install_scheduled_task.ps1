param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern("^([01]\d|2[0-3]):[0-5]\d$")]
    [string]$RunTime,

    [string]$TaskName = "ChileSolarWeatherETL",

    [string]$PythonExe = "C:\Users\Equipo\AppData\Local\Python\pythoncore-3.14-64\python.exe"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$RunnerScript = Join-Path $PSScriptRoot "run_pipeline.ps1"

if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
    throw "Global Python executable not found: $PythonExe"
}
if (-not (Test-Path -LiteralPath $RunnerScript -PathType Leaf)) {
    throw "Task runner script not found: $RunnerScript"
}

$PowerShellExe = (Get-Command powershell.exe -ErrorAction Stop).Source
$ActionArguments = (
    '-NoProfile -ExecutionPolicy Bypass -File "{0}" -PythonExe "{1}"' -f `
        $RunnerScript, $PythonExe
)
$Action = New-ScheduledTaskAction `
    -Execute $PowerShellExe `
    -Argument $ActionArguments `
    -WorkingDirectory $ProjectRoot

$DailyTime = [datetime]::ParseExact($RunTime, "HH:mm", $null)
$Trigger = New-ScheduledTaskTrigger -Daily -At $DailyTime
$Settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 15) `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
    -StartWhenAvailable `
    -WakeToRun

$CurrentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$Principal = New-ScheduledTaskPrincipal `
    -UserId $CurrentUser `
    -LogonType Interactive `
    -RunLevel Limited

$Task = New-ScheduledTask `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Principal $Principal `
    -Description "Chile Solar Weather ETL Pipeline V4 daily run"

Register-ScheduledTask -TaskName $TaskName -InputObject $Task -Force | Out-Null

Write-Host "Scheduled task created: $TaskName"
Write-Host "Daily run time: $RunTime"
Write-Host "View task: Get-ScheduledTask -TaskName '$TaskName'"
Write-Host "Manual test: Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "View result: Get-ScheduledTaskInfo -TaskName '$TaskName'"
