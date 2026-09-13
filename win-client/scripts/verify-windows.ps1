[CmdletBinding()]
param(
    [ValidateSet("x86", "x64", "ARM64")]
    [string]$Architecture = "x64",
    [ValidateSet("Debug", "Release")]
    [string]$Configuration = "Debug"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$windows = [System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform(
    [System.Runtime.InteropServices.OSPlatform]::Windows
)
if (-not $windows) {
    throw "Этот скрипт предназначен для Windows: он собирает Avalonia host перед обязательным интерактивным native smoke."
}

$dotnetCommand = Get-Command dotnet -ErrorAction SilentlyContinue
if ($null -eq $dotnetCommand) {
    throw "Команда dotnet не найдена. Установите .NET 8 SDK."
}

$windowsSolutionPath = Resolve-Path (Join-Path $PSScriptRoot "..\GameClub.Client.Windows.sln")
$linuxFirstSolutionPath = Resolve-Path (Join-Path $PSScriptRoot "..\GameClub.Client.sln")

Write-Host "Проверяем Avalonia Windows host: $windowsSolutionPath"
Write-Host "Проверяем Avalonia/Core test graph: $linuxFirstSolutionPath"
& $dotnetCommand.Source --info
if ($LASTEXITCODE -ne 0) {
    throw "dotnet --info завершился с кодом $LASTEXITCODE."
}

& $dotnetCommand.Source restore $windowsSolutionPath.Path
if ($LASTEXITCODE -ne 0) {
    throw "dotnet restore завершился с кодом $LASTEXITCODE."
}

& $dotnetCommand.Source build $windowsSolutionPath.Path `
    --configuration $Configuration `
    -p:Platform=$Architecture `
    --no-restore
if ($LASTEXITCODE -ne 0) {
    throw "dotnet build завершился с кодом $LASTEXITCODE."
}

& $dotnetCommand.Source restore $linuxFirstSolutionPath.Path
if ($LASTEXITCODE -ne 0) {
    throw "Avalonia/Core restore завершился с кодом $LASTEXITCODE."
}

& $dotnetCommand.Source build $linuxFirstSolutionPath.Path `
    --configuration $Configuration `
    -p:Platform=$Architecture `
    --no-restore
if ($LASTEXITCODE -ne 0) {
    throw "Avalonia/Core build завершился с кодом $LASTEXITCODE."
}

& $dotnetCommand.Source test $linuxFirstSolutionPath.Path `
    --configuration $Configuration `
    -p:Platform=$Architecture `
    --no-restore
if ($LASTEXITCODE -ne 0) {
    throw "Avalonia/Core test завершился с кодом $LASTEXITCODE."
}

Write-Host "Avalonia Windows build и portable Core checks пройдены. Далее выполните native runtime smoke под обычным пользователем:"
Write-Host "1. Запустить клиент обычным пользователем, без прав администратора: он должен стартовать Locked в полноэкранном borderless shell."
Write-Host "2. До назначения MAC проверить pending/waiting screen без user profile, баланса и рабочих действий."
Write-Host "3. Назначить MAC в админке, дождаться approved, heartbeat, device policy и theme."
Write-Host "4. Зарегистрировать пользователя, выполнить login/logout и проверить только его баланс и историю."
Write-Host "5. Остановить и восстановить backend или сеть; дождаться reconnect и heartbeat без ручного token setup."
Write-Host "6. Перезапустить клиент; убедиться, что он снова стартует Locked и сохраняет только installation identity."
Write-Host "7. Открыть режим обслуживания через явный пункт менеджера, ввести manager password и проверить возврат в Locked."
Write-Host "8. Проверить session/product retry и отсутствие повторного debit, sale или active session."
Write-Host "9. После login проверить compact always-on-top widget, Скрыть → tray → Показать и явный выход из tray."
Write-Host "10. В Assigned Access/Shell Launcher проверить запрет выхода в desktop и shell."
