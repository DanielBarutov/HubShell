[CmdletBinding()]
param(
    [ValidateSet("x86", "x64", "ARM64")]
    [string]$Architecture = "x64",
    [ValidateSet("Debug", "Release")]
    [string]$Configuration = "Release",
    [switch]$SingleFile
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not [System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform(
        [System.Runtime.InteropServices.OSPlatform]::Windows)) {
    throw "Сборка установочного пакета WinUI 3 выполняется только на Windows."
}

$clientRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$publishScript = Join-Path $clientRoot "win-client\scripts\publish-windows.ps1"
$runtime = "win-$($Architecture.ToLowerInvariant())"
$publishPath = Join-Path $clientRoot "win-client\artifacts\publish\$runtime\$Configuration"
$packagePath = Join-Path $clientRoot "win-client\artifacts\installer\$runtime\$Configuration"

$publishArguments = @{
    Architecture = $Architecture
    Configuration = $Configuration
}
if ($SingleFile) {
    $publishArguments.SingleFile = $true
}
& $publishScript @publishArguments

New-Item -ItemType Directory -Path $packagePath -Force | Out-Null
Copy-Item -Path (Join-Path $publishPath "*") -Destination $packagePath -Recurse -Force
Copy-Item -Path (Join-Path $PSScriptRoot "install-windows.ps1") -Destination $packagePath -Force
Copy-Item -Path (Join-Path $PSScriptRoot "uninstall-windows.ps1") -Destination $packagePath -Force
Copy-Item -Path (Join-Path $PSScriptRoot "configure-windows-kiosk.ps1") -Destination $packagePath -Force

Write-Host "Установочный пакет подготовлен: $packagePath"
Write-Host "Запуск установки: .\install-windows.ps1 -DeviceId <id> -DeviceBootstrapToken <token>"
