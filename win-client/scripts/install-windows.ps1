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
    throw "Установка Avalonia Windows-клиента выполняется только на Windows."
}

$resolvedPublishPath = (Resolve-Path -LiteralPath $PublishPath -ErrorAction Stop).Path
$sourceExecutable = Join-Path $resolvedPublishPath "HubShell.exe"
if (-not (Test-Path -LiteralPath $sourceExecutable -PathType Leaf)) {
    throw "В каталоге публикации не найден HubShell.exe: $resolvedPublishPath"
}

if ($RegisterRecoveryTask -and -not $NoStartup) {
    throw "Выберите один механизм запуска: обычный HKCU Run или -RegisterRecoveryTask с -NoStartup."
}

$resolvedInstallPath = [System.IO.Path]::GetFullPath($InstallPath)
New-Item -ItemType Directory -Path $resolvedInstallPath -Force | Out-Null
Copy-Item -Path (Join-Path $resolvedPublishPath "*") -Destination $resolvedInstallPath -Recurse -Force
$installedExecutable = Join-Path $resolvedInstallPath "HubShell.exe"
Set-Content -LiteralPath (Join-Path $resolvedInstallPath ".gameclub-installation") -Value "HubShell" -Encoding UTF8

if (-not $NoStartup) {
    $runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
    Remove-ItemProperty -Path $runKey -Name "GameClub.Client.Windows" -ErrorAction SilentlyContinue
    New-Item -Path $runKey -Force | Out-Null
    Set-ItemProperty -Path $runKey -Name "HubShell" -Value ('"{0}"' -f $installedExecutable)
}

if ($RegisterRecoveryTask) {
    Unregister-ScheduledTask -TaskName "GameClub.Client.Windows.Recovery" -Confirm:$false -ErrorAction SilentlyContinue
    $taskName = "HubShell.Recovery"
    $action = New-ScheduledTaskAction -Execute $installedExecutable
    $trigger = New-ScheduledTaskTrigger -AtLogOn
    $settings = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
}

Write-Host "HubShell установлен: $installedExecutable"
if (-not $NoStartup) {
    Write-Host "Автозапуск зарегистрирован для текущего пользователя."
}
Write-Host "Первая привязка выполняется автоматически по MAC после назначения ПК в админке."
Write-Host "Для полного kiosk-ограничения Windows отдельно используйте Assigned Access или Shell Launcher."
