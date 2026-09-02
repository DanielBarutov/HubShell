[CmdletBinding()]
param(
    [ValidateSet("x86", "x64", "ARM64")]
    [string]$Architecture = "x64",
    [ValidateSet("Debug", "Release")]
    [string]$Configuration = "Release",
    [switch]$SingleFile,
    [string]$OutputPath,
    [ValidateSet("dev", "staging", "production")]
    [string]$EnvironmentName = "production",
    [string]$AuthAddress = "https://api.gameclub.local:8100",
    [string]$GrpcAddress = "https://api.gameclub.local:51051"
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
$projectPath = Join-Path $clientRoot "win-client\src\GameClub.Client\GameClub.Client.csproj"
$runtime = "win-$($Architecture.ToLowerInvariant())"
$outputPath = if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    Join-Path $clientRoot "win-client\artifacts\publish\$runtime\$Configuration"
}
elseif ([System.IO.Path]::IsPathRooted($OutputPath)) {
    $OutputPath
}
else {
    Join-Path $clientRoot $OutputPath
}
New-Item -ItemType Directory -Path $outputPath -Force | Out-Null
$singleFileValue = $SingleFile.IsPresent.ToString().ToLowerInvariant()

Write-Host "Публикация GameClub Client: $runtime / $Configuration"
Write-Host "Каталог результата: $outputPath"

& $dotnetCommand.Source publish $projectPath --configuration $Configuration --runtime $runtime --self-contained true --output $outputPath -p:Platform=$Architecture -p:WindowsPackageType=None -p:WindowsAppSDKSelfContained=true -p:SelfContained=true -p:GameClubEnvironment=$EnvironmentName -p:GameClubAuthAddress=$AuthAddress -p:GameClubGrpcAddress=$GrpcAddress -p:IncludeAllContentForSelfExtract=$singleFileValue -p:IncludeNativeLibrariesForSelfExtract=$singleFileValue -p:EnableCompressionInSingleFile=$singleFileValue -p:PublishTrimmed=false `
    -p:PublishSingleFile=$singleFileValue
if ($LASTEXITCODE -ne 0) {
    throw "dotnet publish завершился с кодом $LASTEXITCODE."
}

$executablePath = Join-Path $outputPath "GameClub.Client.exe"
if (-not (Test-Path -LiteralPath $executablePath -PathType Leaf)) {
    throw "Публикация завершилась без ожидаемого файла $executablePath."
}

Write-Host "Готово: $executablePath"
if ($SingleFile) {
    Write-Host "Включён single-file режим. Перед эксплуатацией проверьте запуск на чистой Windows-машине."
}
else {
    Write-Host "Это self-contained каталог: EXE поставляется вместе с WinUI/.NET зависимостями."
}
