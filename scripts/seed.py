#!/usr/bin/env python3
"""
TAXUP — Script de données de test (seed)
=========================================
Stratégie :
  1. Insère les 2 admins directement en base (admin + amadou.kane).
  2. Crée tous les autres utilisateurs via l'API.
  3. LOT A : Transactions normales (petits montants) via API — résilient
             aux erreurs réseau (chaque requête est retryée / ignorée
             si elle échoue, pour ne jamais planter le seed entier).
  4. LOT B : Transactions suspectes injectées directement en base
             avec created_at dans le passé (hors fenêtre velocity)
             → alertes fraude insérées en base (LARGE_AMOUNT,
               STRUCTURING, ROUND_TRIPPING).
  5. Crée les audits via l'API.

Usage :
    docker compose exec api python scripts/seed.py

Comptes de test :
    ADMIN            admin@taxup.sn              Admin@2026!
    ADMIN            amadou.kane@taxup.sn        P@sser123
    AGENT_DGID       agent_diallo@dgid.sn        Agent@2026!
    AGENT_DGID       agent_sow@dgid.sn           Agent@2026!
    AUDITEUR_FISCAL  auditeur_fall@taxup.sn      Audit@2026!
    AUDITEUR_FISCAL  auditeur_ndiaye@taxup.sn    Audit@2026!
    OPERATEUR_MOBILE wave_sn@taxup.sn            Oper@2026!
    OPERATEUR_MOBILE orangemoney@taxup.sn        Oper@2026!
    OPERATEUR_MOBILE freemoney@taxup.sn          Oper@2026!
    CITOYEN          amadou_ba@gmail.com         Citoyen@2026!
    CITOYEN          fatou_mbaye@gmail.com       Citoyen@2026!
"""

import sys
import os
sys.path.insert(0, "/app")

import asyncio
import json
import random
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import asyncpg
import httpx

from app.core.security import get_password_hash

# ── Config ────────────────────────────────────────────────────────────────────

BASE_URL = os.getenv("SEED_API_URL", "http://localhost:8000/api/v1")
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "Admin@2026!"

# Second admin persistant — ne sera jamais perdu après un re-seed
EXTRA_ADMIN_USERNAME = "amadou.kane"
EXTRA_ADMIN_EMAIL = "amadou.kane@taxup.sn"
EXTRA_ADMIN_PASSWORD = "P@sser123"

# Tuning anti-surcharge API (signature RSA des reçus est coûteuse)
TX_PER_OPERATOR_LOT_A = 20        # était 40 — réduit pour éviter ReadError
SUSPICIOUS_TX_PER_OPERATOR = 25
REQUEST_TIMEOUT = 120.0           # 2 min par requête
DELAY_BETWEEN_TX = 0.15           # 150 ms entre transactions → décharge l'API
MAX_RETRIES = 3

# Numéros de téléphone simulés
PHONES = [
    "+224621000001", "+224621000002", "+224621000003", "+224621000004",
    "+224621000005", "+224621000006", "+224621000007", "+224621000008",
    "+224661000001", "+224661000002", "+224661000003", "+224661000004",
    "+221771000001", "+221771000002", "+221771000003",
]

TX_TYPES = ["TRANSFERT", "PAIEMENT", "RETRAIT", "DEPOT", "REMBOURSEMENT"]
TX_TYPE_WEIGHTS = [100, 30, 15, 15, 5]

NORMAL_AMOUNTS = [
    5_000, 7_500, 10_000, 15_000, 20_000,
    25_000, 100_000, 50_000, 75_000, 100_000,
    150_000, 200_000, 300_000, 400_000, 499_000,
]

SUSPICIOUS_AMOUNTS = [
    1_000_000, 1_500_000, 2_000_000, 2_500_000, 5_000_000,
    7_500_000, 10_000_000, 15_000_000, 25_000_000,
]

