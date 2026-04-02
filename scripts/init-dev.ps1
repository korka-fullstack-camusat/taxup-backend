# ============================================================
# TAXUP - Initialisation secrets locaux (Windows PowerShell)
# Usage: .\scripts\init-dev.ps1
# ============================================================
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host "==> Creation du dossier secrets/" -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path "secrets" | Out-Null

# ── Lire DB_PASSWORD depuis .env ────────────────────────────
$dbPassword = $null
$secretKey  = $null
foreach ($line in Get-Content .env) {
    if ($line -match "^DB_PASSWORD=(.+)$")  { $dbPassword = $Matches[1] }
    if ($line -match "^SECRET_KEY=(.+)$")   { $secretKey  = $Matches[1] }
}
if (-not $dbPassword) { Write-Error "DB_PASSWORD introuvable dans .env"; exit 1 }
if (-not $secretKey)  { $secretKey = [Convert]::ToBase64String((1..32 | ForEach-Object { Get-Random -Maximum 256 })) }

# ── Ecrire les fichiers texte ────────────────────────────────
[System.IO.File]::WriteAllText("secrets\db_password.txt", $dbPassword)
[System.IO.File]::WriteAllText("secrets\secret_key.txt",  $secretKey)
Write-Host "    db_password.txt et secret_key.txt ecrits" -ForegroundColor Green

# ── Generer les cles RSA ─────────────────────────────────────
$openssl = Get-Command openssl -ErrorAction SilentlyContinue
if ($openssl) {
    Write-Host "==> Generation des cles RSA via openssl..." -ForegroundColor Cyan
    & openssl genrsa -out secrets\private_key.pem 2048 2>$null
    & openssl rsa -in secrets\private_key.pem -pubout -out secrets\public_key.pem 2>$null
    Write-Host "    private_key.pem et public_key.pem generes" -ForegroundColor Green
} else {
    Write-Host "==> openssl non trouve - generation des cles RSA en PowerShell..." -ForegroundColor Yellow
    Add-Type -AssemblyName System.Security
    $rsa = [System.Security.Cryptography.RSA]::Create(2048)

    # Private key (PKCS#8 PEM)
    $privBytes = $rsa.ExportPkcs8PrivateKey()
    $privB64   = [Convert]::ToBase64String($privBytes) -replace "(.{64})", "`$1`n"
    $privPem   = "-----BEGIN PRIVATE KEY-----`n$privB64`n-----END PRIVATE KEY-----"
    [System.IO.File]::WriteAllText("secrets\private_key.pem", $privPem)

    # Public key (SubjectPublicKeyInfo PEM)
    $pubBytes  = $rsa.ExportSubjectPublicKeyInfo()
    $pubB64    = [Convert]::ToBase64String($pubBytes) -replace "(.{64})", "`$1`n"
    $pubPem    = "-----BEGIN PUBLIC KEY-----`n$pubB64`n-----END PUBLIC KEY-----"
    [System.IO.File]::WriteAllText("secrets\public_key.pem", $pubPem)
    Write-Host "    private_key.pem et public_key.pem generes" -ForegroundColor Green
}

Write-Host ""
Write-Host "Secrets initialises ! Vous pouvez maintenant lancer :" -ForegroundColor Green
Write-Host "  docker compose up -d" -ForegroundColor White
