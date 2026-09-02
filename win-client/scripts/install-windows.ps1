[CmdletBinding()]
param(
    [string]$PublishPath = $PSScriptRoot,
    [string]$InstallPath = (Join-Path ([Environment]::GetFolderPath("LocalApplicationData")) "GameClub\Client"),
    [switch]$NoStartup,
    [switch]$RegisterRecoveryTask
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not [System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform(
        [System.Runtime.InteropServices.OSPlatform]::Windows)) {
    throw "Установка WinUI-клиента выполняется только на Windows."
}

$resolvedPublishPath = (Resolve-Path -LiteralPath $PublishPath -ErrorAction Stop).Path
$sourceExecutable = Join-Path $resolvedPublishPath "GameClub.Client.exe"
if (-not (Test-Path -LiteralPath $sourceExecutable -PathType Leaf)) {
    throw "В каталоге публикации не найден GameClub.Client.exe: $resolvedPublishPath"
}

New-Item -ItemType Directory -Path $InstallPath -Force | Out-Null
Copy-Item -Path (Join-Path $resolvedPublishPath "*") -Destination $InstallPath -Recurse -Force
$installedExecutable = Join-Path $InstallPath "GameClub.Client.exe"

if (-not $NoStartup) {
    $runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
    New-Item -Path $runKey -Force | Out-Null
    Set-ItemProperty -Path $runKey -Name "GameClub.Client" -Value ('"{0}"' -f $installedExecutable)
}

if ($RegisterRecoveryTask) {
    $taskName = "GameClub.Client.Recovery"
    $action = New-ScheduledTaskAction -Execute $installedExecutable
    $trigger = New-ScheduledTaskTrigger -AtLogOn
    $settings = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
}

Write-Host "GameClub Client установлен: $installedExecutable"
if (-not $NoStartup) {
    Write-Host "Автозапуск зарегистрирован для текущего пользователя."
}
Write-Host "Первая привязка выполняется автоматически по MAC после назначения ПК в админке."
Write-Host "Для полного kiosk-ограничения Windows отдельно используйте Assigned Access или Shell Launcher."
