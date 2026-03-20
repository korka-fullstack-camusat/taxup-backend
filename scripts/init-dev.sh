#!/usr/bin/env bash
# ============================================================
# TAXUP - Initialisation secrets locaux (Linux/macOS)
# Usage: bash scripts/init-dev.sh
# ============================================================
set -euo pipefail

echo "==> Création du dossier secrets/"
mkdir -p secrets

# ── Lire DB_PASSWORD depuis .env ────────────────────────────
DB_PASSWORD=$(grep -E "^DB_PASSWORD=" .env | cut -d= -f2-)
SECRET_KEY=$(grep -E "^SECRET_KEY=" .env | cut -d= -f2- || openssl rand -base64 32)

if [ -z "$DB_PASSWORD" ]; then
  echo "ERREUR : DB_PASSWORD introuvable dans .env" >&2
  exit 1
fi

printf '%s' "$DB_PASSWORD" > secrets/db_password.txt
printf '%s' "$SECRET_KEY"  > secrets/secret_key.txt
echo "    db_password.txt et secret_key.txt écrits"

# ── Générer les clés RSA ─────────────────────────────────────
echo "==> Génération des clés RSA..."
openssl genrsa -out secrets/private_key.pem 2048 2>/dev/null
openssl rsa -in secrets/private_key.pem -pubout -out secrets/public_key.pem 2>/dev/null
echo "    private_key.pem et public_key.pem générés"

chmod 600 secrets/*.pem secrets/*.txt

echo ""
echo "Secrets initialisés ! Vous pouvez maintenant lancer :"
echo "  docker compose up -d"
