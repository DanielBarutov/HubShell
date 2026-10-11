[CmdletBinding(SupportsShouldProcess, ConfirmImpact = "High")]
param(
    [string]$InstallPath = (Join-Path ([Environment]::GetFolderPath("LocalApplicationData")) "GameClub\Client"),
    [switch]$RemoveRuntimeData,
    [switch]$ConfirmRemoval,
    [switch]$RemoveWatchdogService
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not [System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform(
        [System.Runtime.InteropServices.OSPlatform]::Windows)) {
    throw "Удаление Avalonia Windows-клиента выполняется только на Windows."
}

if (-not $ConfirmRemoval) {
    throw "Удаление требует явного параметра -ConfirmRemoval."
}

if ($RemoveWatchdogService -and -not $PSBoundParameters.ContainsKey("InstallPath")) {
    $InstallPath = Join-Path ([Environment]::GetFolderPath("ProgramFiles")) "GameClub\Client"
}

$resolvedInstallPath = [System.IO.Path]::GetFullPath($InstallPath)
$defaultInstallPath = [System.IO.Path]::GetFullPath((Join-Path (
        [Environment]::GetFolderPath("LocalApplicationData")) "GameClub\Client"))
$markerPath = Join-Path $resolvedInstallPath ".gameclub-installation"
$isDefaultPath = [string]::Equals(
    $resolvedInstallPath.TrimEnd([System.IO.Path]::DirectorySeparatorChar),
    $defaultInstallPath.TrimEnd([System.IO.Path]::DirectorySeparatorChar),
    [System.StringComparison]::OrdinalIgnoreCase)

if (-not $isDefaultPath -and -not (Test-Path -LiteralPath $markerPath -PathType Leaf)) {
    throw "Путь установки не подтверждён marker-файлом: $resolvedInstallPath"
}

if ([string]::Equals(
        $resolvedInstallPath.TrimEnd([System.IO.Path]::DirectorySeparatorChar),
        [System.IO.Path]::GetPathRoot($resolvedInstallPath).TrimEnd([System.IO.Path]::DirectorySeparatorChar),
        [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Нельзя удалять корень диска."
}

$runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$removeMatchingWatchdog = $false
$watchdog = Get-CimInstance -ClassName Win32_Service -Filter "Name='HubShell.Watchdog'"
if ($null -ne $watchdog) {
    $expectedCommand = '"{0}" --watchdog-service' -f (Join-Path $resolvedInstallPath "HubShell.exe")
    if ([string]::Equals($watchdog.PathName, $expectedCommand, [StringComparison]::OrdinalIgnoreCase)) {
        if (-not $RemoveWatchdogService) { throw "Для этой установки требуется -RemoveWatchdogService." }
        $removeMatchingWatchdog = $true
    }
    elseif ($RemoveWatchdogService) {
        throw "Служба относится к другому каталогу; удаление остановлено."
    }
}

$removed = $false
if ($PSCmdlet.ShouldProcess($resolvedInstallPath, "удалить установку HubShell")) {
    Remove-ItemProperty -Path $runKey -Name "GameClub.Client.Windows" -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName "GameClub.Client.Windows.Recovery" -Confirm:$false -ErrorAction SilentlyContinue
    Remove-ItemProperty -Path $runKey -Name "HubShell" -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName "HubShell.Recovery" -Confirm:$false -ErrorAction SilentlyContinue

    if ($removeMatchingWatchdog) {
        Stop-Service -Name "HubShell.Watchdog" -ErrorAction Stop
        & sc.exe delete "HubShell.Watchdog"
        if ($LASTEXITCODE -ne 0) { throw "Не удалось удалить службу watchdog." }
    }

    if (Test-Path -LiteralPath $resolvedInstallPath) {
        Remove-Item -LiteralPath $resolvedInstallPath -Recurse -Force
    }

    if ($RemoveRuntimeData) {
        $runtimeRoot = Join-Path ([Environment]::GetFolderPath("LocalApplicationData")) "GameClub"
        foreach ($runtimeFile in @(
                "offline-journal.jsonl",
                "offline-journal.jsonl.sequence",
                "startup.log")) {
            $runtimePath = Join-Path $runtimeRoot $runtimeFile
            if (Test-Path -LiteralPath $runtimePath -PathType Leaf) {
                Remove-Item -LiteralPath $runtimePath -Force
            }
        }
    }
    $removed = $true
}

if (-not $removed) {
    Write-Host "Удаление отменено: $resolvedInstallPath"
    exit 0
}

Write-Host "HubShell удален из $resolvedInstallPath"
if ($RemoveRuntimeData) {
    Write-Host "Runtime offline data и startup.log удалены явно по параметру -RemoveRuntimeData."
}
else {
    Write-Host "Offline journal и startup.log сохранены. Для их удаления повторите с -RemoveRuntimeData."
}
