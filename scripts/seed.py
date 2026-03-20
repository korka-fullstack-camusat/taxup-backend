#!/usr/bin/env python3
"""
TAXUP — Script de données de test (seed)
=========================================
Crée des utilisateurs, transactions, reçus, audits, alertes de fraude
et notifications pour tester toutes les fonctionnalités par rôle.

Usage :
    # Depuis la racine du backend (Docker) — service = "api" :
    docker compose exec api python scripts/seed.py

    # En local (après avoir configuré DATABASE_URL) :
    DATABASE_URL=postgresql://... python scripts/seed.py

Comptes créés :
    ADMIN          admin@taxup.sn        / Admin@2026
    AGENT_DGID     agent.diallo@dgid.sn  / Agent@2026
    AGENT_DGID     agent.sow@dgid.sn     / Agent@2026
    AUDITEUR       auditeur.fall@taxup.sn / Audit@2026
    AUDITEUR       auditeur.ndiaye@taxup.sn / Audit@2026
    OPERATEUR      wave@taxup.sn         / Oper@2026
    OPERATEUR      orangemoney@taxup.sn  / Oper@2026
    OPERATEUR      freemoney@taxup.sn    / Oper@2026
    CITOYEN        amadou.ba@gmail.com   / Cit@2026
    CITOYEN        fatou.mbaye@gmail.com / Cit@2026
"""

import asyncio
import os
import random
import uuid
import hashlib
import json
from datetime import datetime, timedelta, timezone

import asyncpg
import warnings
warnings.filterwarnings("ignore", ".*error reading bcrypt version.*")
from passlib.context import CryptContext

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ── Connexion ─────────────────────────────────────────────────────────────────

def get_db_url() -> str:
    url = os.getenv("DATABASE_URL", "")
    if not url:
        raise RuntimeError("DATABASE_URL n'est pas définie.")
    # asyncpg attend postgresql:// (pas postgresql+asyncpg://)
    return url.replace("postgresql+asyncpg://", "postgresql://").replace("postgres://", "postgresql://")


# ── Hachage mot de passe ──────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return _pwd.hash(plain)


# ── Helpers date ──────────────────────────────────────────────────────────────

def random_date(days_back: int = 180) -> datetime:
    delta = random.randint(0, days_back * 24 * 60)   # minutes
    return datetime.now(timezone.utc) - timedelta(minutes=delta)


def fiscal_period(dt: datetime) -> str:
    q = (dt.month - 1) // 3 + 1
    return f"{dt.year}-Q{q}"


# ── Données ───────────────────────────────────────────────────────────────────

USERS = [
    # (username, email, full_name, role, phone, organization, password)
    ("admin",            "admin@taxup.sn",             "Administrateur Système",    "ADMIN",            "+224600000001", "TAXUP",                    "Admin@2026"),
    ("agent.diallo",     "agent.diallo@dgid.sn",       "Ibrahima Diallo",           "AGENT_DGID",       "+224600000002", "DGID — Bureau Conakry",    "Agent@2026"),
    ("agent.sow",        "agent.sow@dgid.sn",          "Mariama Sow",               "AGENT_DGID",       "+224600000003", "DGID — Bureau Labé",       "Agent@2026"),
    ("auditeur.fall",    "auditeur.fall@taxup.sn",      "Cheikh Fall",               "AUDITEUR_FISCAL",  "+224600000004", "Cellule Audit Fiscal",     "Audit@2026"),
    ("auditeur.ndiaye",  "auditeur.ndiaye@taxup.sn",    "Aissatou Ndiaye",           "AUDITEUR_FISCAL",  "+224600000005", "Cellule Audit Fiscal",     "Audit@2026"),
    ("wave.sn",          "wave@taxup.sn",               "Wave Sénégal",              "OPERATEUR_MOBILE", "+224600000010", "Wave Mobile Money",        "Oper@2026"),
    ("orange.money.sn",  "orangemoney@taxup.sn",        "Orange Money Guinée",       "OPERATEUR_MOBILE", "+224600000011", "Orange Money SA",          "Oper@2026"),
    ("free.money.sn",    "freemoney@taxup.sn",          "Free Money",                "OPERATEUR_MOBILE", "+224600000012", "Free Guinée",              "Oper@2026"),
    ("amadou.ba",        "amadou.ba@gmail.com",         "Amadou Ba",                 "CITOYEN",          "+224620000001", None,                       "Cit@2026"),
    ("fatou.mbaye",      "fatou.mbaye@gmail.com",       "Fatou Mbaye",               "CITOYEN",          "+224620000002", None,                       "Cit@2026"),
]

