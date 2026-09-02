[CmdletBinding()]
param(
    [string]$InstallPath = (Join-Path ([Environment]::GetFolderPath("LocalApplicationData")) "GameClub\Client")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not [System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform(
        [System.Runtime.InteropServices.OSPlatform]::Windows)) {
    throw "Удаление WinUI-клиента выполняется только на Windows."
}

$runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
Remove-ItemProperty -Path $runKey -Name "GameClub.Client" -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName "GameClub.Client.Recovery" -Confirm:$false -ErrorAction SilentlyContinue

if (Test-Path -LiteralPath $InstallPath) {
    Remove-Item -LiteralPath $InstallPath -Recurse -Force
}
Write-Host "GameClub Client удален из $InstallPath"
