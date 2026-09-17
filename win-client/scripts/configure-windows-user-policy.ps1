[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory = $true)]
    [string]$KioskUser,
    [string]$BackupPath = (Join-Path $PSScriptRoot "..\artifacts\kiosk\user-policy.backup.json"),
    [switch]$Apply,
    [switch]$Restore,
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Assert-Windows {
    if (-not [System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform(
            [System.Runtime.InteropServices.OSPlatform]::Windows)) {
        throw "Windows user policy provisioning выполняется только на Windows."
    }
}

function Assert-Administrator {
    $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [System.Security.Principal.WindowsPrincipal]::new($identity)
    if (-not $principal.IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "Запустите PowerShell от имени администратора."
    }
}

function Get-LocalUserSid([string]$userName) {
    $account = Get-CimInstance Win32_UserAccount |
        Where-Object { $_.LocalAccount -and $_.Name -eq $userName } |
        Select-Object -First 1
    if ($null -eq $account -or [string]::IsNullOrWhiteSpace($account.SID)) {
        throw "Не найдена локальная учётная запись: $userName"
    }
    return [string]$account.SID
}

function Get-UserProfilePath([string]$sid) {
    $profile = Get-CimInstance Win32_UserProfile |
        Where-Object { $_.SID -eq $sid } |
        Select-Object -First 1
    if ($null -eq $profile -or [string]::IsNullOrWhiteSpace($profile.LocalPath)) {
        throw "Для $KioskUser не найден профиль Windows. Один раз войдите этой учётной записью и повторите provisioning."
    }
    return [string]$profile.LocalPath
}

function Open-UserHive([string]$sid, [string]$profilePath) {
    $loadedHivePath = "Registry::HKEY_USERS\$sid"
    if (Test-Path -LiteralPath $loadedHivePath) {
        return [pscustomobject]@{
            MountName = $sid
            MountedByScript = $false
        }
    }

    $ntUserPath = Join-Path $profilePath "NTUSER.DAT"
    if (-not (Test-Path -LiteralPath $ntUserPath -PathType Leaf)) {
        throw "Профиль $profilePath не содержит NTUSER.DAT."
    }

    $mountName = "GameClubPolicy_$([guid]::NewGuid().ToString('N'))"
    & reg.exe load "HKU\$mountName" $ntUserPath | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Не удалось временно подключить пользовательский hive $ntUserPath."
    }

    return [pscustomobject]@{
        MountName = $mountName
        MountedByScript = $true
    }
}

function Close-UserHive($hive) {
    if ($hive.MountedByScript) {
        & reg.exe unload "HKU\$($hive.MountName)" | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "Не удалось отключить временный пользовательский hive HKU\$($hive.MountName)."
        }
    }
}

function Get-PolicyKeyPath([string]$mountName) {
    return "Registry::HKEY_USERS\$mountName\Software\Microsoft\Windows\CurrentVersion\Policies\Explorer"
}

function Get-NoRunState([string]$keyPath) {
    $keyExists = Test-Path -LiteralPath $keyPath
    $valueExists = $false
    $value = $null
    if ($keyExists) {
        $properties = Get-ItemProperty -LiteralPath $keyPath -Name NoRun -ErrorAction SilentlyContinue
        if ($null -ne $properties) {
            $valueExists = $true
            $value = [int]$properties.NoRun
        }
    }

    return [ordered]@{
        KeyExisted = $keyExists
        NoRunExisted = $valueExists
        NoRunValue = $value
    }
}

Assert-Windows
if ($Apply -and $Restore) {
    throw "Нельзя одновременно указывать -Apply и -Restore."
}

$resolvedBackupPath = [System.IO.Path]::GetFullPath($BackupPath)
$sid = Get-LocalUserSid $KioskUser
$previewKeyPath = Get-PolicyKeyPath $sid

if (-not $Apply -and -not $Restore) {
    Write-Host "Пользователь: $KioskUser"
    Write-Host "SID: $sid"
    Write-Host "Policy key: $previewKeyPath"
    Write-Host "Policy: NoRun=1 (убрать Run и запретить Win+R)"
    Write-Host "Backup: $resolvedBackupPath"
    Write-Host "Preview завершён. Для изменения добавьте -Apply."
    return
}

Assert-Administrator
$profilePath = Get-UserProfilePath $sid
$hive = Open-UserHive $sid $profilePath
$policyKeyPath = Get-PolicyKeyPath $hive.MountName

try {
    if ($Restore) {
        if (-not (Test-Path -LiteralPath $resolvedBackupPath -PathType Leaf)) {
            throw "Backup пользовательской policy не найден: $resolvedBackupPath"
        }

        $backup = Get-Content -LiteralPath $resolvedBackupPath -Raw | ConvertFrom-Json
        if ([string]$backup.SID -ne $sid) {
            throw "Backup относится к SID $($backup.SID), а не к $sid."
        }

        if ($PSCmdlet.ShouldProcess($policyKeyPath, "восстановить NoRun для $KioskUser")) {
            if ([bool]$backup.NoRunExisted) {
                New-Item -ItemType Directory -Path $policyKeyPath -Force | Out-Null
                New-ItemProperty -LiteralPath $policyKeyPath -Name NoRun -Value ([int]$backup.NoRunValue) -PropertyType DWord -Force | Out-Null
            }
            else {
                Remove-ItemProperty -LiteralPath $policyKeyPath -Name NoRun -ErrorAction SilentlyContinue
            }
            Write-Host "NoRun восстановлен для $KioskUser. Выполните новый вход пользователя."
        }
        return
    }

    if ((Test-Path -LiteralPath $resolvedBackupPath) -and -not $Force) {
        throw "Backup уже существует: $resolvedBackupPath. Используйте -Force только после проверки backup."
    }

    $before = Get-NoRunState $policyKeyPath
    $backup = [ordered]@{
        Version = 1
        KioskUser = $KioskUser
        SID = $sid
        CapturedAtUtc = [DateTime]::UtcNow.ToString("O")
        KeyExisted = $before.KeyExisted
        NoRunExisted = $before.NoRunExisted
        NoRunValue = $before.NoRunValue
    }

    if ($PSCmdlet.ShouldProcess($resolvedBackupPath, "сохранить backup пользовательской policy")) {
        New-Item -ItemType Directory -Path (Split-Path -Parent $resolvedBackupPath) -Force | Out-Null
        $backup | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $resolvedBackupPath -Encoding UTF8
    }

    if ($PSCmdlet.ShouldProcess($policyKeyPath, "включить NoRun=1 для $KioskUser")) {
        New-Item -ItemType Directory -Path $policyKeyPath -Force | Out-Null
        New-ItemProperty -LiteralPath $policyKeyPath -Name NoRun -Value 1 -PropertyType DWord -Force | Out-Null
        Write-Host "NoRun=1 применён для $KioskUser. Выполните новый вход пользователя."
        Write-Host "Win+R и Run должны быть недоступны для этой учётной записи. Backup: $resolvedBackupPath"
    }
}
finally {
    Close-UserHive $hive
}
