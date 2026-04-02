#!/bin/bash
# Generate RSA key pair for fiscal receipt digital signatures
# Run once before first deployment

set -e

SECRETS_DIR="./secrets"
mkdir -p "$SECRETS_DIR"

echo "Generating RSA-2048 key pair for TAXUP digital signatures..."

openssl genrsa -out "$SECRETS_DIR/private_key.pem" 2048
openssl rsa -in "$SECRETS_DIR/private_key.pem" -pubout -out "$SECRETS_DIR/public_key.pem"

# Generate DB password and secret key
openssl rand -hex 32 > "$SECRETS_DIR/db_password.txt"
openssl rand -base64 48 > "$SECRETS_DIR/secret_key.txt"

chmod 600 "$SECRETS_DIR/private_key.pem"
chmod 644 "$SECRETS_DIR/public_key.pem"
chmod 600 "$SECRETS_DIR/db_password.txt"
chmod 600 "$SECRETS_DIR/secret_key.txt"

echo "Keys generated in $SECRETS_DIR/"
echo "  private_key.pem - RSA private key (keep secret!)"
echo "  public_key.pem  - RSA public key"
echo "  db_password.txt - Database password"
echo "  secret_key.txt  - JWT secret key"
echo ""
echo "WARNING: Never commit the secrets/ directory to git!"
