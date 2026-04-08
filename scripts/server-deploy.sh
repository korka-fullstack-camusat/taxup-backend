#!/usr/bin/env bash
# =============================================================================
# TaxUp — Script de déploiement production
# Serveur : 141.94.204.35 | SSH : 4230
# Usage   : bash scripts/server-deploy.sh
# =============================================================================
set -euo pipefail

# ── Couleurs ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()  { echo -e "${BLUE}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

# ── Configuration ─────────────────────────────────────────────────────────────
SERVER_IP="141.94.204.35"
DEPLOY_DIR="/opt/taxup"
BACKEND_REPO="https://github.com/korka-fullstack-camusat/taxup-backend.git"
FRONTEND_REPO="https://github.com/korka-fullstack-camusat/taxup-frontend.git"
BRANCH="claude/deploy-production-server-HgQYf"

echo ""
echo "========================================================="
echo "   TaxUp — Déploiement Production"
echo "   Serveur : ${SERVER_IP}"
echo "   Répertoire : ${DEPLOY_DIR}"
echo "========================================================="
echo ""

# ── 1. Vérifier/Installer Docker ─────────────────────────────────────────────
info "Vérification de Docker..."
if ! command -v docker &>/dev/null; then
    warn "Docker non trouvé. Installation en cours..."
    apt-get update -qq
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
    ok "Docker installé."
else
    ok "Docker $(docker --version | cut -d' ' -f3 | tr -d ',') déjà présent."
fi

if ! docker compose version &>/dev/null; then
    warn "Docker Compose plugin non trouvé. Installation..."
    apt-get install -y docker-compose-plugin
    ok "Docker Compose installé."
else
    ok "Docker Compose $(docker compose version --short) déjà présent."
fi

# ── 2. Installer les dépendances système ──────────────────────────────────────
info "Installation des dépendances système..."
apt-get install -y -qq git curl openssl
ok "Dépendances OK."

# ── 3. Créer la structure de répertoires ──────────────────────────────────────
info "Création de la structure ${DEPLOY_DIR}..."
mkdir -p "${DEPLOY_DIR}"
cd "${DEPLOY_DIR}"

# ── 4. Cloner ou mettre à jour les dépôts ────────────────────────────────────
for REPO_NAME in backend frontend; do
    REPO_URL="${BACKEND_REPO}"
    [ "$REPO_NAME" = "frontend" ] && REPO_URL="${FRONTEND_REPO}"

    if [ -d "${DEPLOY_DIR}/${REPO_NAME}/.git" ]; then
        info "Mise à jour du dépôt ${REPO_NAME}..."
        git -C "${DEPLOY_DIR}/${REPO_NAME}" fetch origin
        git -C "${DEPLOY_DIR}/${REPO_NAME}" checkout "${BRANCH}" 2>/dev/null || \
            git -C "${DEPLOY_DIR}/${REPO_NAME}" checkout main
        git -C "${DEPLOY_DIR}/${REPO_NAME}" pull
    else
        info "Clonage du dépôt ${REPO_NAME}..."
        git clone --branch "${BRANCH}" "${REPO_URL}" "${DEPLOY_DIR}/${REPO_NAME}" 2>/dev/null || \
            git clone "${REPO_URL}" "${DEPLOY_DIR}/${REPO_NAME}"
    fi
    ok "Dépôt ${REPO_NAME} prêt."
done

# ── 5. Configurer le fichier .env backend ────────────────────────────────────
BACKEND_ENV="${DEPLOY_DIR}/backend/.env"
if [ ! -f "${BACKEND_ENV}" ]; then
    info "Création du fichier .env backend..."
    cp "${DEPLOY_DIR}/backend/.env.example" "${BACKEND_ENV}"

    # Générer une SECRET_KEY sécurisée
    NEW_SECRET=$(openssl rand -base64 48)
    sed -i "s|^SECRET_KEY=.*|SECRET_KEY=${NEW_SECRET}|" "${BACKEND_ENV}"

    # Générer un mot de passe DB sécurisé
    NEW_DB_PASS=$(openssl rand -hex 24)
    sed -i "s|^DB_PASSWORD=.*|DB_PASSWORD=${NEW_DB_PASS}|" "${BACKEND_ENV}"
    sed -i "s|^DATABASE_URL=.*|DATABASE_URL=postgresql://taxup_user:${NEW_DB_PASS}@postgres:5432/taxup|" "${BACKEND_ENV}"

    # Configurer CORS avec l'IP du serveur
    sed -i "s|^BACKEND_CORS_ORIGINS=.*|BACKEND_CORS_ORIGINS=http://${SERVER_IP}:3000,http://${SERVER_IP}:8000|" "${BACKEND_ENV}"

    # Configurer l'environnement production
    sed -i "s|^DEBUG=.*|DEBUG=false|" "${BACKEND_ENV}"
    sed -i "s|^ENVIRONMENT=.*|ENVIRONMENT=production|" "${BACKEND_ENV}"

    # Configurer le chemin du frontend
    echo "" >> "${BACKEND_ENV}"
    echo "# Déploiement" >> "${BACKEND_ENV}"
    echo "FRONTEND_PATH=${DEPLOY_DIR}/frontend" >> "${BACKEND_ENV}"
    echo "NEXT_PUBLIC_API_URL=http://${SERVER_IP}:8000" >> "${BACKEND_ENV}"

    ok ".env backend créé avec des clés sécurisées auto-générées."