TX_TYPES = ["TRANSFERT", "PAIEMENT", "RETRAIT", "DEPOT", "REMBOURSEMENT"]
TX_STATUSES = ["PENDING", "COMPLETED", "FAILED", "CANCELLED", "UNDER_REVIEW"]
TX_STATUS_WEIGHTS = [10, 60, 10, 8, 12]   # % de chaque statut

SENEGAL_PHONES = [
    "+221771234567", "+221781234567", "+221701234567",
    "+221751234567", "+221761234567", "+224621234567",
    "+224661234567", "+224671234567", "+224681234567",
]

FRAUD_TYPES = ["VELOCITY", "LARGE_AMOUNT", "ROUND_TRIPPING", "STRUCTURING", "UNUSUAL_PATTERN", "BLACKLISTED"]
FRAUD_STATUSES = ["DETECTED", "INVESTIGATING", "CONFIRMED", "FALSE_POSITIVE", "RESOLVED"]

ANOMALY_TYPES = ["MONTANT_SUSPECT", "FREQUENCE_ANORMALE", "IDENTITE_DOUTEUSE",
                 "DOUBLE_TRANSACTION", "EVASION_FISCALE", "BLANCHIMENT", "AUTRE"]
AUDIT_STATUSES = ["OUVERT", "EN_COURS", "RESOLU", "ESCALADE", "CLOS"]
AUDIT_PRIORITIES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]   # utilisé dans le titre — pas un champ BDD

NOTIF_TYPES = ["FRAUD_ALERT", "AUDIT_UPDATE", "RECEIPT_GENERATED", "SYSTEM", "TAX_COMPLIANCE"]


# ── Insertion principale ───────────────────────────────────────────────────────

