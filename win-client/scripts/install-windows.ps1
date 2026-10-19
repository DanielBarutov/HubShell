[CmdletBinding()]
param(
    [string]$PublishPath = $PSScriptRoot,
    [string]$InstallPath = (Join-Path ([Environment]::GetFolderPath("LocalApplicationData")) "GameClub\Client"),
    [switch]$NoStartup,
    [switch]$RegisterRecoveryTask,
    [switch]$RegisterWatchdogService,
    [string]$UpdaterEnrollmentFile,
    [string]$UpdateBackendAddress,
    [string]$UpdatePublicKeyPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$provisionUpdater = -not [string]::IsNullOrWhiteSpace($UpdaterEnrollmentFile) -or
    -not [string]::IsNullOrWhiteSpace($UpdateBackendAddress) -or
    -not [string]::IsNullOrWhiteSpace($UpdatePublicKeyPath)
if ($provisionUpdater) {
    if (-not $RegisterWatchdogService -or [string]::IsNullOrWhiteSpace($UpdaterEnrollmentFile) -or
        [string]::IsNullOrWhiteSpace($UpdateBackendAddress) -or [string]::IsNullOrWhiteSpace($UpdatePublicKeyPath)) {
        throw "Для настройки обновлений укажите службу, enrollment JSON, HTTP-адрес backend и публичный ключ."
    }
    foreach ($name in @("UpdaterEnrollmentFile", "UpdatePublicKeyPath")) {
        $value = Get-Variable -Name $name -ValueOnly
        if (-not [IO.Path]::IsPathRooted($value)) { $value = Join-Path $PSScriptRoot $value }
        Set-Variable -Name $name -Value (Resolve-Path -LiteralPath $value -ErrorAction Stop).Path
    }
}

if (-not [System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform(
        [System.Runtime.InteropServices.OSPlatform]::Windows)) {
    throw "Установка Avalonia Windows-клиента выполняется только на Windows."
}

if ($RegisterWatchdogService) {
    if ($RegisterRecoveryTask) { throw "Watchdog и recovery task нельзя устанавливать вместе." }
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "Установка службы требует запуска PowerShell от администратора."
    }
    $programFilesRoot = [Environment]::GetFolderPath("ProgramFiles")
    if (-not $PSBoundParameters.ContainsKey("InstallPath")) {
        $InstallPath = Join-Path $programFilesRoot "GameClub\Client"
    }
    $portablePath = [string]::Equals([IO.Path]::GetFullPath($InstallPath).TrimEnd('\'),
        "C:\GameClub", [StringComparison]::OrdinalIgnoreCase)
    if (-not $portablePath -and -not ([IO.Path]::GetFullPath($InstallPath)).StartsWith(
            $programFilesRoot.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "SYSTEM-службу устанавливайте внутри Program Files или в C:\GameClub."
    }
    if (Get-Process -Name HubShell -ErrorAction SilentlyContinue | Where-Object { $_.SessionId -ne 0 }) {
        throw "Перед установкой службы завершите игровые сессии и остановите открытый клиент."
    }
    $NoStartup = $true
}

$resolvedPublishPath = (Resolve-Path -LiteralPath $PublishPath -ErrorAction Stop).Path
$sourceExecutable = Join-Path $resolvedPublishPath "HubShell.exe"
if (-not (Test-Path -LiteralPath $sourceExecutable -PathType Leaf)) {
    throw "В каталоге публикации не найден HubShell.exe: $resolvedPublishPath"
}

if ($RegisterWatchdogService -and -not (Test-Path -LiteralPath (
        Join-Path $resolvedPublishPath "HubShell.Watchdog.exe") -PathType Leaf)) {
    throw "Не найден HubShell.Watchdog.exe. Используйте полную новую поставку службы."
}

if ($RegisterRecoveryTask -and -not $NoStartup) {
    throw "Выберите один механизм запуска: обычный HKCU Run или -RegisterRecoveryTask с -NoStartup."
}

$resolvedInstallPath = [System.IO.Path]::GetFullPath($InstallPath)
if ($RegisterWatchdogService -and (Test-Path -LiteralPath $resolvedInstallPath)) {
    if (Get-ChildItem -LiteralPath $resolvedInstallPath -Recurse -Force | Where-Object {
            $_.Attributes -band [IO.FileAttributes]::ReparsePoint }) {
        throw "Каталог службы не должен содержать ссылки/reparse points."
    }
    if ((Get-Item -LiteralPath $resolvedInstallPath -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw "Каталог службы не должен быть ссылкой/reparse point."
    }
}
if ($RegisterWatchdogService -and (Get-Service -Name "HubShell.Watchdog" -ErrorAction SilentlyContinue)) {
    $existingService = Get-CimInstance -ClassName Win32_Service -Filter "Name='HubShell.Watchdog'"
    if ($existingService.StartName -ne "LocalSystem") {
        throw "Watchdog должен работать от LocalSystem. Исправьте существующую службу перед установкой."
    }
    $legacyCommand = '"{0}" --watchdog-service' -f (Join-Path $resolvedInstallPath "HubShell.exe")
    $serviceCommand = '"{0}"' -f (Join-Path $resolvedInstallPath "HubShell.Watchdog.exe")
    if (-not [string]::Equals($existingService.PathName, $legacyCommand, [StringComparison]::OrdinalIgnoreCase) -and
        -not [string]::Equals($existingService.PathName, $serviceCommand, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Служба HubShell.Watchdog уже зарегистрирована для другой папки. Сначала удалите прежнюю установку."
    }
    Stop-Service -Name "HubShell.Watchdog" -ErrorAction Stop
}
New-Item -ItemType Directory -Path $resolvedInstallPath -Force | Out-Null
if (-not [string]::Equals($resolvedPublishPath.TrimEnd('\'), $resolvedInstallPath.TrimEnd('\'),
        [StringComparison]::OrdinalIgnoreCase)) {
    Copy-Item -Path (Join-Path $resolvedPublishPath "*") -Destination $resolvedInstallPath -Recurse -Force
}
if ($RegisterWatchdogService) {
    & icacls.exe $resolvedInstallPath /reset /Q
    if ($LASTEXITCODE -ne 0) { throw "Не удалось сбросить ACL каталога службы." }
    & icacls.exe $resolvedInstallPath /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' '*S-1-5-32-545:(OI)(CI)RX'
    if ($LASTEXITCODE -ne 0) { throw "Не удалось защитить каталог службы." }
    # Machine DPAPI requires the credential file to remain unreadable by ordinary users.
    foreach ($item in Get-ChildItem -LiteralPath $resolvedInstallPath -Recurse -Force) {
        if ($item.FullName -eq (Join-Path $resolvedInstallPath ".client-updater.json")) { continue }
        & icacls.exe $item.FullName /reset /Q
        if ($LASTEXITCODE -ne 0) { throw "Не удалось сбросить ACL файла службы." }
    }
    & icacls.exe $resolvedInstallPath /setowner '*S-1-5-32-544' /T /Q
    if ($LASTEXITCODE -ne 0) { throw "Не удалось назначить владельца каталога службы." }
}
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

if ($RegisterWatchdogService) {
    $serviceName = "HubShell.Watchdog"
    $watchdogExecutable = Join-Path $resolvedInstallPath "HubShell.Watchdog.exe"
    $serviceCommand = '"{0}"' -f $watchdogExecutable
    if ($provisionUpdater) {
        & $watchdogExecutable --configure-updater $UpdaterEnrollmentFile $UpdateBackendAddress $UpdatePublicKeyPath
        if ($LASTEXITCODE -ne 0) { throw "Не удалось сохранить защищённые настройки обновления." }
    }
    elseif (Test-Path -LiteralPath (Join-Path $resolvedInstallPath ".client-updater.json")) {
        & $watchdogExecutable --validate-updater-config
        if ($LASTEXITCODE -ne 0) { throw "Настройки обновления не прошли проверку. Служба оставлена остановленной." }
    }
    if (Get-Service -Name $serviceName -ErrorAction SilentlyContinue) {
        & sc.exe config $serviceName binPath= $serviceCommand start= auto
        if ($LASTEXITCODE -ne 0) { throw "Не удалось обновить службу watchdog." }
    }
    else {
        New-Service -Name $serviceName -BinaryPathName $serviceCommand -StartupType Automatic `
            -DisplayName "HubShell Client Watchdog" -Description "Восстанавливает клиент в существующей пользовательской сессии." | Out-Null
    }
    & sc.exe failure $serviceName reset= 86400 actions= restart/5000/restart/15000/restart/60000
    if ($LASTEXITCODE -ne 0) { throw "Не удалось настроить восстановление службы." }
    Remove-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name "HubShell" -ErrorAction SilentlyContinue
    Remove-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name "GameClub.Client.Windows" -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName "HubShell.Recovery" -Confirm:$false -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName "GameClub.Client.Windows.Recovery" -Confirm:$false -ErrorAction SilentlyContinue
    Start-Service -Name $serviceName
    Write-Host "Служба восстановления установлена. Учётная запись пользователя и политики Windows не изменены."
}

Write-Host "HubShell установлен: $installedExecutable"
if (-not $NoStartup) {
    Write-Host "Автозапуск зарегистрирован для текущего пользователя."
}
Write-Host "Первая привязка выполняется автоматически по MAC после назначения ПК в админке."
Write-Host "Клиент не блокирует Ctrl+Alt+Del и не заменяет системные ограничения Windows."
