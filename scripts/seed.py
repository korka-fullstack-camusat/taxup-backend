#!/usr/bin/env python3
"""
TAXUP — Script de données de test (seed)
=========================================
Stratégie :
  1. Insère l'admin directement en base.
  2. Crée tous les autres utilisateurs via l'API.
  3. LOT A : Transactions normales (petits montants) via API
             → fraud_service ne déclenchera pas car velocity faible
             → reçus fiscaux à 18% générés automatiquement
  4. LOT B : Transactions suspectes injectées directement en base
             avec created_at dans le passé (hors fenêtre velocity)
             → fraud_service déclenché manuellement sur ces tx
  5. Crée les audits via l'API.

Usage :
    docker compose exec api python scripts/seed.py

Comptes de test :
    ADMIN            admin@taxup.sn              Admin@2026!
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

# Numéros de téléphone simulés
PHONES = [
    "+224621000001", "+224621000002", "+224621000003", "+224621000004",
    "+224621000005", "+224621000006", "+224621000007", "+224621000008",
    "+224661000001", "+224661000002", "+224661000003", "+224661000004",
    "+221771000001", "+221771000002", "+221771000003",
]

TX_TYPES = ["TRANSFERT", "PAIEMENT", "RETRAIT", "DEPOT", "REMBOURSEMENT"]
TX_TYPE_WEIGHTS = [100, 30, 15, 15, 5]

# Montants "normaux" (< 500 000 XOF) → ne déclenchent pas LARGE_AMOUNT
NORMAL_AMOUNTS = [
    5_000, 7_500, 10_000, 15_000, 20_000,
    25_000, 100_000, 50_000, 75_000, 100_000,
    150_000, 200_000, 300_000, 400_000, 499_000,
]

# Montants "suspects" (≥ 1 000 000 XOF) → déclenchent LARGE_AMOUNT + STRUCTURING
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
    """Date dans le passé (entre days_ago_min et days_ago_max jours en arrière)."""
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

# ── Seed principal ────────────────────────────────────────────────────────────

async def run() -> None:
    db_url = get_db_url()
    print(f"📦 Connexion DB : {db_url[:50]}...")
    conn = await asyncpg.connect(db_url)

    try:
        # ── 1. Nettoyage ────────────────────────────────────────────────────
        print("🗑  Nettoyage des tables...")
        await conn.execute("""
            TRUNCATE notifications, fraud_alerts, audits, fiscal_receipts, transactions, users
            RESTART IDENTITY CASCADE
        """)

        # ── 2. Création de l'admin directement en base ──────────────────────
        print("👤 Création de l'admin...")
        admin_id = uuid.uuid4()
        await conn.execute("""
            INSERT INTO users (id, username, email, hashed_password, full_name, role,
                               phone_number, organization, is_active, is_verified,
                               api_key, created_at, updated_at)
            VALUES ($1,$2,$3,$4,$5,'ADMIN',$6,$7,true,true,$8,NOW(),NOW())
        """,
            admin_id, ADMIN_USERNAME, "admin@taxup.sn",
            get_password_hash(ADMIN_PASSWORD),
            "Administrateur Système", "+224600000001", "TAXUP",
            secrets.token_urlsafe(32),
        )
        print(f"   ✓ admin@taxup.sn créé (id={admin_id})")

    finally:
        await conn.close()

    # ── 3. Appels API ────────────────────────────────────────────────────────
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=60) as client:

        # Login admin
        print("\n🔑 Connexion admin...")
        r = await client.post("/auth/login", json={
            "username": ADMIN_USERNAME,
            "password": ADMIN_PASSWORD,
        })
        if r.status_code != 200:
            raise RuntimeError(f"Échec login admin : {r.status_code} — {r.text}")
        admin_token = r.json()["access_token"]
        ah = {"Authorization": f"Bearer {admin_token}"}
        print("   ✓ Connecté en tant qu'admin")

        # ── 4. Création des utilisateurs ─────────────────────────────────────
        print("\n👥 Création des utilisateurs...")
        other_users = [
            ("agent_diallo",   "agent_diallo@dgid.sn",       "Ibrahima Diallo",        "AGENT_DGID",       "+224600000002", "DGID — Bureau Conakry",  "Agent@2026!"),
            ("agent_sow",      "agent_sow@dgid.sn",          "Mariama Sow",             "AGENT_DGID",       "+224600000003", "DGID — Bureau Labé",     "Agent@2026!"),
            ("auditeur_fall",  "auditeur_fall@taxup.sn",     "Cheikh Fall",             "AUDITEUR_FISCAL",  "+224600000004", "Cellule Audit Fiscal",   "Audit@2026!"),
            ("auditeur_ndiaye","auditeur_ndiaye@taxup.sn",   "Aissatou Ndiaye",         "AUDITEUR_FISCAL",  "+224600000005", "Cellule Audit Fiscal",   "Audit@2026!"),
            ("wave_sn",        "wave_sn@taxup.sn",           "Wave Sénégal",            "OPERATEUR_MOBILE", "+224600000010", "Wave Mobile Money",      "Oper@2026!"),
            ("orangemoney",    "orangemoney@taxup.sn",        "Orange Money Guinée",     "OPERATEUR_MOBILE", "+224600000011", "Orange Money SA",        "Oper@2026!"),
            ("freemoney",      "freemoney@taxup.sn",          "Free Money",              "OPERATEUR_MOBILE", "+224600000012", "Free Guinée",            "Oper@2026!"),
            ("amadou_ba",      "amadou_ba@gmail.com",         "Amadou Ba",               "CITOYEN",          "+224620000001", None,                     "Citoyen@2026!"),
            ("fatou_mbaye",    "fatou_mbaye@gmail.com",       "Fatou Mbaye",             "CITOYEN",          "+224620000002", None,                     "Citoyen@2026!"),
        ]

        operator_ids = {}  # username → UUID

        for (uname, email, fname, role, phone, org, pwd) in other_users:
            payload = {
                "username": uname, "email": email, "password": pwd,
                "full_name": fname, "role": role, "phone_number": phone,
            }
            if org:
                payload["organization"] = org

            r = await client.post("/users", headers=ah, json=payload)
            if r.status_code not in (200, 201):
                print(f"   ✗ {uname} : {r.status_code} — {r.text[:120]}")
                continue
            print(f"   ✓ {role:<20} {email}")

        # Récupérer les IDs des opérateurs
        r_users = await client.get("/users", headers=ah, params={"page_size": 50})
        if r_users.status_code == 200:
            items = r_users.json().get("items", [])
            for u in items:
                operator_ids[u["username"]] = u["id"]

        # ── 5a. LOT A : Transactions normales via API ─────────────────────────
        # Petits montants espacés → pas de velocity alert → génèrent des reçus
        print("\n💸 LOT A — Transactions normales (40 par opérateur, petits montants)...")
        operators = [
            ("wave_sn",     "Oper@2026!"),
            ("orangemoney", "Oper@2026!"),
            ("freemoney",   "Oper@2026!"),
        ]

        tx_ids: list[str] = []
        user_tokens: dict[str, str] = {}

        for (uname, pwd) in operators:
            r = await client.post("/auth/login", json={"username": uname, "password": pwd})
            if r.status_code != 200:
                print(f"   ✗ Login {uname} : {r.status_code}")
                continue
            op_token = r.json()["access_token"]
            op_h = {"Authorization": f"Bearer {op_token}"}
            user_tokens[uname] = op_token

            count = 0
            for _ in range(200):
                sender = rand_phone()
                receiver = random.choice([p for p in PHONES if p != sender])
                # Montants petits pour éviter LARGE_AMOUNT → reçus générés
                amount = random.choice(NORMAL_AMOUNTS)
                # Date transaction dans le passé lointain (> 2 jours)
                tx_date = rand_past_date(days_ago_min=2, days_ago_max=120)
                r2 = await client.post("/transactions", headers=op_h, json={
                    "amount": str(float(amount)),
                    "currency": "XOF",
                    "transaction_type": random.choices(TX_TYPES, weights=TX_TYPE_WEIGHTS)[0],
                    "sender_phone": sender,
                    "receiver_phone": receiver,
                    "sender_name": f"Émetteur {random.randint(100,999)}",
                    "receiver_name": f"Destinataire {random.randint(100,999)}",
                    "transaction_date": tx_date.isoformat(),
                })
                if r2.status_code == 201:
                    tx_ids.append(r2.json()["id"])
                    count += 1
            print(f"   ✓ {uname} : {count}/40 transactions normales créées")

        # ── 5b. LOT B : Transactions suspectes directement en base ───────────
        # Gros montants + created_at dans le passé lointain (> 2h)
        # → fraud_service déclenché manuellement ; velocity ne se cumule pas
        print("\n🚨 LOT B — Injection transactions suspectes en base (25 par opérateur)...")
        conn2 = await asyncpg.connect(get_db_url())
        try:
            suspicious_tx_ids = []
            operator_usernames = ["wave_sn", "orangemoney", "freemoney"]

            for uname in operator_usernames:
                op_uuid_str = operator_ids.get(uname)
                if not op_uuid_str:
                    print(f"   ✗ UUID introuvable pour {uname}")
                    continue

                count = 0
                for _ in range(25):
                    tx_id = uuid.uuid4()
                    # created_at entre 3 et 30 jours en arrière → hors fenêtre velocity (60 min)
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
                            $1,$2,$3,$4,'XOF',
                            $5,$6,$7,
                            $8,$9,'UNDER_REVIEW',
                            $10,$11,$11
                        )
                    """,
                        tx_id,
                        ref,
                        uuid.UUID(op_uuid_str),
                        Decimal(str(amount)),
                        random.choices(TX_TYPES, weights=TX_TYPE_WEIGHTS)[0],
                        sender, receiver,
                        f"Suspect {random.randint(100,999)}",
                        f"Destinataire {random.randint(100,999)}",
                        tx_date,
                        past_created_at,
                    )

                    # Insérer les alertes fraude correspondantes
                    # 1. LARGE_AMOUNT (systématique pour ≥ 1M)
                    risk_large = min(1.0, amount / 2_000_000)
                    await conn2.execute("""
                        INSERT INTO fraud_alerts (id, transaction_id, fraud_type, status, risk_score, description, details, detected_at)
                        VALUES ($1,$2,'LARGE_AMOUNT','DETECTED',$3,$4,$5,$6)
                    """,
                        uuid.uuid4(), tx_id,
                        round(risk_large, 4),
                        f"Montant {amount:,.0f} XOF dépasse le seuil de 1 000 000 XOF",
                        f'{{"amount": {amount}, "threshold": 1000000}}',
                        past_created_at,
                    )

                    # 2. STRUCTURING (aléatoire, ~60%)
                    if random.random() < 0.6:
                        cumulative = amount + random.randint(200_000, 800_000)
                        risk_struct = min(1.0, cumulative / 1_000_000)
                        await conn2.execute("""
                            INSERT INTO fraud_alerts (id, transaction_id, fraud_type, status, risk_score, description, details, detected_at)
                            VALUES ($1,$2,'STRUCTURING','DETECTED',$3,$4,$5,$6)
                        """,
                            uuid.uuid4(), tx_id,
                            round(risk_struct, 4),
                            f"Montant cumulé {cumulative:,.0f} XOF sur 24h — structuring probable",
                            f'{{"cumulative_amount": {cumulative}, "threshold": 500000}}',
                            past_created_at,
                        )

                    # 3. ROUND_TRIPPING (~30%)
                    if random.random() < 0.3:
                        await conn2.execute("""
                            INSERT INTO fraud_alerts (id, transaction_id, fraud_type, status, risk_score, description, details, detected_at)
                            VALUES ($1,$2,'ROUND_TRIPPING','DETECTED',0.85,$3,$4,$5)
                        """,
                            uuid.uuid4(), tx_id,
                            "Transaction aller-retour détectée entre les mêmes parties",
                            f'{{"reverse_count": 1, "window_hours": 24}}',
                            past_created_at,
                        )

                    suspicious_tx_ids.append(str(tx_id))
                    count += 1

                print(f"   ✓ {uname} : {count}/25 transactions suspectes injectées")

        finally:
            await conn2.close()

        # ── 6. Login agents → audits ─────────────────────────────────────────
        print("\n🔍 Création des audits...")
        agents = [
            ("agent_diallo",   "Agent@2026!"),
            ("agent_sow",      "Agent@2026!"),
            ("auditeur_fall",  "Audit@2026!"),
            ("auditeur_ndiaye","Audit@2026!"),
        ]
        agent_tokens = []
        for (uname, pwd) in agents:
            r = await client.post("/auth/login", json={"username": uname, "password": pwd})
            if r.status_code == 200:
                agent_tokens.append(r.json()["access_token"])
                user_tokens[uname] = r.json()["access_token"]

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
            # Lier à une transaction existante pour les premiers audits
            if all_tx_for_audit and i < len(all_tx_for_audit):
                payload["transaction_id"] = all_tx_for_audit[i]
            r = await client.post("/audits", headers=agt_h, json=payload)
            if r.status_code == 201:
                audit_count += 1
        print(f"   ✓ {audit_count}/{len(AUDIT_TITLES)} audits créés")

        # ── 7. Notifications pour citoyen et opérateurs ───────────────────────
        print("\n🔔 Vérification des notifications...")
        for (uname, pwd) in [("amadou_ba", "Citoyen@2026!"), ("wave_sn", "Oper@2026!")]:
            r = await client.post("/auth/login", json={"username": uname, "password": pwd})
            if r.status_code == 200:
                user_tokens[uname] = r.json()["access_token"]

        total_tx = len(tx_ids) + len(suspicious_tx_ids)

        # ── 8. Résumé ─────────────────────────────────────────────────────────
        print(f"\n{'='*65}")
        print("✅ BASE DE DONNÉES INITIALISÉE AVEC SUCCÈS")
        print(f"{'='*65}")
        print(f"  Transactions normales   : ~{len(tx_ids)} (reçus fiscaux 18%)")
        print(f"  Transactions suspectes  : ~{len(suspicious_tx_ids)} (alertes fraude)")
        print(f"  Total transactions      : ~{total_tx}")
        print(f"  Audits créés            : {audit_count}")
        print(f"  (Reçus & alertes fraude générés automatiquement en arrière-plan)")
        print()
        print("  Comptes de test :")
        print(f"  {'Rôle':<20} {'Email':<30} {'Mot de passe'}")
        print(f"  {'-'*70}")
        rows = [
            ("ADMIN",            "admin@taxup.sn",           "Admin@2026!"),
            ("AGENT_DGID",       "agent_diallo@dgid.sn",     "Agent@2026!"),
            ("AGENT_DGID",       "agent_sow@dgid.sn",        "Agent@2026!"),
            ("AUDITEUR_FISCAL",  "auditeur_fall@taxup.sn",   "Audit@2026!"),
            ("AUDITEUR_FISCAL",  "auditeur_ndiaye@taxup.sn", "Audit@2026!"),
            ("OPERATEUR_MOBILE", "wave_sn@taxup.sn",         "Oper@2026!"),
            ("OPERATEUR_MOBILE", "orangemoney@taxup.sn",     "Oper@2026!"),
            ("OPERATEUR_MOBILE", "freemoney@taxup.sn",       "Oper@2026!"),
            ("CITOYEN",          "amadou_ba@gmail.com",      "Citoyen@2026!"),
            ("CITOYEN",          "fatou_mbaye@gmail.com",    "Citoyen@2026!"),
        ]
        for (role, email, pwd) in rows:
            print(f"  {role:<20} {email:<30} {pwd}")
        print(f"{'='*65}\n")


if __name__ == "__main__":
    asyncio.run(run())
