[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$ExecutablePath = (Join-Path $PSScriptRoot "GameClub.Client.exe"),
    [string]$KioskUser,
    [string]$OutputPath = (Join-Path $PSScriptRoot "..\artifacts\kiosk\shell-launcher.xml"),
    [string]$BackupPath = (Join-Path $PSScriptRoot "..\artifacts\kiosk\shell-launcher.backup.xml"),
    [switch]$Apply,
    [switch]$Restore,
    [switch]$EnableFeature
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Assert-Windows {
    if (-not [System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform(
            [System.Runtime.InteropServices.OSPlatform]::Windows)) {
        throw "Windows kiosk provisioning выполняется только на Windows."
    }
}

function Assert-Administrator {
    $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [System.Security.Principal.WindowsPrincipal]::new($identity)
    if (-not $principal.IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "Запустите PowerShell от имени администратора."
    }
}

function Assert-SystemContext {
    $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
    if ($identity.User.Value -ne "S-1-5-18") {
        throw "MDM_AssignedAccess нужно применять из SYSTEM-контекста. Используйте Scheduled Task или PsExec -i -s powershell.exe."
    }
}

function Get-AssignedAccessObject {
    $object = Get-CimInstance -Namespace "root\cimv2\mdm\dmmap" -ClassName "MDM_AssignedAccess"
    if ($null -eq $object) {
        throw "Не найден MDM_AssignedAccess. Проверьте редакцию Windows и компоненты Device Lockdown."
    }
    return $object
}

function Get-EncodedShellLauncher([string]$xml) {
    return [System.Net.WebUtility]::HtmlEncode($xml)
}

function Get-ShellLauncherXml([string]$path, [string]$user) {
    $escapedPath = [System.Security.SecurityElement]::Escape($path)
    $escapedUser = [System.Security.SecurityElement]::Escape($user)
    $profileId = "{$([guid]::NewGuid().ToString().ToUpperInvariant())}"

    return @"
<?xml version="1.0" encoding="utf-8"?>
<ShellLauncherConfiguration xmlns="http://schemas.microsoft.com/ShellLauncher/2018/Configuration" xmlns:V2="http://schemas.microsoft.com/ShellLauncher/2019/Configuration">
  <Profiles>
    <DefaultProfile>
      <Shell Shell="%SystemRoot%\explorer.exe" />
    </DefaultProfile>
    <Profile Id="$profileId" Name="GameClub Client">
      <Shell Shell="$escapedPath" V2:AppType="Desktop" V2:AllAppsFullScreen="false">
        <ReturnCodeActions>
          <ReturnCodeAction ReturnCode="0" Action="RestartShell" />
          <ReturnCodeAction ReturnCode="-1" Action="RestartShell" />
        </ReturnCodeActions>
        <DefaultAction Action="RestartShell" />
      </Shell>
    </Profile>
  </Profiles>
  <Configs>
    <Config>
      <Account Name="$escapedUser" />
      <Profile Id="$profileId" />
    </Config>
  </Configs>
</ShellLauncherConfiguration>
"@
}

Assert-Windows

$resolvedOutputPath = [System.IO.Path]::GetFullPath($OutputPath)
$resolvedBackupPath = [System.IO.Path]::GetFullPath($BackupPath)
$resolvedExecutablePath = [System.IO.Path]::GetFullPath($ExecutablePath)

if (-not $Apply) {
    if ($Restore) {
        throw "Для восстановления укажите -Apply -Restore."
    }
    if ([string]::IsNullOrWhiteSpace($KioskUser)) {
        throw "Укажите -KioskUser для preview конфигурации."
    }
    $preview = Get-ShellLauncherXml $resolvedExecutablePath $KioskUser
    New-Item -ItemType Directory -Path (Split-Path -Parent $resolvedOutputPath) -Force | Out-Null
    Set-Content -LiteralPath $resolvedOutputPath -Value $preview -Encoding UTF8
    Write-Host "Preview XML создан: $resolvedOutputPath"
    Write-Host "Для применения повторите команду с -Apply. По умолчанию политика не изменяется."
    return
}

Assert-Administrator
Assert-SystemContext

if ($Restore) {
    if (-not (Test-Path -LiteralPath $resolvedBackupPath -PathType Leaf)) {
        throw "Backup Shell Launcher не найден: $resolvedBackupPath"
    }

    $backupContent = Get-Content -LiteralPath $resolvedBackupPath -Raw
    $assignedAccess = Get-AssignedAccessObject
    if ($backupContent -match "<ShellLauncherConfiguration\b") {
        $assignedAccess.ShellLauncher = Get-EncodedShellLauncher $backupContent
        $restoreMessage = "предыдущая Shell Launcher policy восстановлена"
    }
    else {
        $assignedAccess.ShellLauncher = $null
        $restoreMessage = "предыдущая Shell Launcher policy отсутствовала"
    }

    if ($PSCmdlet.ShouldProcess("MDM_AssignedAccess", "восстановить Shell Launcher")) {
        Set-CimInstance -CimInstance $assignedAccess | Out-Null
        Write-Host "Готово: $restoreMessage. Перезагрузите устройство или выполните новый вход пользователя."
    }
    return
}

$resolvedExecutablePath = (Resolve-Path -LiteralPath $resolvedExecutablePath -ErrorAction Stop).Path
if ([string]::IsNullOrWhiteSpace($KioskUser)) {
    throw "Укажите существующую локальную учётную запись -KioskUser."
}

$osCaption = (Get-CimInstance Win32_OperatingSystem).Caption
if ($osCaption -notmatch "Enterprise|Education|IoT") {
    throw "Shell Launcher требует поддерживаемую редакцию Windows Enterprise/Education/IoT. Определена: $osCaption"
}

if ($EnableFeature) {
    if ($PSCmdlet.ShouldProcess("Windows optional features", "включить Client-DeviceLockdown и Client-EmbeddedShellLauncher")) {
        Enable-WindowsOptionalFeature -Online -FeatureName @(
            "Client-DeviceLockdown",
            "Client-EmbeddedShellLauncher"
        ) -All -NoRestart | Out-Null
    }
}

$assignedAccess = Get-AssignedAccessObject
$existingPolicy = [string]$assignedAccess.ShellLauncher
New-Item -ItemType Directory -Path (Split-Path -Parent $resolvedOutputPath) -Force | Out-Null
New-Item -ItemType Directory -Path (Split-Path -Parent $resolvedBackupPath) -Force | Out-Null
if ([string]::IsNullOrWhiteSpace($existingPolicy)) {
    Set-Content -LiteralPath $resolvedBackupPath -Value "<!-- GameClub: no previous Shell Launcher policy -->" -Encoding UTF8
}
else {
    Set-Content -LiteralPath $resolvedBackupPath -Value $existingPolicy -Encoding UTF8
}

$xml = Get-ShellLauncherXml $resolvedExecutablePath $KioskUser
Set-Content -LiteralPath $resolvedOutputPath -Value $xml -Encoding UTF8

if ($PSCmdlet.ShouldProcess("MDM_AssignedAccess", "применить GameClub Shell Launcher для $KioskUser")) {
    $assignedAccess.ShellLauncher = Get-EncodedShellLauncher $xml
    Set-CimInstance -CimInstance $assignedAccess | Out-Null
    Write-Host "Shell Launcher применён для $KioskUser. Backup: $resolvedBackupPath"
    Write-Host "Изменения вступают в силу после нового входа пользователя; при необходимости перезагрузите ПК."
}
