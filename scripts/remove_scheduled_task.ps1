param(
    [string]$TaskName = "ChileSolarWeatherETL"
)

$ErrorActionPreference = "Stop"
$Task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue

if ($null -eq $Task) {
    Write-Host "Scheduled task does not exist: $TaskName"
    exit 0
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
Write-Host "Scheduled task removed: $TaskName"
Write-Host "Project files and data were not deleted."
