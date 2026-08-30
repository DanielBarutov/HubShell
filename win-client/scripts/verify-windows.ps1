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

& $dotnetCommand.Source restore $solutionPath.Path
if ($LASTEXITCODE -ne 0) {
    throw "dotnet restore завершился с кодом $LASTEXITCODE."
}

& $dotnetCommand.Source build $solutionPath.Path `
    --configuration $Configuration `
    -p:Platform=$Architecture `
    --no-restore
if ($LASTEXITCODE -ne 0) {
    throw "dotnet build завершился с кодом $LASTEXITCODE."
}

& $dotnetCommand.Source test $solutionPath.Path `
    --configuration $Configuration `
    -p:Platform=$Architecture `
    --no-restore
if ($LASTEXITCODE -ne 0) {
    throw "dotnet test завершился с кодом $LASTEXITCODE."
}

Write-Host "Native build пройден. Далее выполните ручные проверки под обычным пользователем:"
@(
    "1. Запустить клиент без прав администратора и проверить компактный виджет.",
    "2. Переключить compact/full-window режим и убедиться, что контекст сохраняется.",
    "3. Применить theme.apply для VIP и обычной группы ПК; проверить safe default.",
    "4. Остановить и восстановить backend или сеть; дождаться reconnect и heartbeat.",
    "5. Перезапустить клиент; убедиться, что он стартует Locked без рабочих данных.",
    "6. Проверить отдельный manager password, maintenance и idle relock.",
    "7. Проверить device stream, ACK и отсутствие повторного локального side effect.",
    "8. В Assigned Access/Shell Launcher проверить запрет выхода в desktop и shell."
) | ForEach-Object { Write-Host $_ }