else
    warn ".env backend existant conservé."
    # S'assurer que FRONTEND_PATH est défini
    if ! grep -q "^FRONTEND_PATH=" "${BACKEND_ENV}"; then
        echo "FRONTEND_PATH=${DEPLOY_DIR}/frontend" >> "${BACKEND_ENV}"
        echo "NEXT_PUBLIC_API_URL=http://${SERVER_IP}:8000" >> "${BACKEND_ENV}"
    fi
fi

# ── 6. Générer les clés RSA (signatures fiscales) ────────────────────────────
SECRETS_DIR="${DEPLOY_DIR}/backend/secrets"
if [ ! -f "${SECRETS_DIR}/private_key.pem" ]; then
    info "Génération des clés RSA pour les signatures fiscales..."
    mkdir -p "${SECRETS_DIR}"
    bash "${DEPLOY_DIR}/backend/scripts/generate_keys.sh"
    ok "Clés RSA générées dans ${SECRETS_DIR}."
else
    ok "Clés RSA déjà présentes."
fi

# ── 7. Configurer le firewall ────────────────────────────────────────────────
if command -v ufw &>/dev/null; then
    info "Configuration du firewall UFW..."
    ufw allow 3000/tcp comment 'TaxUp Frontend' 2>/dev/null || true
    ufw allow 8000/tcp comment 'TaxUp Backend API' 2>/dev/null || true
    ok "Firewall configuré (ports 3000 et 8000 ouverts)."
fi

# ── 8. Lancer les conteneurs ─────────────────────────────────────────────────
info "Démarrage des services Docker..."
cd "${DEPLOY_DIR}/backend"

# Arrêter les conteneurs existants
if docker compose ps --quiet 2>/dev/null | grep -q .; then
    warn "Arrêt des conteneurs existants..."
    docker compose --profile frontend down
fi

# Build et démarrage
info "Build et démarrage des conteneurs (cela peut prendre 5-10 minutes)..."
docker compose --profile frontend up -d --build

ok "Conteneurs démarrés."

# ── 9. Vérifications ─────────────────────────────────────────────────────────
echo ""
info "Attente du démarrage des services (30s)..."
sleep 30

echo ""
echo "─── État des conteneurs ───────────────────────────────────"
docker compose --profile frontend ps

echo ""
info "Test du backend (health check)..."
for i in 1 2 3 4 5; do
    if curl -sf "http://localhost:8000/health" &>/dev/null; then
        ok "Backend opérationnel : http://${SERVER_IP}:8000"
        break
    fi
    warn "Tentative $i/5 — attente 10s..."
    sleep 10
done

info "Test du frontend..."
for i in 1 2 3 4 5; do
    if curl -sf "http://localhost:3000" &>/dev/null; then
        ok "Frontend opérationnel : http://${SERVER_IP}:3000"
        break
    fi
    warn "Tentative $i/5 — attente 10s..."
    sleep 10
done

info "Test de l'API docs..."
if curl -sf "http://localhost:8000/docs" &>/dev/null; then
    ok "Documentation API : http://${SERVER_IP}:8000/docs"
fi

# ── 10. Résumé ───────────────────────────────────────────────────────────────
echo ""
echo "========================================================="
echo -e "${GREEN}   DÉPLOIEMENT TERMINÉ${NC}"
echo "========================================================="
echo ""
echo "  Frontend   : http://${SERVER_IP}:3000"
echo "  Backend    : http://${SERVER_IP}:8000"
echo "  API Docs   : http://${SERVER_IP}:8000/docs"
echo ""
echo "  Logs backend : cd ${DEPLOY_DIR}/backend && docker compose logs -f api"
echo "  Logs frontend: cd ${DEPLOY_DIR}/backend && docker compose --profile frontend logs -f frontend"
echo "  Arrêter tout : cd ${DEPLOY_DIR}/backend && docker compose --profile frontend down"
echo ""
echo "  Fichier .env : ${BACKEND_ENV}"
echo "  Clés RSA     : ${SECRETS_DIR}/"
echo "========================================================="