async def run() -> None:
    url = get_db_url()
    print(f"Connexion à {url[:40]}...")
    conn = await asyncpg.connect(url)

    try:
        # ── Vider les tables dans l'ordre FK ────────────────────────────────
        print("Nettoyage des tables existantes...")
        await conn.execute("""
            TRUNCATE notifications, fraud_alerts, audits, fiscal_receipts, transactions, users
            RESTART IDENTITY CASCADE
        """)

        # ── Utilisateurs ────────────────────────────────────────────────────
        print("Création des utilisateurs...")
        user_ids: dict[str, uuid.UUID] = {}
        operator_ids: list[uuid.UUID] = []

        for (uname, email, full_name, role, phone, org, pwd) in USERS:
            uid = uuid.uuid4()
            user_ids[uname] = uid
            if role == "OPERATEUR_MOBILE":
                operator_ids.append(uid)

            await conn.execute("""
                INSERT INTO users (id, username, email, hashed_password, full_name, role,
                                   phone_number, organization, is_active, is_verified, created_at, updated_at)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,true,true,$9,$9)
            """, uid, uname, email, hash_password(pwd), full_name, role,
                phone, org, datetime.now(timezone.utc))

        print(f"  {len(USERS)} utilisateurs créés.")

        # ── Transactions (100 entrées) ───────────────────────────────────────
        print("Création des transactions...")
        tx_ids: list[uuid.UUID] = []
        tx_completed: list[uuid.UUID] = []     # éligibles à un reçu
        tx_suspicious: list[uuid.UUID] = []   # éligibles à une alerte fraude

        for i in range(100):
            tx_id = uuid.uuid4()
            tx_ids.append(tx_id)

            operator_id = random.choice(operator_ids)
            tx_type = random.choice(TX_TYPES)
            status   = random.choices(TX_STATUSES, weights=TX_STATUS_WEIGHTS)[0]
            amount   = round(random.choice([
                random.uniform(1_000, 50_000),
                random.uniform(50_000, 500_000),
                random.uniform(500_000, 5_000_000),
                random.choice([999_999, 1_000_000, 2_500_000, 5_000_000]),
            ]), 2)
            sender   = random.choice(SENEGAL_PHONES)
            receiver = random.choice([p for p in SENEGAL_PHONES if p != sender])
            tx_date  = random_date(180)
            ref      = f"TXN{tx_date.strftime('%Y%m%d')}{i:04d}"

            await conn.execute("""
                INSERT INTO transactions (id, reference, operator_id, amount, currency,
                    transaction_type, sender_phone, receiver_phone, sender_name, receiver_name,
                    status, transaction_date, created_at, updated_at)
                VALUES ($1,$2,$3,$4,'XOF',$5,$6,$7,$8,$9,$10,$11,$11,$11)
            """, tx_id, ref, operator_id, amount, tx_type,
                sender, receiver,
                f"Émetteur {i+1}", f"Destinataire {i+1}",
                status, tx_date)

            if status == "COMPLETED":
                tx_completed.append(tx_id)
            if amount >= 1_000_000 or (status == "UNDER_REVIEW"):
                tx_suspicious.append(tx_id)

        print(f"  {len(tx_ids)} transactions créées ({len(tx_completed)} complétées).")

        # ── Reçus fiscaux (toutes les transactions COMPLETED) ────────────────
        print("Création des reçus fiscaux...")
        tax_rate = 0.18
        receipt_count = 0
        for j, tx_id in enumerate(tx_completed):
            row = await conn.fetchrow("SELECT amount, operator_id, transaction_date FROM transactions WHERE id=$1", tx_id)
            amount    = float(row["amount"])
            op_id     = row["operator_id"]
            tx_date   = row["transaction_date"]
            tax_base  = round(amount / (1 + tax_rate), 2)
            tax_amt   = round(amount - tax_base, 2)
            sig       = hashlib.sha256(f"{tx_id}{amount}{tax_rate}".encode()).hexdigest()
            fp        = fiscal_period(tx_date)
            rnum      = f"RF{tx_date.strftime('%Y%m%d')}{j:04d}"

            await conn.execute("""
                INSERT INTO fiscal_receipts (id, receipt_number, transaction_id, operator_id,
                    tax_base, tax_rate, tax_amount, total_amount, currency,
                    digital_signature, signature_algorithm, fiscal_year, fiscal_period,
                    is_certified, is_cancelled, issued_at)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,'XOF',$9,'RSA-SHA256',$10,$11,true,false,$12)
            """, uuid.uuid4(), rnum, tx_id, op_id,
                tax_base, tax_rate, tax_amt, amount,
                sig, tx_date.year, fp, tx_date)
            receipt_count += 1

        # Annuler 5 % des reçus
        cancelled = await conn.fetch(
            "SELECT id FROM fiscal_receipts ORDER BY RANDOM() LIMIT $1",
            max(1, receipt_count // 20)
        )
        for r in cancelled:
            await conn.execute("""
                UPDATE fiscal_receipts SET is_cancelled=true, cancellation_reason='Erreur de montant',
                cancelled_at=NOW() WHERE id=$1
            """, r["id"])

        print(f"  {receipt_count} reçus créés ({len(cancelled)} annulés).")

        # ── Alertes de fraude (20 entrées) ────────────────────────────────────
        print("Création des alertes de fraude...")
        if not tx_suspicious:
            tx_suspicious = tx_ids[:20]
        for k in range(min(20, len(tx_suspicious))):
            tx_id  = tx_suspicious[k % len(tx_suspicious)]
            ftype  = random.choice(FRAUD_TYPES)
            fstat  = random.choices(
                FRAUD_STATUSES,
                weights=[30, 25, 20, 15, 10]
            )[0]
            risk   = round(random.uniform(0.40, 0.99), 4)
            det_at = random_date(90)

            await conn.execute("""
                INSERT INTO fraud_alerts (id, transaction_id, fraud_type, status, risk_score,
                    description, detected_at)
                VALUES ($1,$2,$3,$4,$5,$6,$7)
            """, uuid.uuid4(), tx_id, ftype, fstat, risk,
                f"Alerte automatique : {ftype.lower().replace('_',' ')} détecté(e).",
                det_at)

        print("  20 alertes de fraude créées.")

        # ── Audits (15 entrées) ───────────────────────────────────────────────
        print("Création des audits...")
        auditor_ids = [user_ids["agent.diallo"], user_ids["agent.sow"],
                       user_ids["auditeur.fall"], user_ids["auditeur.ndiaye"]]

        audit_data = [
            ("Audit conformité Q1 2026",     "MONTANT_SUSPECT",    "OUVERT",    tx_ids[0]),
            ("Vérification opérateur Wave",   "FREQUENCE_ANORMALE", "EN_COURS",  tx_ids[1]),
            ("Contrôle blanchiment",          "BLANCHIMENT",        "ESCALADE",  tx_ids[2]),
            ("Anomalie double transaction",   "DOUBLE_TRANSACTION", "RESOLU",    tx_ids[3]),
            ("Suspicion évasion fiscale",     "EVASION_FISCALE",    "OUVERT",    tx_ids[4]),
            ("Audit identité douteuse",       "IDENTITE_DOUTEUSE",  "EN_COURS",  None),
            ("Contrôle fréquence Mobile",     "FREQUENCE_ANORMALE", "OUVERT",    tx_ids[5]),
            ("Revue montants suspects Q4",    "MONTANT_SUSPECT",    "CLOS",      tx_ids[6]),
            ("Audit réseau Orange Money",     "AUTRE",              "EN_COURS",  tx_ids[7]),
            ("Détection structuring",         "MONTANT_SUSPECT",    "ESCALADE",  tx_ids[8]),
            ("Contrôle identités Free Money", "IDENTITE_DOUTEUSE",  "RESOLU",    tx_ids[9]),
            ("Audit annuel 2025",             "EVASION_FISCALE",    "CLOS",      None),
            ("Fraude potentielle aller-ret.", "BLANCHIMENT",        "OUVERT",    tx_ids[10]),
            ("Anomalie dépôt en espèces",     "MONTANT_SUSPECT",    "EN_COURS",  tx_ids[11]),
            ("Revue conformité Q2 2026",      "AUTRE",              "OUVERT",    None),
        ]

        for idx, (title, anom, astatus, tx_id) in enumerate(audit_data):
            audit_id = uuid.uuid4()
            auditor  = random.choice(auditor_ids)
            created  = random_date(120)
            num      = f"AUD{created.strftime('%Y%m%d')}{idx:03d}"
            findings = "Analyse en cours — données collectées." if astatus in ("EN_COURS", "ESCALADE") else None
            resolution = "Dossier clôturé sans suite." if astatus in ("RESOLU", "CLOS") else None
            resolved_at = (created + timedelta(days=random.randint(5, 30))) if astatus in ("RESOLU", "CLOS") else None

            await conn.execute("""
                INSERT INTO audits (id, audit_number, auditor_id, transaction_id, anomaly_type,
                    status, title, description, findings, resolution, created_at, updated_at, resolved_at)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$11,$12)
            """, audit_id, num, auditor, tx_id, anom, astatus, title,
                f"Description détaillée : {title.lower()}.",
                findings, resolution, created, resolved_at)

        print("  15 audits créés.")

        # ── Notifications ─────────────────────────────────────────────────────
        print("Création des notifications...")
        notif_count = 0
        all_user_ids = list(user_ids.values())

        notif_templates = {
            "FRAUD_ALERT":        ("Alerte de fraude détectée",          "Une activité suspecte a été détectée sur une transaction récente."),
            "AUDIT_UPDATE":       ("Mise à jour d'audit",                 "Un audit vous concernant a été mis à jour."),
            "RECEIPT_GENERATED":  ("Reçu fiscal généré",                  "Un nouveau reçu fiscal a été émis pour votre compte."),
            "SYSTEM":             ("Maintenance planifiée",               "Une maintenance est prévue le dimanche de 02h00 à 04h00."),
            "TAX_COMPLIANCE":     ("Rappel de conformité fiscale",        "Veillez à soumettre vos déclarations avant la fin du mois."),
        }

        for uid in all_user_ids:
            # 3 à 8 notifications par utilisateur
            for _ in range(random.randint(3, 8)):
                ntype = random.choice(NOTIF_TYPES)
                title, message = notif_templates[ntype]
                is_read = random.random() < 0.5
                created = random_date(30)
                await conn.execute("""
                    INSERT INTO notifications (id, recipient_id, notification_type, title, message,
                        is_read, created_at)
                    VALUES ($1,$2,$3,$4,$5,$6,$7)
                """, uuid.uuid4(), uid, ntype, title, message, is_read, created)
                notif_count += 1

        print(f"  {notif_count} notifications créées.")

        # ── Résumé ─────────────────────────────────────────────────────────────
        print("\n✓ Base de données initialisée avec succès !\n")
        print("┌─────────────────────────────────────────────────────────────┐")
        print("│  Comptes de test TAXUP                                      │")
        print("├───────────────────┬──────────────────────────┬─────────────┤")
        print("│ Rôle              │ Email                    │ Mot de passe│")
        print("├───────────────────┼──────────────────────────┼─────────────┤")
        print("│ ADMIN             │ admin@taxup.sn           │ Admin@2026  │")
        print("│ AGENT_DGID        │ agent.diallo@dgid.sn     │ Agent@2026  │")
        print("│ AGENT_DGID        │ agent.sow@dgid.sn        │ Agent@2026  │")
        print("│ AUDITEUR_FISCAL   │ auditeur.fall@taxup.sn   │ Audit@2026  │")
        print("│ AUDITEUR_FISCAL   │ auditeur.ndiaye@taxup.sn │ Audit@2026  │")
        print("│ OPERATEUR_MOBILE  │ wave@taxup.sn            │ Oper@2026   │")
        print("│ OPERATEUR_MOBILE  │ orangemoney@taxup.sn     │ Oper@2026   │")
        print("│ OPERATEUR_MOBILE  │ freemoney@taxup.sn       │ Oper@2026   │")
        print("│ CITOYEN           │ amadou.ba@gmail.com      │ Cit@2026    │")
        print("│ CITOYEN           │ fatou.mbaye@gmail.com    │ Cit@2026    │")
        print("└───────────────────┴──────────────────────────┴─────────────┘")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(run())
