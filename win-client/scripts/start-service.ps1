[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$installPath = [IO.Path]::GetFullPath($PSScriptRoot).TrimEnd('\')
if (-not [string]::Equals($installPath, "C:\GameClub", [StringComparison]::OrdinalIgnoreCase)) {
    throw "Сначала скопируйте содержимое release в C:\GameClub."
}
if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot "server.ini") -PathType Leaf)) {
    throw "Не найден server.ini. Укажите адрес сервера перед запуском службы."
}
$grpcLine = @(Get-Content -LiteralPath (Join-Path $PSScriptRoot "server.ini") |
    Where-Object { $_ -match '^\s*GrpcAddress\s*=' })
if ($grpcLine.Count -ne 1 -or [string]::IsNullOrWhiteSpace(($grpcLine[0] -split '=', 2)[1])) {
    throw "Заполните GrpcAddress в server.ini перед установкой службы."
}
& (Join-Path $PSScriptRoot "install-windows.ps1") -PublishPath $PSScriptRoot `
    -InstallPath $PSScriptRoot -RegisterWatchdogService
