[CmdletBinding()]
param(
    [string]$InstallPath = (Join-Path ([Environment]::GetFolderPath("ProgramFiles")) "GameClub\Client"),
    [switch]$KeepUserEnvironment
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

if (-not $KeepUserEnvironment) {
    @(
        "GAMECLUB_ENVIRONMENT",
        "GAMECLUB_DEVICE_ID",
        "GAMECLUB_DEVICE_BOOTSTRAP_TOKEN",
        "GAMECLUB_AUTH_ADDRESS",
        "GAMECLUB_GRPC_ADDRESS",
        "GAMECLUB_MANAGER_PASSWORD_HASH",
        "GAMECLUB_CLIENT_ACCESS_PIN_HASH"
    ) | ForEach-Object {
        [Environment]::SetEnvironmentVariable($_, $null, "User")
    }
}

if (Test-Path -LiteralPath $InstallPath) {
    Remove-Item -LiteralPath $InstallPath -Recurse -Force
}
Write-Host "GameClub Client удален из $InstallPath"
