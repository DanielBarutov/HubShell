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
    throw "Этот скрипт предназначен для Windows: WinUI 3 и Windows App SDK нельзя проверить в Linux."
}

$dotnetCommand = Get-Command dotnet -ErrorAction SilentlyContinue
if ($null -eq $dotnetCommand) {
    throw "Команда dotnet не найдена. Установите .NET 8 SDK и Visual Studio workload .NET desktop development."
}

$solutionPath = Resolve-Path (Join-Path $PSScriptRoot "..\GameClub.Client.sln")

Write-Host "Проверяем Windows client: $solutionPath"
& $dotnetCommand.Source --info
if ($LASTEXITCODE -ne 0) {
    throw "dotnet --info завершился с кодом $LASTEXITCODE."
}

& $dotnetCommand.Source restore $solutionPath.Path `
    -p:UseWPF=false `
    -p:UseWindowsForms=false
if ($LASTEXITCODE -ne 0) {
    throw "dotnet restore завершился с кодом $LASTEXITCODE."
}

& $dotnetCommand.Source build $solutionPath.Path `
    --configuration $Configuration `
    -p:Platform=$Architecture `
    -p:UseWPF=false `
    -p:UseWindowsForms=false `
    --no-restore
if ($LASTEXITCODE -ne 0) {
    throw "dotnet build завершился с кодом $LASTEXITCODE."
}

& $dotnetCommand.Source test $solutionPath.Path `
    --configuration $Configuration `
    -p:Platform=$Architecture `
    -p:UseWPF=false `
    -p:UseWindowsForms=false `
    --no-restore
if ($LASTEXITCODE -ne 0) {
    throw "dotnet test завершился с кодом $LASTEXITCODE."
}

Write-Host "Native build пройден. Далее выполните ручные проверки под обычным пользователем:"
Write-Host "1. Запустить клиент обычным пользователем, без прав администратора: он должен стартовать Locked в полноэкранном borderless shell."
Write-Host "2. До назначения MAC проверить pending/waiting screen без user profile, баланса и рабочих действий."
Write-Host "3. Назначить MAC в админке, дождаться approved, heartbeat, device policy и theme."
Write-Host "4. Зарегистрировать пользователя, выполнить login/logout и проверить только его баланс и историю."
Write-Host "5. Остановить и восстановить backend или сеть; дождаться reconnect и heartbeat без ручного token setup."
Write-Host "6. Перезапустить клиент; убедиться, что он снова стартует Locked и сохраняет только installation identity."
Write-Host "7. Проверить отдельный manager password через Ctrl+Alt+P и возврат из maintenance в Locked."
Write-Host "8. Проверить session/product retry и отсутствие повторного debit, sale или active session."
Write-Host "9. В Assigned Access/Shell Launcher проверить запрет выхода в desktop и shell."
