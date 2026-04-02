#!/bin/bash
# TAXUP - Script de setup rapide
# Exécutez ce script APRÈS avoir extrait le ZIP

set -e
echo "=== TAXUP Setup ==="

# 1. Créer .env
if [ ! -f .env ]; then
    cp .env.example .env
    echo "✓ .env créé depuis .env.example — pensez à le configurer"
fi

# 2. Générer les clés cryptographiques
mkdir -p secrets
if [ ! -f secrets/private_key.pem ]; then
    ./scripts/generate_keys.sh
    echo "✓ Clés RSA générées"
fi

# 3. Lancer avec Docker Compose
echo ""
echo "Pour lancer le projet :"
echo "  docker compose up -d"
echo ""
echo "Pour le développement (avec hot-reload) :"
echo "  docker compose -f docker-compose.yml -f docker-compose.dev.yml up"
echo ""
echo "Docs API disponibles sur : http://localhost:8000/docs"