AUDIT_TITLES = [
    ("Audit de conformité Q1 2026",        "MONTANT_SUSPECT"),
    ("Vérification opérateur Wave",         "FREQUENCE_ANORMALE"),
    ("Contrôle blanchiment Conakry",        "BLANCHIMENT"),
    ("Anomalie double transaction",         "DOUBLE_TRANSACTION"),
    ("Suspicion évasion fiscale",           "EVASION_FISCALE"),
    ("Audit identité douteuse",             "IDENTITE_DOUTEUSE"),
    ("Contrôle fréquence Mobile Money",     "FREQUENCE_ANORMALE"),
    ("Revue montants suspects Q4 2025",     "MONTANT_SUSPECT"),
    ("Audit réseau Orange Money",           "AUTRE"),
    ("Détection structuring — seuil 1M",    "MONTANT_SUSPECT"),
    ("Contrôle identités Free Money",       "IDENTITE_DOUTEUSE"),
    ("Audit annuel 2025",                   "EVASION_FISCALE"),
    ("Fraude potentielle aller-retour",     "BLANCHIMENT"),
    ("Anomalie dépôt en espèces",           "MONTANT_SUSPECT"),
    ("Revue conformité Q2 2026",            "AUTRE"),
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def rand_past_date(days_ago_min: int = 1, days_ago_max: int = 180) -> datetime:
    delta_minutes = random.randint(days_ago_min * 1440, days_ago_max * 1440)
    return datetime.now(timezone.utc) - timedelta(minutes=delta_minutes)

def rand_phone() -> str:
    return random.choice(PHONES)

def rand_ref(prefix: str = "TXN") -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    rand = secrets.token_hex(4).upper()
    return f"{prefix}-{ts}-{rand}"

def get_db_url() -> str:
    url = os.getenv("DATABASE_URL", "")
    if not url:
        raise RuntimeError("DATABASE_URL n'est pas définie.")
    return (
        url.replace("postgresql+asyncpg://", "postgresql://")
           .replace("postgres://", "postgresql://")
    )

async def safe_post(client: httpx.AsyncClient, url: str, *,
                    headers: dict | None = None,
                    json_body: dict | None = None) -> httpx.Response | None:
    """POST avec retry sur ReadError/ConnectError. Retourne None après épuisement."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return await client.post(url, headers=headers, json=json_body)
        except (httpx.ReadError, httpx.ConnectError, httpx.ReadTimeout,
                httpx.RemoteProtocolError) as e:
            if attempt == MAX_RETRIES:
                print(f"   ⚠ {url} échec après {MAX_RETRIES} tentatives ({type(e).__name__})")
                return None
            await asyncio.sleep(1.0 * attempt)  # backoff 1s, 2s
    return None

async def insert_admin_direct(conn: asyncpg.Connection, username: str,
                              email: str, password: str, full_name: str,
                              phone: str) -> uuid.UUID:
    """Insère un ADMIN directement en base avec ON CONFLICT (idempotent)."""
    admin_id = uuid.uuid4()
    await conn.execute("""
        INSERT INTO users (id, username, email, hashed_password, full_name, role,
                           phone_number, organization, is_active, is_verified,
                           api_key, created_at, updated_at)
        VALUES ($1,$2,$3,$4,$5,'ADMIN',$6,$7,true,true,$8,NOW(),NOW())
        ON CONFLICT (username) DO UPDATE SET
            email = EXCLUDED.email,
            hashed_password = EXCLUDED.hashed_password,
            full_name = EXCLUDED.full_name,
            role = 'ADMIN',
            is_active = true,
            is_verified = true,
            updated_at = NOW()
    """,
        admin_id, username, email,
        get_password_hash(password),
        full_name, phone, "TAXUP",
        secrets.token_urlsafe(32),
    )
    return admin_id

# ── Phase 1 : setup DB (event loop isolé — évite conflit asyncpg/httpx) ───────

async def setup_db() -> None:
    db_url = get_db_url()
    print(f"📦 Connexion DB : {db_url[:50]}...")
    conn = await asyncpg.connect(db_url)
    try:
        print("🗑  Nettoyage des tables...")
        await conn.execute("""
            TRUNCATE notifications, fraud_alerts, audits, fiscal_receipts, transactions, users
            RESTART IDENTITY CASCADE
        """)

        print("👤 Création des admins...")
        await insert_admin_direct(conn, ADMIN_USERNAME, "admin@taxup.sn",
                                  ADMIN_PASSWORD, "Administrateur Système",
                                  "+224600000001")
        print(f"   ✓ admin / {ADMIN_PASSWORD}")

        await insert_admin_direct(conn, EXTRA_ADMIN_USERNAME, EXTRA_ADMIN_EMAIL,
                                  EXTRA_ADMIN_PASSWORD, "Amadou Kane",
                                  "+224600000099")
        print(f"   ✓ {EXTRA_ADMIN_USERNAME} / {EXTRA_ADMIN_PASSWORD}")
    finally:
        await conn.close()


# ── Phase 2 : seed via API (event loop frais — httpx fonctionne correctement) ─

async def seed_via_api() -> None:
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=REQUEST_TIMEOUT) as client:

        print("\n🔑 Connexion admin...")
        r = await safe_post(client, "/auth/login", json_body={
            "username": ADMIN_USERNAME, "password": ADMIN_PASSWORD,
        })
        if r is None or r.status_code != 200:
            raise RuntimeError("Échec login admin")
        admin_token = r.json()["access_token"]
        ah = {"Authorization": f"Bearer {admin_token}"}
        print("   ✓ Connecté")

        print("\n👥 Création des utilisateurs...")
        other_users = [
            ("agent_diallo",   "agent_diallo@dgid.sn",       "Ibrahima Diallo",        "AGENT_DGID",       "+224600000002", "DGID — Bureau Conakry",  "Agent@2026!"),
            ("agent_sow",      "agent_sow@dgid.sn",          "Mariama Sow",             "AGENT_DGID",       "+224600000003", "DGID — Bureau Labé",     "Agent@2026!"),
            ("auditeur_fall",  "auditeur_fall@taxup.sn",     "Cheikh Fall",             "AUDITEUR_FISCAL",  "+224600000004", "Cellule Audit Fiscal",   "Audit@2026!"),
            ("auditeur_ndiaye","auditeur_ndiaye@taxup.sn",   "Aissatou Ndiaye",         "AUDITEUR_FISCAL",  "+224600000005", "Cellule Audit Fiscal",   "Audit@2026!"),
            ("wave_sn",        "wave_sn@taxup.sn",           "Wave Sénégal",            "OPERATEUR_MOBILE", "+224600000010", "Wave Mobile Money",      "Oper@2026!"),
            ("orangemoney",    "orangemoney@taxup.sn",        "Orange Money Guinée",     "OPERATEUR_MOBILE", "+224600000011", "Orange Money SA",        "Oper@2026!"),
            ("freemoney",      "freemoney@taxup.sn",          "Free Money",              "OPERATEUR_MOBILE", "+224600000012", "Wave Senegal",           "Oper@2026!"),
            ("amadou_ba",      "amadou_ba@gmail.com",         "Amadou Ba",               "CITOYEN",          "+224620000001", None,                     "Citoyen@2026!"),
            ("fatou_mbaye",    "fatou_mbaye@gmail.com",       "Fatou Mbaye",             "CITOYEN",          "+224620000002", None,                     "Citoyen@2026!"),
        ]

        operator_ids: dict[str, str] = {}

        for (uname, email, fname, role, phone, org, pwd) in other_users:
            payload = {
                "username": uname, "email": email, "password": pwd,
                "full_name": fname, "role": role, "phone_number": phone,
            }
            if org:
                payload["organization"] = org
            r = await safe_post(client, "/users", headers=ah, json_body=payload)
            if r is None or r.status_code not in (200, 201):
                code = r.status_code if r is not None else "NETWORK"
                print(f"   ✗ {uname} : {code}")
                continue
            print(f"   ✓ {role:<20} {email}")

        r_users = await client.get("/users", headers=ah, params={"page_size": 50})
        if r_users.status_code == 200:
            for u in r_users.json().get("items", []):
                operator_ids[u["username"]] = u["id"]

        # ── 5a. LOT A : Transactions normales (résilient) ─────────────────────
        print(f"\n💸 LOT A — Transactions normales ({TX_PER_OPERATOR_LOT_A}/opérateur)...")
        operators = [
            ("wave_sn",     "Oper@2026!"),
            ("orangemoney", "Oper@2026!"),
            ("freemoney",   "Oper@2026!"),
        ]

        tx_ids: list[str] = []
        user_tokens: dict[str, str] = {}

        for (uname, pwd) in operators:
            r = await safe_post(client, "/auth/login",
                                json_body={"username": uname, "password": pwd})
            if r is None or r.status_code != 200:
                print(f"   ✗ Login {uname}")
                continue
            op_token = r.json()["access_token"]
            op_h = {"Authorization": f"Bearer {op_token}"}
            user_tokens[uname] = op_token

            count = 0
            failed = 0
            for _ in range(TX_PER_OPERATOR_LOT_A):
                sender = rand_phone()
                receiver = random.choice([p for p in PHONES if p != sender])
                amount = random.choice(NORMAL_AMOUNTS)
                tx_date = rand_past_date(days_ago_min=2, days_ago_max=120)
                r2 = await safe_post(client, "/transactions", headers=op_h, json_body={
                    "amount": str(float(amount)),
                    "currency": "XOF",
                    "transaction_type": random.choices(TX_TYPES, weights=TX_TYPE_WEIGHTS)[0],
                    "sender_phone": sender,
                    "receiver_phone": receiver,
                    "sender_name": f"Émetteur {random.randint(100,999)}",
                    "receiver_name": f"Destinataire {random.randint(100,999)}",
                    "transaction_date": tx_date.isoformat(),
                })
                if r2 is not None and r2.status_code == 201:
                    tx_ids.append(r2.json()["id"])
                    count += 1
                else:
                    failed += 1
                await asyncio.sleep(DELAY_BETWEEN_TX)
            tag = "" if failed == 0 else f" ({failed} échecs tolérés)"
            print(f"   ✓ {uname} : {count}/{TX_PER_OPERATOR_LOT_A}{tag}")

        # receipt generation happens in Phase 3 (generate_receipts_db)

        # ── 5b. LOT B : Transactions suspectes directement en base ───────────
        print(f"\n🚨 LOT B — Transactions suspectes ({SUSPICIOUS_TX_PER_OPERATOR}/opérateur)...")
        conn2 = await asyncpg.connect(get_db_url())
        try:
            suspicious_tx_ids: list[str] = []
            for uname in ["wave_sn", "orangemoney", "freemoney"]:
                op_uuid_str = operator_ids.get(uname)
                if not op_uuid_str:
                    print(f"   ✗ UUID introuvable pour {uname}")
                    continue

                count = 0
                for _ in range(SUSPICIOUS_TX_PER_OPERATOR):
                    tx_id = uuid.uuid4()
                    past_created_at = rand_past_date(days_ago_min=3, days_ago_max=30)
                    tx_date = rand_past_date(days_ago_min=3, days_ago_max=90)
                    amount = random.choice(SUSPICIOUS_AMOUNTS)
                    sender = rand_phone()
                    receiver = random.choice([p for p in PHONES if p != sender])
                    ref = rand_ref("TX-SUSP")

                    await conn2.execute("""
                        INSERT INTO transactions (
                            id, reference, operator_id, amount, currency,
                            transaction_type, sender_phone, receiver_phone,
                            sender_name, receiver_name, status,
                            transaction_date, created_at, updated_at
                        ) VALUES (
                            $1,$2,$3,$4,'XOF', $5,$6,$7,
                            $8,$9,'UNDER_REVIEW', $10,$11,$11
                        )
                    """,
                        tx_id, ref, uuid.UUID(op_uuid_str),
                        Decimal(str(amount)),
                        random.choices(TX_TYPES, weights=TX_TYPE_WEIGHTS)[0],
                        sender, receiver,
                        f"Suspect {random.randint(100,999)}",
                        f"Destinataire {random.randint(100,999)}",
                        tx_date, past_created_at,
                    )

                    risk_large = min(1.0, amount / 2_000_000)
                    await conn2.execute("""
                        INSERT INTO fraud_alerts (id, transaction_id, fraud_type, status,
                                                  risk_score, description, details, detected_at)
                        VALUES ($1,$2,'LARGE_AMOUNT','DETECTED',$3,$4,$5,$6)
                    """,
                        uuid.uuid4(), tx_id, round(risk_large, 4),
                        f"Montant {amount:,.0f} XOF dépasse le seuil de 1 000 000 XOF",
                        json.dumps({"amount": amount, "threshold": 1_000_000}),
                        past_created_at,
                    )

                    if random.random() < 0.6:
                        cumulative = amount + random.randint(200_000, 800_000)
                        risk_struct = min(1.0, cumulative / 1_000_000)
                        await conn2.execute("""
                            INSERT INTO fraud_alerts (id, transaction_id, fraud_type, status,
                                                      risk_score, description, details, detected_at)
                            VALUES ($1,$2,'STRUCTURING','DETECTED',$3,$4,$5,$6)
                        """,
                            uuid.uuid4(), tx_id, round(risk_struct, 4),
                            f"Montant cumulé {cumulative:,.0f} XOF sur 24h — structuring probable",
                            json.dumps({"cumulative_amount": cumulative, "threshold": 500_000}),
                            past_created_at,
                        )

                    if random.random() < 0.3:
                        await conn2.execute("""
                            INSERT INTO fraud_alerts (id, transaction_id, fraud_type, status,
                                                      risk_score, description, details, detected_at)
                            VALUES ($1,$2,'ROUND_TRIPPING','DETECTED',0.85,$3,$4,$5)
                        """,
                            uuid.uuid4(), tx_id,
                            "Transaction aller-retour détectée entre les mêmes parties",
                            json.dumps({"reverse_count": 1, "window_hours": 24}),
                            past_created_at,
                        )

                    suspicious_tx_ids.append(str(tx_id))
                    count += 1

                print(f"   ✓ {uname} : {count}/{SUSPICIOUS_TX_PER_OPERATOR}")
        finally:
            await conn2.close()

        # ── 6. Audits ─────────────────────────────────────────────────────────
        print("\n🔍 Création des audits...")
        agents = [
            ("agent_diallo",   "Agent@2026!"),
            ("agent_sow",      "Agent@2026!"),
            ("auditeur_fall",  "Audit@2026!"),
            ("auditeur_ndiaye","Audit@2026!"),
        ]
        agent_tokens: list[str] = []
        for (uname, pwd) in agents:
            r = await safe_post(client, "/auth/login",
                                json_body={"username": uname, "password": pwd})
            if r is not None and r.status_code == 200:
                agent_tokens.append(r.json()["access_token"])

        all_tx_for_audit = tx_ids + suspicious_tx_ids
        audit_count = 0
        for i, (title, anom) in enumerate(AUDIT_TITLES):
            if not agent_tokens:
                break
            agt_h = {"Authorization": f"Bearer {agent_tokens[i % len(agent_tokens)]}"}
            payload: dict = {
                "title": title,
                "description": f"Description détaillée : {title.lower()}. Analyse en cours.",
                "anomaly_type": anom,
            }
            if all_tx_for_audit and i < len(all_tx_for_audit):
                payload["transaction_id"] = all_tx_for_audit[i]
            r = await safe_post(client, "/audits", headers=agt_h, json_body=payload)
            if r is not None and r.status_code == 201:
                audit_count += 1
        print(f"   ✓ {audit_count}/{len(AUDIT_TITLES)} audits créés")

        total_tx = len(tx_ids) + len(suspicious_tx_ids)

        print(f"\n{'='*65}")
        print("✅ BASE DE DONNÉES INITIALISÉE AVEC SUCCÈS")
        print(f"{'='*65}")
        print(f"  Transactions normales   : {len(tx_ids)}")
        print(f"  Transactions suspectes  : {len(suspicious_tx_ids)} (alertes fraude)")
        print(f"  Total transactions      : {total_tx}")
        print(f"  Audits créés            : {audit_count}")
        print()
        print("  Comptes de test :")
        print(f"  {'Rôle':<20} {'Login':<26} {'Mot de passe'}")
        print(f"  {'-'*66}")
        rows = [
            ("ADMIN",            "admin",                    "Admin@2026!"),
            ("ADMIN",            "amadou.kane",              "P@sser123"),
            ("AGENT_DGID",       "agent_diallo",             "Agent@2026!"),
            ("AGENT_DGID",       "agent_sow",                "Agent@2026!"),
            ("AUDITEUR_FISCAL",  "auditeur_fall",            "Audit@2026!"),
            ("AUDITEUR_FISCAL",  "auditeur_ndiaye",          "Audit@2026!"),
            ("OPERATEUR_MOBILE", "wave_sn",                  "Oper@2026!"),
            ("OPERATEUR_MOBILE", "orangemoney",              "Oper@2026!"),
            ("OPERATEUR_MOBILE", "freemoney",                "Oper@2026!"),
            ("CITOYEN",          "amadou_ba",                "Citoyen@2026!"),
            ("CITOYEN",          "fatou_mbaye",              "Citoyen@2026!"),
        ]
        for (role, login, pwd) in rows:
            print(f"  {role:<20} {login:<26} {pwd}")
        print(f"{'='*65}\n")


# ── Phase 3 : Génération des reçus fiscaux (event loop isolé) ──────────────────

async def generate_receipts_db() -> int:
    import hashlib
    conn = await asyncpg.connect(get_db_url())
    receipt_count = 0
    try:
        rows = await conn.fetch(
            "SELECT id, reference, operator_id, amount, currency FROM transactions "
            "WHERE id NOT IN (SELECT transaction_id FROM fiscal_receipts)"
        )
        print(f"\n🧾 Génération des reçus fiscaux ({len(rows)} transactions sans reçu)...")
        now = datetime.now(timezone.utc)
        fiscal_year = now.year
        quarter = (now.month - 1) // 3 + 1
        fiscal_period = f"{fiscal_year}-Q{quarter}"
        tax_rate = 0.18
        ts_str = now.strftime("%Y%m%d")

        for row in rows:
            tax_base   = float(row["amount"])
            tax_amount = round(tax_base * tax_rate, 2)
            total      = round(tax_base + tax_amount, 2)
            hash_part  = hashlib.sha256(
                f"{row['operator_id']}{row['reference']}".encode()
            ).hexdigest()[:8].upper()
            receipt_number    = f"RCPT-{ts_str}-{hash_part}"
            sig_raw           = f"{receipt_number}|{row['reference']}|{row['amount']}|{tax_rate}"
            digital_signature = hashlib.sha256(sig_raw.encode()).hexdigest()
            qr_data           = f"TAXUP|{receipt_number}|{digital_signature[:16]}"
            try:
                await conn.execute("""
                    INSERT INTO fiscal_receipts (
                        id, receipt_number, transaction_id, operator_id,
                        tax_base, tax_rate, tax_amount, total_amount, currency,
                        digital_signature, signature_algorithm, qr_code_data,
                        fiscal_year, fiscal_period, is_certified, issued_at,
                        is_cancelled
                    ) VALUES (
                        $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,true,$15,false
                    )
                """,
                    uuid.uuid4(), receipt_number, row["id"], row["operator_id"],
                    tax_base, tax_rate, tax_amount, total, row["currency"],
                    digital_signature, "SHA256-SEED", qr_data,
                    fiscal_year, fiscal_period, now,
                )
                await conn.execute(
                    "UPDATE transactions SET status='COMPLETED', updated_at=$1 WHERE id=$2",
                    now, row["id"],
                )
                receipt_count += 1
            except Exception as e:
                print(f"   ✗ Reçu {row['reference']}: {e}")
    finally:
        await conn.close()
    print(f"   ✓ {receipt_count} reçus générés")
    return receipt_count


if __name__ == "__main__":
    # Flush Redis pour effacer les rate limits de la session précédente
    import redis as _redis
    _redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    _r = _redis.from_url(_redis_url)
    _r.flushdb()
    print("🗑  Redis vidé (rate limits effacés)")
    _r.close()

    # Phase 1 : setup DB dans un event loop isolé (évite conflit asyncpg/httpx)
    asyncio.run(setup_db())
    # Phase 2 : seed via API dans un event loop frais
    asyncio.run(seed_via_api())
    # Phase 3 : génération des reçus fiscaux (event loop frais)
    asyncio.run(generate_receipts_db())
