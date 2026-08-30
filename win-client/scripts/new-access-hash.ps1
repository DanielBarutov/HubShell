[CmdletBinding()]
param(
    [ValidateSet("user", "manager")]
    [string]$Kind = "manager",
    [int]$Iterations = 210000
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($Iterations -lt 100000 -or $Iterations -gt 1000000) {
    throw "Iterations должен быть в диапазоне от 100000 до 1000000."
}

$secret = Read-Host "Введите секрет ($Kind)" -AsSecureString
$pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
try {
    $plainSecret = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    if ($Kind -eq "manager" -and $plainSecret.Length -lt 8) {
        throw "Пароль менеджера должен содержать минимум 8 символов."
    }
    $salt = [System.Security.Cryptography.RandomNumberGenerator]::GetBytes(16)
    $derived = [System.Security.Cryptography.Rfc2898DeriveBytes]::Pbkdf2(
        $plainSecret,
        $salt,
        $Iterations,
        [System.Security.Cryptography.HashAlgorithmName]::SHA256,
        32
    )
    $encoded = "pbkdf2-sha256`$" + $Iterations + "`$" +
        [Convert]::ToBase64String($salt) + "`$" +
        [Convert]::ToBase64String($derived)
    $variable = if ($Kind -eq "manager") { "GAMECLUB_MANAGER_PASSWORD_HASH" } else { "GAMECLUB_CLIENT_ACCESS_PIN_HASH" }
    Write-Output "$variable=$encoded"
}
finally {
    if ($pointer -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    }
    $plainSecret = $null
    $secret.Dispose()
}
