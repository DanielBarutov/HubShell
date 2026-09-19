[CmdletBinding()]
param(
    [Uri]$ServerUrl = "http://127.0.0.1:8200/"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function ConvertFrom-SecureInput {
    param([Parameter(Mandatory)][Security.SecureString]$Value)

    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Value)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    }
    finally {
        if ($pointer -ne [IntPtr]::Zero) {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
        }
        $Value.Dispose()
    }
}

function New-RandomSecret {
    $bytes = New-Object byte[] 32
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $generator.GetBytes($bytes)
        return [Convert]::ToBase64String($bytes)
    }
    finally {
        $generator.Dispose()
    }
}

function Get-RequiredText {
    param([Parameter(Mandatory)][string]$Prompt)

    while ($true) {
        $value = (Read-Host $Prompt).Trim()
        if (-not [string]::IsNullOrWhiteSpace($value)) {
            return $value
        }
        Write-Host "Значение обязательно." -ForegroundColor Yellow
    }
}

function Invoke-SteamGuestRequest {
    param(
        [Parameter(Mandatory)][ValidateSet("Get", "Post")][string]$Method,
        [Parameter(Mandatory)][string]$Path,
        [object]$Body
    )

    $headers = @{ "X-Steam-Guest-Admin-Key" = $script:AdminKey }
    $arguments = @{
        Method = $Method
        Uri = [Uri]::new($ServerUrl, $Path)
        Headers = $headers
        ContentType = "application/json"
        ErrorAction = "Stop"
    }
    if ($null -ne $Body) {
        $arguments.Body = $Body | ConvertTo-Json -Compress
    }
    return Invoke-RestMethod @arguments
}

function Add-Station {
    Clear-Host
    Write-Host "=== Добавление игрового ПК ===" -ForegroundColor Cyan
    $stationId = Get-RequiredText "Название ПК (например, VIP03)"
    $generate = (Read-Host "Сгенерировать уникальный ключ ПК автоматически? [Y/n]").Trim()
    if ([string]::IsNullOrWhiteSpace($generate) -or $generate -match "^[YyДд]$") {
        $stationKey = New-RandomSecret
        Write-Host "`nСкопируйте ключ в .env рядом с HubShellSteam.exe:" -ForegroundColor Green
        Write-Host "HUBSHELL_STEAM_STATION_ID=$stationId"
        Write-Host "HUBSHELL_STEAM_STATION_KEY=$stationKey" -ForegroundColor Yellow
    }
    else {
        $stationKey = ConvertFrom-SecureInput (Read-Host "Введите уникальный ключ ПК" -AsSecureString)
    }

    Invoke-SteamGuestRequest -Method Post -Path "v1/stations" -Body @{
        stationId = $stationId
        stationKey = $stationKey
    } | Out-Null
    $stationKey = $null
    Write-Host "`nПК '$stationId' зарегистрирован." -ForegroundColor Green
    Write-Host "Важно: сохраните показанный ключ только в .env этого ПК." -ForegroundColor Yellow
}

function Add-SteamAccount {
    Clear-Host
    Write-Host "=== Добавление гостевого Steam-аккаунта ===" -ForegroundColor Cyan
    $login = Get-RequiredText "Логин Steam"
    $password = ConvertFrom-SecureInput (Read-Host "Пароль Steam" -AsSecureString)
    try {
        $result = Invoke-SteamGuestRequest -Method Post -Path "v1/accounts" -Body @{
            login = $login
            password = $password
        }
        Write-Host "`nАккаунт добавлен. Идентификатор: $($result.accountId)" -ForegroundColor Green
    }
    finally {
        $password = $null
    }
}

function Show-Accounts {
    Clear-Host
    Write-Host "=== Пул гостевых Steam-аккаунтов ===" -ForegroundColor Cyan
    $accounts = @(Invoke-SteamGuestRequest -Method Get -Path "v1/accounts")
    if ($accounts.Count -eq 0) {
        Write-Host "Аккаунтов пока нет."
        return
    }
    $accounts |
        Select-Object Login, State, StationId, LeasedAt |
        Format-Table -AutoSize
}

function Test-SteamGuestServer {
    Clear-Host
    Write-Host "=== Проверка связи с сервером ===" -ForegroundColor Cyan
    $healthUrl = [Uri]::new($ServerUrl, "health/live")
    $health = Invoke-RestMethod -Method Get -Uri $healthUrl -ErrorAction Stop
    Write-Host "Сервер доступен: $($health.status)" -ForegroundColor Green
}

if ($ServerUrl.Scheme -ne "http" -and $ServerUrl.Scheme -ne "https") {
    throw "Адрес сервера должен начинаться с http:// или https://"
}

Write-Host "Управление гостевыми Steam-аккаунтами" -ForegroundColor Cyan
Write-Host "Сервер: $ServerUrl"
if ($ServerUrl.Scheme -eq "http") {
    Write-Host "Используется HTTP. Это допустимо только в закрытой локальной сети клуба." -ForegroundColor Yellow
}
$script:AdminKey = ConvertFrom-SecureInput (Read-Host "Введите ключ администратора Steam Guest" -AsSecureString)

try {
    $running = $true
    while ($running) {
        Write-Host ""
        Write-Host "1. Добавить игровой ПК"
        Write-Host "2. Добавить гостевой Steam-аккаунт"
        Write-Host "3. Показать пул аккаунтов"
        Write-Host "4. Проверить связь с сервером"
        Write-Host "0. Выйти"
        $choice = (Read-Host "Выберите пункт").Trim()
        try {
            switch ($choice) {
                "1" { Add-Station }
                "2" { Add-SteamAccount }
                "3" { Show-Accounts }
                "4" { Test-SteamGuestServer }
                "0" { $running = $false }
                default { Write-Host "Введите 0, 1, 2, 3 или 4." -ForegroundColor Yellow }
            }
        }
        catch {
            Write-Host "Ошибка: $($_.Exception.Message)" -ForegroundColor Red
            Write-Host "Проверьте адрес сервера, ключ администратора и состояние контейнера." -ForegroundColor Yellow
        }
    }
}
finally {
    $script:AdminKey = $null
}
