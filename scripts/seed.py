#!/usr/bin/env python3
"""
TAXUP — Script de données de test (seed)
=========================================
Insertion directe en base (asyncpg) — aucun appel HTTP.

Usage :
    docker compose run --rm api python scripts/seed.py

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

from app.core.security import get_password_hash

# ── Config ────────────────────────────────────────────────────────────────────

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
    25_000, 50_000, 75_000, 100_000,
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

def get_db_url() -> str:
    url = os.getenv("DATABASE_URL", "")
    if not url:
        raise RuntimeError("DATABASE_URL n'est pas définie.")
    return (
        url.replace("postgresql+asyncpg://", "postgresql://")
           .replace("postgres://", "postgresql://")
    )

def rand_past_date(days_min: int = 1, days_max: int = 180) -> datetime:
    delta = random.randint(days_min * 1440, days_max * 1440)
    return datetime.now(timezone.utc) - timedelta(minutes=delta)

def rand_phone() -> str:
    return random.choice(PHONES)

def rand_ref(prefix: str = "TXN") -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")[:18]
    return f"{prefix}-{ts}-{secrets.token_hex(3).upper()}"

# ── Seed ───────────────────────────────────────────────────────────────────────

async def run() -> None:
    db_url = get_db_url()
    print(f"📦 Connexion DB : {db_url[:55]}...")
    conn = await asyncpg.connect(db_url)

    try:
        # ── 1. Nettoyage ────────────────────────────────────────────────
        print("🗑  Nettoyage des tables...")
        await conn.execute("""
            TRUNCATE notifications, fraud_alerts, audits,
                     fiscal_receipts, transactions, users
            RESTART IDENTITY CASCADE
        """)

        # ── 2. Utilisateurs ─────────────────────────────────────────────
        print("👥 Création des utilisateurs...")

        all_users = [
            # (username, email, full_name, role, phone, org, password)
            ("admin",          "admin@taxup.sn",           "Administrateur Système", "ADMIN",           "+224600000001", "TAXUP",                  "Admin@2026!"),
            ("agent_diallo",   "agent_diallo@dgid.sn",     "Ibrahima Diallo",         "AGENT_DGID",      "+224600000002", "DGID — Bureau Conakry",   "Agent@2026!"),
            ("agent_sow",      "agent_sow@dgid.sn",        "Mariama Sow",             "AGENT_DGID",      "+224600000003", "DGID — Bureau Labé",      "Agent@2026!"),
            ("auditeur_fall",  "auditeur_fall@taxup.sn",   "Cheikh Fall",             "AUDITEUR_FISCAL", "+224600000004", "Cellule Audit Fiscal",    "Audit@2026!"),
            ("auditeur_ndiaye","auditeur_ndiaye@taxup.sn", "Aissatou Ndiaye",         "AUDITEUR_FISCAL", "+224600000005", "Cellule Audit Fiscal",    "Audit@2026!"),
            ("wave_sn",        "wave_sn@taxup.sn",         "Wave Sénégal",            "OPERATEUR_MOBILE","+224600000010", "Wave Mobile Money",       "Oper@2026!"),
            ("orangemoney",    "orangemoney@taxup.sn",     "Orange Money Guinée",     "OPERATEUR_MOBILE","+224600000011", "Orange Money SA",         "Oper@2026!"),
            ("freemoney",      "freemoney@taxup.sn",       "Free Money",              "OPERATEUR_MOBILE","+224600000012", "Free Guinée",             "Oper@2026!"),
            ("amadou_ba",      "amadou_ba@gmail.com",      "Amadou Ba",               "CITOYEN",         "+224620000001", None,                      "Citoyen@2026!"),
            ("fatou_mbaye",    "fatou_mbaye@gmail.com",    "Fatou Mbaye",             "CITOYEN",         "+224620000002", None,                      "Citoyen@2026!"),
        ]

        user_ids: dict[str, uuid.UUID] = {}

        for (uname, email, fname, role, phone, org, pwd) in all_users:
            uid = uuid.uuid4()
            user_ids[uname] = uid
            await conn.execute("""
                INSERT INTO users (
                    id, username, email, hashed_password, full_name, role,
                    phone_number, organization, is_active, is_verified,
                    api_key, created_at, updated_at
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,true,true,$9,NOW(),NOW())
            """,
                uid, uname, email,
                get_password_hash(pwd),
                fname, role, phone, org,
                secrets.token_urlsafe(32),
            )
            print(f"   ✓ {role:<20} {email}")

        # ── 3. LOT A — Transactions normales (40 par opérateur) ─────────────
        print("\n💸 LOT A — Transactions normales (40 par opérateur)...")
        operators = ["wave_sn", "orangemoney", "freemoney"]
        tx_ids: list[uuid.UUID] = []

        for op in operators:
            op_id = user_ids[op]
            count = 0
            for _ in range(40):
                tx_id = uuid.uuid4()
                sender = rand_phone()
                receiver = random.choice([p for p in PHONES if p != sender])
                amount = Decimal(str(random.choice(NORMAL_AMOUNTS)))
                tx_date = rand_past_date(2, 120)
                created_at = rand_past_date(2, 120)

                await conn.execute("""
                    INSERT INTO transactions (
                        id, reference, operator_id, amount, currency,
                        transaction_type, sender_phone, receiver_phone,
                        sender_name, receiver_name, status,
                        transaction_date, created_at, updated_at
                    ) VALUES (
                        $1,$2,$3,$4,'XOF',$5,$6,$7,$8,$9,'COMPLETED',$10,$11,$11
                    )
                """,
                    tx_id,
                    rand_ref("TXN"),
                    op_id, amount,
                    random.choices(TX_TYPES, weights=TX_TYPE_WEIGHTS)[0],
                    sender, receiver,
                    f"Émetteur {random.randint(100,999)}",
                    f"Destinataire {random.randint(100,999)}",
                    tx_date, created_at,
                )
                tx_ids.append(tx_id)
                count += 1
            print(f"   ✓ {op:<15} : {count}/40 transactions normales")

        # ── 4. LOT B — Transactions suspectes + alertes fraude ────────────
        print("\n🚨 LOT B — Transactions suspectes (25 par opérateur) + alertes fraude...")
        suspicious_ids: list[uuid.UUID] = []

        for op in operators:
            op_id = user_ids[op]
            count = 0
            for _ in range(25):
                tx_id = uuid.uuid4()
                past = rand_past_date(3, 30)
                tx_date = rand_past_date(3, 90)
                amount = Decimal(str(random.choice(SUSPICIOUS_AMOUNTS)))
                sender = rand_phone()
                receiver = random.choice([p for p in PHONES if p != sender])

                await conn.execute("""
                    INSERT INTO transactions (
                        id, reference, operator_id, amount, currency,
                        transaction_type, sender_phone, receiver_phone,
                        sender_name, receiver_name, status,
                        transaction_date, created_at, updated_at
                    ) VALUES (
                        $1,$2,$3,$4,'XOF',$5,$6,$7,$8,$9,'UNDER_REVIEW',$10,$11,$11
                    )
                """,
                    tx_id, rand_ref("TX-SUSP"), op_id, amount,
                    random.choices(TX_TYPES, weights=TX_TYPE_WEIGHTS)[0],
                    sender, receiver,
                    f"Suspect {random.randint(100,999)}",
                    f"Destinataire {random.randint(100,999)}",
                    tx_date, past,
                )

                # LARGE_AMOUNT (systématique)
                amt_int = int(amount)
                risk = round(min(1.0, amt_int / 2_000_000), 4)
                await conn.execute("""
                    INSERT INTO fraud_alerts (
                        id, transaction_id, fraud_type, status,
                        risk_score, description, details, detected_at
                    ) VALUES ($1,$2,'LARGE_AMOUNT','DETECTED',$3,$4,$5,$6)
                """,
                    uuid.uuid4(), tx_id, risk,
                    f"Montant {amt_int:,} XOF dépasse le seuil de 1 000 000 XOF",
                    f'{{"amount": {amt_int}, "threshold": 1000000}}',
                    past,
                )

                # STRUCTURING (~60%)
                if random.random() < 0.6:
                    cum = amt_int + random.randint(200_000, 800_000)
                    await conn.execute("""
                        INSERT INTO fraud_alerts (
                            id, transaction_id, fraud_type, status,
                            risk_score, description, details, detected_at
                        ) VALUES ($1,$2,'STRUCTURING','DETECTED',$3,$4,$5,$6)
                    """,
                        uuid.uuid4(), tx_id,
                        round(min(1.0, cum / 1_000_000), 4),
                        f"Montant cumulé {cum:,} XOF sur 24h — structuring probable",
                        f'{{"cumulative_amount": {cum}, "threshold": 500000}}',
                        past,
                    )

                # ROUND_TRIPPING (~30%)
                if random.random() < 0.3:
                    await conn.execute("""
                        INSERT INTO fraud_alerts (
                            id, transaction_id, fraud_type, status,
                            risk_score, description, details, detected_at
                        ) VALUES ($1,$2,'ROUND_TRIPPING','DETECTED',0.85,$3,$4,$5)
                    """,
                        uuid.uuid4(), tx_id,
                        "Transaction aller-retour détectée entre les mêmes parties",
                        '{"reverse_count": 1, "window_hours": 24}',
                        past,
                    )

                suspicious_ids.append(tx_id)
                count += 1
            print(f"   ✓ {op:<15} : {count}/25 transactions suspectes")

        # ── 5. Audits ─────────────────────────────────────────────────────
        print("\n🔍 Création des audits...")
        all_tx = tx_ids + suspicious_ids
        auditors = [
            user_ids["agent_diallo"],
            user_ids["agent_sow"],
            user_ids["auditeur_fall"],
            user_ids["auditeur_ndiaye"],
        ]

        audit_count = 0
        for i, (title, anom) in enumerate(AUDIT_TITLES):
            audit_id = uuid.uuid4()
            audit_number = rand_ref("AUD")
            auditor_id = auditors[i % len(auditors)]
            tx_id = all_tx[i] if i < len(all_tx) else None
            created_at = rand_past_date(1, 60)

            await conn.execute("""
                INSERT INTO audits (
                    id, audit_number, auditor_id, transaction_id,
                    anomaly_type, status, title, description,
                    created_at, updated_at
                ) VALUES ($1,$2,$3,$4,$5,'OUVERT',$6,$7,$8,$8)
            """,
                audit_id, audit_number, auditor_id, tx_id,
                anom, title,
                f"Description détaillée : {title.lower()}. Analyse en cours.",
                created_at,
            )
            audit_count += 1

        print(f"   ✓ {audit_count}/{len(AUDIT_TITLES)} audits créés")

        # ── 6. Résumé ─────────────────────────────────────────────────────
        total_tx = len(tx_ids) + len(suspicious_ids)
        print(f"\n{'='*65}")
        print("✅ BASE DE DONNÉES INITIALISÉE AVEC SUCCÈS")
        print(f"{'='*65}")
        print(f"  Transactions normales   : {len(tx_ids)}")
        print(f"  Transactions suspectes  : {len(suspicious_ids)} (avec alertes fraude)")
        print(f"  Total transactions      : {total_tx}")
        print(f"  Audits créés            : {audit_count}")
        print()
        print("  Comptes de test :")
        print(f"  {'Rôle':<20} {'Email':<32} {'Mot de passe'}")
        print(f"  {'-'*72}")
        for (uname, email, _, role, _, _, pwd) in all_users:
            print(f"  {role:<20} {email:<32} {pwd}")
        print(f"{'='*65}\n")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(run())
