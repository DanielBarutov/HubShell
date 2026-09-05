[CmdletBinding(SupportsShouldProcess, ConfirmImpact = "High")]
param(
    [string]$InstallPath = (Join-Path ([Environment]::GetFolderPath("LocalApplicationData")) "GameClub\Client"),
    [switch]$RemoveRuntimeData,
    [switch]$ConfirmRemoval
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not [System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform(
        [System.Runtime.InteropServices.OSPlatform]::Windows)) {
    throw "Удаление WinUI-клиента выполняется только на Windows."
}

if (-not $ConfirmRemoval) {
    throw "Удаление требует явного параметра -ConfirmRemoval."
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
$removed = $false
if ($PSCmdlet.ShouldProcess($resolvedInstallPath, "удалить установку GameClub Client")) {
    Remove-ItemProperty -Path $runKey -Name "GameClub.Client" -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName "GameClub.Client.Recovery" -Confirm:$false -ErrorAction SilentlyContinue

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

Write-Host "GameClub Client удален из $resolvedInstallPath"
if ($RemoveRuntimeData) {
    Write-Host "Runtime offline data и startup.log удалены явно по параметру -RemoveRuntimeData."
}
else {
    Write-Host "Offline journal и startup.log сохранены. Для их удаления повторите с -RemoveRuntimeData."
}
