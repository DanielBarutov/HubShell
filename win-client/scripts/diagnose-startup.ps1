[CmdletBinding()]
param(
    [string]$ExecutablePath = "C:\Git\HubShell\win-client\artifacts\publish\win-x64\Debug\GameClub.Client.exe",
    [string]$OutputPath = (Join-Path $PSScriptRoot "..\artifacts\diagnostics"),
    [ValidateRange(1, 300)]
    [int]$TimeoutSeconds = 30
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not [System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform(
        [System.Runtime.InteropServices.OSPlatform]::Windows)) {
    throw "Диагностика запуска WinUI-клиента выполняется только на Windows."
}

$resolvedExecutablePath = [System.IO.Path]::GetFullPath($ExecutablePath)
if (-not (Test-Path -LiteralPath $resolvedExecutablePath -PathType Leaf)) {
    throw "EXE не найден: $resolvedExecutablePath"
}

$processName = [System.IO.Path]::GetFileName($resolvedExecutablePath)
$resolvedOutputPath = [System.IO.Path]::GetFullPath($OutputPath)
$runId = Get-Date -Format "yyyyMMdd-HHmmss-fff"
$reportDirectory = Join-Path $resolvedOutputPath $runId
New-Item -ItemType Directory -Path $reportDirectory -Force | Out-Null
$reportPath = Join-Path $reportDirectory "startup-report.txt"
$startupLogPath = Join-Path ([Environment]::GetFolderPath("LocalApplicationData")) "GameClub\startup.log"
$startedAt = Get-Date
$process = $null
$waitCompleted = $false
$exitCode = $null
$startError = $null
$eventReadError = $null
$events = @()
$startupLogLines = @()
$startupLogReadError = $null
$processArchitecture = if ([Environment]::Is64BitProcess) { "x64" } else { "x86" }
$osArchitecture = if ([Environment]::Is64BitOperatingSystem) { "x64" } else { "x86" }
$diagnosticSessionId = [System.Diagnostics.Process]::GetCurrentProcess().SessionId
$interactiveDesktop = $diagnosticSessionId -ne 0

try {
    $workingDirectory = Split-Path -Parent $resolvedExecutablePath
    $process = Start-Process `
        -FilePath $resolvedExecutablePath `
        -WorkingDirectory $workingDirectory `
        -PassThru
    $waitCompleted = $process.WaitForExit($TimeoutSeconds * 1000)
    if ($waitCompleted) {
        $process.Refresh()
        $exitCode = $process.ExitCode
    }
}
catch {
    $startError = $_.Exception.ToString()
}

try {
    $events = @(
        Get-WinEvent -FilterHashtable @{
            LogName = "Application"
            StartTime = $startedAt.AddSeconds(-2)
        } -ErrorAction Stop |
        Where-Object {
            $_.ProviderName -in ".NET Runtime", "Application Error", "Windows Error Reporting" `
                -and $_.Message -match [Regex]::Escape($processName)
        } |
        Select-Object TimeCreated, ProviderName, Id, LevelDisplayName, Message
    )
}
catch {
    $eventReadError = $_.Exception.ToString()
}

try {
    if (Test-Path -LiteralPath $startupLogPath -PathType Leaf) {
        $startupLogLines = @(Get-Content -LiteralPath $startupLogPath -Tail 100 -ErrorAction Stop)
    }
}
catch {
    $startupLogReadError = $_.Exception.ToString()
}

$lines = [System.Collections.Generic.List[string]]::new()
$lines.Add("GameClub Client startup diagnostic")
$lines.Add("StartedAt: $($startedAt.ToString('o'))")
$lines.Add("ExecutablePath: $resolvedExecutablePath")
$lines.Add("ExecutableSHA256: $((Get-FileHash -LiteralPath $resolvedExecutablePath -Algorithm SHA256).Hash)")
$lines.Add("FileVersion: $((Get-Item -LiteralPath $resolvedExecutablePath).VersionInfo.FileVersion)")
$lines.Add("WorkingDirectory: $(Split-Path -Parent $resolvedExecutablePath)")
$lines.Add("OS: $([Environment]::OSVersion.VersionString)")
$lines.Add("ProcessArchitecture: $processArchitecture")
$lines.Add("OSArchitecture: $osArchitecture")
$lines.Add("DiagnosticSessionId: $diagnosticSessionId")
$lines.Add("InteractiveDesktop: $interactiveDesktop")
if (-not $interactiveDesktop) {
    $lines.Add("Warning: WinUI GUI must be launched from the interactive Windows desktop. Session 0 (for example SSH) is not a valid GUI runtime test.")
}
$lines.Add("TimeoutSeconds: $TimeoutSeconds")
$lines.Add("StartupLogPath: $startupLogPath")

if ($null -ne $process) {
    $lines.Add("PID: $($process.Id)")
    $lines.Add("ExitedWithinTimeout: $waitCompleted")
}
else {
    $lines.Add("PID: not-started")
}

if ($null -ne $exitCode) {
    $lines.Add("ExitCode: $exitCode")
}
if ($null -ne $startError) {
    $lines.Add("StartError:")
    $lines.Add($startError)
}
if ($null -ne $eventReadError) {
    $lines.Add("EventLogReadError:")
    $lines.Add($eventReadError)
}
if ($null -ne $startupLogReadError) {
    $lines.Add("StartupLogReadError:")
    $lines.Add($startupLogReadError)
}

$lines.Add("ApplicationEvents: $($events.Count)")
foreach ($event in $events) {
    $lines.Add("")
    $lines.Add("[$($event.TimeCreated)] $($event.ProviderName) / Id=$($event.Id) / Level=$($event.LevelDisplayName)")
    $lines.Add([string]$event.Message)
}

$lines.Add("")
$lines.Add("ApplicationStartupLogTail: $($startupLogLines.Count) lines")
foreach ($startupLogLine in $startupLogLines) {
    $lines.Add([string]$startupLogLine)
}

Set-Content -LiteralPath $reportPath -Value $lines -Encoding UTF8

Write-Host "Startup diagnostic report: $reportPath"
if (-not $interactiveDesktop) {
    Write-Host "ВНИМАНИЕ: текущая Windows-сессия $diagnosticSessionId не является интерактивным desktop-сеансом. Для WinUI запускайте EXE из Session 1/RDP; результат SSH-запуска нельзя считать проверкой окна."
}
if ($null -ne $startError) {
    Write-Host "EXE не удалось запустить. Подробность сохранена в отчёте."
    exit 2
}
if ($waitCompleted) {
    Write-Host "EXE завершился с кодом: $exitCode"
    if ($exitCode -ne 0) {
        exit 1
    }
    exit 0
}

Write-Host "EXE остаётся запущенным после $TimeoutSeconds секунд; PID: $($process.Id)"
exit 0
