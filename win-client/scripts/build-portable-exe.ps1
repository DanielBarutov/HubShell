[CmdletBinding()]
param(
    [ValidateSet("x86", "x64", "ARM64")]
    [string]$Architecture = "x64",
    [ValidateSet("Debug", "Release")]
    [string]$Configuration = "Release",
    [ValidateSet("dev", "staging", "production")]
    [string]$EnvironmentName = "production",
    [string]$AuthAddress,
    [string]$GrpcAddress
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$windows = [System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform(
    [System.Runtime.InteropServices.OSPlatform]::Windows
)
if (-not $windows) {
    throw "Публикация WinUI 3 выполняется на Windows с установленным .NET 8 SDK и Windows SDK."
}

$dotnetCommand = Get-Command dotnet -ErrorAction SilentlyContinue
if ($null -eq $dotnetCommand) {
    throw "Команда dotnet не найдена. Установите .NET 8 SDK и workload .NET desktop development."
}

$clientRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$publishScript = Join-Path $clientRoot "win-client\scripts\publish-windows.ps1"
$runtime = "win-$($Architecture.ToLowerInvariant())"
$distributionPath = Join-Path $clientRoot "win-client\artifacts\portable\$runtime\$Configuration"
$temporaryPath = Join-Path ([System.IO.Path]::GetTempPath()) ("gameclub-client-publish-" + [Guid]::NewGuid().ToString("N"))

if (-not (Test-Path -LiteralPath $distributionPath)) {
    New-Item -ItemType Directory -Path $distributionPath -Force | Out-Null
}

try {
    & $publishScript -Architecture $Architecture -Configuration $Configuration -OutputPath $temporaryPath -SingleFile `
        -EnvironmentName $EnvironmentName -AuthAddress $AuthAddress -GrpcAddress $GrpcAddress
    if ($LASTEXITCODE -ne 0) {
        throw "Публикация portable EXE завершилась с кодом $LASTEXITCODE."
    }

    $sourceExecutable = Join-Path $temporaryPath "GameClub.Client.exe"
    if (-not (Test-Path -LiteralPath $sourceExecutable -PathType Leaf)) {
        throw "В результате publish не найден GameClub.Client.exe: $temporaryPath"
    }

    $targetExecutable = Join-Path $distributionPath "GameClub.Client.exe"
    $stagedExecutable = Join-Path $distributionPath (
        ".GameClub.Client.exe." + [Guid]::NewGuid().ToString("N") + ".new")
    Copy-Item -LiteralPath $sourceExecutable -Destination $stagedExecutable -Force
    $hash = (Get-FileHash -LiteralPath $stagedExecutable -Algorithm SHA256).Hash
    Move-Item -LiteralPath $stagedExecutable -Destination $targetExecutable -Force
    Get-ChildItem -LiteralPath $distributionPath -Force |
        Where-Object { $_.FullName -ne $targetExecutable } |
        Remove-Item -Recurse -Force

    Write-Host "Готово. Один переносимый файл:"
    Write-Host $targetExecutable
    Write-Host "SHA-256: $hash"
    Write-Host "На клиентском ПК не нужны Visual Studio, .NET SDK или Windows App SDK."
    Write-Host "На игровом ПК не нужны env-переменные: клиент сам запросит привязку по MAC."
}
finally {
    if (Test-Path -LiteralPath $temporaryPath) {
        Remove-Item -LiteralPath $temporaryPath -Recurse -Force
    }
}
