#!/usr/bin/env bash
# =============================================================================
# TaxUp — Script de mise à jour production
# Usage : bash scripts/server-update.sh
# =============================================================================
set -euo pipefail

GREEN='\033[0;32m'; BLUE='\033[0;34m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${BLUE}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }

DEPLOY_DIR="/opt/taxup"
BRANCH="claude/deploy-production-server-HgQYf"

echo ""
echo "========================================="
echo "   TaxUp — Mise à jour Production"
echo "========================================="
echo ""

# Mettre à jour les dépôts
for REPO in backend frontend; do
    info "Mise à jour ${REPO}..."
    git -C "${DEPLOY_DIR}/${REPO}" pull origin "${BRANCH}" 2>/dev/null || \
        git -C "${DEPLOY_DIR}/${REPO}" pull origin main
    ok "${REPO} mis à jour."
done

# Rebuild et redémarrage
cd "${DEPLOY_DIR}/backend"
info "Rebuild des images Docker..."
docker compose --profile frontend up -d --build

info "Attente du démarrage (20s)..."
sleep 20

echo ""
docker compose --profile frontend ps
echo ""
ok "Mise à jour terminée !"
