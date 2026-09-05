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

if ($RegisterRecoveryTask -and -not $NoStartup) {
    throw "Выберите один механизм запуска: обычный HKCU Run или -RegisterRecoveryTask с -NoStartup."
}

$resolvedInstallPath = [System.IO.Path]::GetFullPath($InstallPath)
New-Item -ItemType Directory -Path $resolvedInstallPath -Force | Out-Null
Copy-Item -Path (Join-Path $resolvedPublishPath "*") -Destination $resolvedInstallPath -Recurse -Force
$installedExecutable = Join-Path $resolvedInstallPath "GameClub.Client.exe"
Set-Content -LiteralPath (Join-Path $resolvedInstallPath ".gameclub-installation") -Value "GameClub.Client" -Encoding UTF8

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
