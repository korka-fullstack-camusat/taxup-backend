#!/usr/bin/env python3
"""
TAXUP — Script de données de test (seed)
=========================================
Comptes de test :
    ADMIN            admin@taxup.sn              admin        passer@123
    AGENT_DGID       agent_diallo@dgid.sn        agent_diallo passer@123
    AGENT_DGID       agent_sow@dgid.sn           agent_sow    passer@123
    AUDITEUR_FISCAL  auditeur_fall@taxup.sn      auditeur_fall passer@123
    AUDITEUR_FISCAL  auditeur_ndiaye@taxup.sn    auditeur_ndiaye passer@123
    OPERATEUR_MOBILE wave_sn@taxup.sn            wave_sn      passer@123
    OPERATEUR_MOBILE orangemoney@taxup.sn        orangemoney  passer@123
    OPERATEUR_MOBILE freemoney@taxup.sn          freemoney    passer@123
    CITOYEN          amadou_ba@gmail.com         amadou_ba    passer@123
    CITOYEN          fatou_mbaye@gmail.com       fatou_mbaye  passer@123
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

# ── Config ────────────────────────────────────────────────────────────────────────────────

BASE_URL = os.getenv("SEED_API_URL", "http://localhost:8000/api/v1")
PASSWORD = "passer@123"
ADMIN_USERNAME = "admin"

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

# ── Helpers ────────────────────────────────────────────────────────────────────────────────

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

# ── Seed principal ─────────────────────────────────────────────────────────────────────

async def run() -> None:
    db_url = get_db_url()
    print(f"📦 Connexion DB : {db_url[:50]}...")
    conn = await asyncpg.connect(db_url)

    try:
        # 1. Nettoyage
        print("🗑  Nettoyage des tables...")
        await conn.execute("""
            TRUNCATE notifications, fraud_alerts, audits, fiscal_receipts, transactions, users
            RESTART IDENTITY CASCADE
        """)

        # 2. Admin directement en base
        print("👤 Création de l'admin...")
        admin_id = uuid.uuid4()
        await conn.execute("""
            INSERT INTO users (id, username, email, hashed_password, full_name, role,
                               phone_number, organization, is_active, is_verified,
                               api_key, created_at, updated_at)
            VALUES ($1,$2,$3,$4,$5,'ADMIN',$6,$7,true,true,$8,NOW(),NOW())
        """,
            admin_id, ADMIN_USERNAME, "admin@taxup.sn",
            get_password_hash(PASSWORD),
            "Administrateur Système", "+224600000001", "TAXUP",
            secrets.token_urlsafe(32),
        )
        print(f"   ✓ admin@taxup.sn  (username=admin, mdp={PASSWORD})")

    finally:
        await conn.close()

    # 3. Autres utilisateurs via API
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=60) as client:
        print("\n🔑 Connexion admin...")
        r = await client.post("/auth/login", json={"username": ADMIN_USERNAME, "password": PASSWORD})
        if r.status_code != 200:
            raise RuntimeError(f"Échec login admin : {r.status_code} — {r.text}")
        ah = {"Authorization": f"Bearer {r.json()['access_token']}"}
        print("   ✓ Connecté")

        print("\n👥 Création des utilisateurs...")
        other_users = [
            ("agent_diallo",    "agent_diallo@dgid.sn",      "Ibrahima Diallo",      "AGENT_DGID",       "+224600000002", "DGID — Bureau Conakry"),
            ("agent_sow",       "agent_sow@dgid.sn",         "Mariama Sow",          "AGENT_DGID",       "+224600000003", "DGID — Bureau Labé"),
            ("auditeur_fall",   "auditeur_fall@taxup.sn",    "Cheikh Fall",          "AUDITEUR_FISCAL",  "+224600000004", "Cellule Audit Fiscal"),
            ("auditeur_ndiaye", "auditeur_ndiaye@taxup.sn",  "Aissatou Ndiaye",      "AUDITEUR_FISCAL",  "+224600000005", "Cellule Audit Fiscal"),
            ("wave_sn",         "wave_sn@taxup.sn",          "Wave Sénégal",         "OPERATEUR_MOBILE", "+224600000010", "Wave Mobile Money"),
            ("orangemoney",     "orangemoney@taxup.sn",       "Orange Money Guinée",  "OPERATEUR_MOBILE", "+224600000011", "Orange Money SA"),
            ("freemoney",       "freemoney@taxup.sn",         "Free Money",           "OPERATEUR_MOBILE", "+224600000012", "Free Guinée"),
            ("amadou_ba",       "amadou_ba@gmail.com",        "Amadou Ba",            "CITOYEN",          "+224620000001", None),
            ("fatou_mbaye",     "fatou_mbaye@gmail.com",      "Fatou Mbaye",          "CITOYEN",          "+224620000002", None),
        ]

        operator_ids = {}
        for (uname, email, fname, role, phone, org) in other_users:
            payload = {"username": uname, "email": email, "password": PASSWORD,
                       "full_name": fname, "role": role, "phone_number": phone}
            if org:
                payload["organization"] = org
            r = await client.post("/users", headers=ah, json=payload)
            if r.status_code not in (200, 201):
                print(f"   ✗ {uname} : {r.status_code} — {r.text[:120]}")
                continue
            print(f"   ✓ {role:<20} {email}  (username={uname}, mdp={PASSWORD})")

        # IDs des opérateurs
        r_users = await client.get("/users", headers=ah, params={"page_size": 50})
        if r_users.status_code == 200:
            for u in r_users.json().get("items", []):
                operator_ids[u["username"]] = u["id"]

        # Tokens agents pour audits
        agents = [("agent_diallo", PASSWORD), ("agent_sow", PASSWORD),
                  ("auditeur_fall", PASSWORD), ("auditeur_ndiaye", PASSWORD)]
        agent_tokens = []
        for (uname, pwd) in agents:
            r = await client.post("/auth/login", json={"username": uname, "password": pwd})
            if r.status_code == 200:
                agent_tokens.append(r.json()["access_token"])

    # 4. LOT A : Transactions normales — injection directe en base
    print("\n💸 LOT A — Transactions normales (40 par opérateur)...")
    conn_a = await asyncpg.connect(get_db_url())
    tx_ids: list[str] = []
    try:
        for uname in ["wave_sn", "orangemoney", "freemoney"]:
            op_uuid_str = operator_ids.get(uname)
            if not op_uuid_str:
                print(f"   ✗ UUID introuvable pour {uname}")
                continue
            count = 0
            for _ in range(40):
                tx_id = uuid.uuid4()
                past = rand_past_date(days_ago_min=2, days_ago_max=120)
                amount = random.choice(NORMAL_AMOUNTS)
                sender = rand_phone()
                receiver = random.choice([p for p in PHONES if p != sender])
                await conn_a.execute("""
                    INSERT INTO transactions (id, reference, operator_id, amount, currency,
                        transaction_type, sender_phone, receiver_phone,
                        sender_name, receiver_name, status, transaction_date, created_at, updated_at)
                    VALUES ($1,$2,$3,$4,'XOF',$5,$6,$7,$8,$9,'COMPLETED',$10,$11,$11)
                """,
                    tx_id, rand_ref("TXN"), uuid.UUID(op_uuid_str),
                    Decimal(str(amount)),
                    random.choices(TX_TYPES, weights=TX_TYPE_WEIGHTS)[0],
                    sender, receiver,
                    f"Émetteur {random.randint(100,999)}",
                    f"Destinataire {random.randint(100,999)}",
                    rand_past_date(2, 120), past,
                )
                tx_ids.append(str(tx_id))
                count += 1
            print(f"   ✓ {uname} : {count}/40 transactions")
    finally:
        await conn_a.close()

    # 5. LOT B : Transactions suspectes + alertes fraude
    print("\n🚨 LOT B — Transactions suspectes (25 par opérateur)...")
    conn2 = await asyncpg.connect(get_db_url())
    suspicious_tx_ids: list[str] = []
    try:
        for uname in ["wave_sn", "orangemoney", "freemoney"]:
            op_uuid_str = operator_ids.get(uname)
            if not op_uuid_str:
                continue
            count = 0
            for _ in range(25):
                tx_id = uuid.uuid4()
                past = rand_past_date(days_ago_min=3, days_ago_max=30)
                amount = random.choice(SUSPICIOUS_AMOUNTS)
                sender = rand_phone()
                receiver = random.choice([p for p in PHONES if p != sender])
                await conn2.execute("""
                    INSERT INTO transactions (id, reference, operator_id, amount, currency,
                        transaction_type, sender_phone, receiver_phone,
                        sender_name, receiver_name, status, transaction_date, created_at, updated_at)
                    VALUES ($1,$2,$3,$4,'XOF',$5,$6,$7,$8,$9,'UNDER_REVIEW',$10,$11,$11)
                """,
                    tx_id, rand_ref("TX-SUSP"), uuid.UUID(op_uuid_str),
                    Decimal(str(amount)),
                    random.choices(TX_TYPES, weights=TX_TYPE_WEIGHTS)[0],
                    sender, receiver,
                    f"Suspect {random.randint(100,999)}",
                    f"Destinataire {random.randint(100,999)}",
                    rand_past_date(3, 90), past,
                )
                risk = min(1.0, amount / 2_000_000)
                await conn2.execute("""
                    INSERT INTO fraud_alerts (id, transaction_id, fraud_type, status,
                        risk_score, description, details, detected_at)
                    VALUES ($1,$2,'LARGE_AMOUNT','DETECTED',$3,$4,$5,$6)
                """,
                    uuid.uuid4(), tx_id, round(risk, 4),
                    f"Montant {amount:,.0f} XOF dépasse 1 000 000 XOF",
                    f'{{"amount": {amount}, "threshold": 1000000}}', past,
                )
                if random.random() < 0.6:
                    cum = amount + random.randint(200_000, 800_000)
                    await conn2.execute("""
                        INSERT INTO fraud_alerts (id, transaction_id, fraud_type, status,
                            risk_score, description, details, detected_at)
                        VALUES ($1,$2,'STRUCTURING','DETECTED',$3,$4,$5,$6)
                    """,
                        uuid.uuid4(), tx_id, round(min(1.0, cum/1_000_000), 4),
                        f"Cumulé {cum:,.0f} XOF sur 24h — structuring probable",
                        f'{{"cumulative_amount": {cum}}}', past,
                    )
                suspicious_tx_ids.append(str(tx_id))
                count += 1
            print(f"   ✓ {uname} : {count}/25 transactions suspectes")
    finally:
        await conn2.close()

    # 6. Audits via API
    print("\n🔍 Création des audits...")
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=60) as client:
        all_tx = tx_ids + suspicious_tx_ids
        audit_count = 0
        for i, (title, anom) in enumerate(AUDIT_TITLES):
            if not agent_tokens:
                break
            agt_h = {"Authorization": f"Bearer {agent_tokens[i % len(agent_tokens)]}"}
            payload: dict = {"title": title,
                             "description": f"Description : {title.lower()}. Analyse en cours.",
                             "anomaly_type": anom}
            if all_tx and i < len(all_tx):
                payload["transaction_id"] = all_tx[i]
            r = await client.post("/audits", headers=agt_h, json=payload)
            if r.status_code == 201:
                audit_count += 1
        print(f"   ✓ {audit_count}/{len(AUDIT_TITLES)} audits créés")

    # 7. Résumé
    total = len(tx_ids) + len(suspicious_tx_ids)
    print(f"\n{'='*65}")
    print("✅ BASE DE DONNÉES INITIALISÉE AVEC SUCCÈS")
    print(f"{'='*65}")
    print(f"  Transactions normales   : {len(tx_ids)}")
    print(f"  Transactions suspectes  : {len(suspicious_tx_ids)}")
    print(f"  Total transactions      : {total}")
    print(f"  Audits créés            : {audit_count}")
    print()
    print("  Comptes de test (mot de passe unique : passer@123) :")
    print(f"  {'Rôle':<20} {'Email':<30} {'Username'}")
    print(f"  {'-'*70}")
    rows = [
        ("ADMIN",            "admin@taxup.sn",           "admin"),
        ("AGENT_DGID",       "agent_diallo@dgid.sn",     "agent_diallo"),
        ("AGENT_DGID",       "agent_sow@dgid.sn",        "agent_sow"),
        ("AUDITEUR_FISCAL",  "auditeur_fall@taxup.sn",   "auditeur_fall"),
        ("AUDITEUR_FISCAL",  "auditeur_ndiaye@taxup.sn", "auditeur_ndiaye"),
        ("OPERATEUR_MOBILE", "wave_sn@taxup.sn",         "wave_sn"),
        ("OPERATEUR_MOBILE", "orangemoney@taxup.sn",     "orangemoney"),
        ("OPERATEUR_MOBILE", "freemoney@taxup.sn",       "freemoney"),
        ("CITOYEN",          "amadou_ba@gmail.com",      "amadou_ba"),
        ("CITOYEN",          "fatou_mbaye@gmail.com",    "fatou_mbaye"),
    ]
    for (role, email, uname) in rows:
        print(f"  {role:<20} {email:<30} {uname}")
    print(f"  Mot de passe commun : passer@123")
    print(f"{'='*65}\n")


if __name__ == "__main__":
    asyncio.run(run())
