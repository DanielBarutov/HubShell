[CmdletBinding()]
param(
    [ValidateSet("x86", "x64", "ARM64")]
    [string]$Architecture = "x64",
    [ValidateSet("Debug", "Release")]
    [string]$Configuration = "Release",
    [switch]$SingleFile,
    [string]$OutputPath,
    [switch]$CleanOutput,
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
$projectPath = Join-Path $clientRoot "win-client\src\GameClub.Client\GameClub.Client.csproj"
$runtime = "win-$($Architecture.ToLowerInvariant())"
$isProduction = $EnvironmentName -eq "production"
if ([string]::IsNullOrWhiteSpace($AuthAddress) -or [string]::IsNullOrWhiteSpace($GrpcAddress)) {
    throw "Для publish нужно явно указать -AuthAddress и -GrpcAddress."
}

foreach ($endpoint in @(
        @{ Name = "AuthAddress"; Value = $AuthAddress },
        @{ Name = "GrpcAddress"; Value = $GrpcAddress })) {
    $parsedUri = $null
    if (-not [Uri]::TryCreate($endpoint.Value, [UriKind]::Absolute, [ref]$parsedUri)) {
        throw "$($endpoint.Name) должен быть абсолютным URI."
    }
    $uri = [Uri]$parsedUri
    if ($uri.Scheme -notin @("http", "https")) {
        throw "$($endpoint.Name) должен использовать http или https."
    }
    if ($uri.Scheme -eq "http" -and (
            $EnvironmentName -ne "dev"
            -or -not $uri.IsLoopback)) {
        throw "$($endpoint.Name) должен использовать HTTPS, кроме loopback HTTP в dev."
    }
    if ($isProduction -and (
            $uri.Scheme -ne "https"
            -or $uri.IsLoopback
            -or $uri.Host -in @("api.gameclub.local", "localhost")
            -or $uri.Host -match "(^|[.])example([.]|$)"
            -or $uri.Host -match "[.]local$")) {
        throw "$($endpoint.Name) для production должен быть реальным внешним HTTPS endpoint без placeholder/loopback host."
    }
}

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

if ($CleanOutput) {
    Get-ChildItem -LiteralPath $outputPath -Force |
        Remove-Item -Recurse -Force
}

Write-Host "Публикация GameClub Client: $runtime / $Configuration"
Write-Host "Каталог результата: $outputPath"

& $dotnetCommand.Source publish $projectPath --configuration $Configuration --runtime $runtime --self-contained true --output $outputPath -p:Platform=$Architecture -p:UseWPF=false -p:UseWindowsForms=false -p:WindowsPackageType=None -p:WindowsAppSDKSelfContained=true -p:SelfContained=true -p:GameClubEnvironment=$EnvironmentName -p:GameClubAuthAddress=$AuthAddress -p:GameClubGrpcAddress=$GrpcAddress -p:IncludeAllContentForSelfExtract=$singleFileValue -p:IncludeNativeLibrariesForSelfExtract=$singleFileValue -p:EnableCompressionInSingleFile=$singleFileValue -p:PublishTrimmed=false `
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
