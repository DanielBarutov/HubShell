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
if ([string]::IsNullOrWhiteSpace($AuthAddress) -or [string]::IsNullOrWhiteSpace($GrpcAddress)) {
    throw "Для publish нужно явно указать -AuthAddress и -GrpcAddress."
}

function Test-PrivateNetworkEndpoint {
    param(
        [Parameter(Mandatory = $true)]
        [Uri]$Uri
    )

    if ($Uri.IsLoopback) {
        return $true
    }

    $address = $null
    if (-not [System.Net.IPAddress]::TryParse($Uri.Host, [ref]$address)) {
        return $false
    }
    if ($address.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork) {
        return $false
    }

    $bytes = $address.GetAddressBytes()
    return $bytes[0] -eq 10 -or
        ($bytes[0] -eq 172 -and $bytes[1] -ge 16 -and $bytes[1] -le 31) -or
        ($bytes[0] -eq 192 -and $bytes[1] -eq 168)
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
    if ($uri.Scheme -eq "http" -and -not (Test-PrivateNetworkEndpoint -Uri $uri)) {
        throw "$($endpoint.Name) для HTTP должен указывать loopback или приватную LAN IPv4-сеть (10/8, 172.16/12, 192.168/16). Для внешнего адреса используйте HTTPS."
    }
    $isPlaceholderHost = $uri.Host -in @("api.gameclub.local") `
        -or $uri.Host -match "(^|[.])example([.]|$)"
    if ($EnvironmentName -eq "production" -and $isPlaceholderHost) {
        throw "$($endpoint.Name) для production должен быть реальным адресом backend, а не placeholder hostname."
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
