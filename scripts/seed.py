#!/usr/bin/env python3
"""
TAXUP — Seed enrichi — Contexte sénégalais
=============================================
Comptes (mot de passe unique : passer@123)

  ADMIN            admin                admin@taxup.sn
  AGENT_DGID       agent_diallo         ibrahima.diallo@dgi.sn
  AGENT_DGID       agent_sow            mariama.sow@dgi.sn
  AGENT_DGID       agent_toure          oumar.toure@dgi.sn
  AGENT_DGID       agent_ba             cheikh.ba@dgi.sn
  AGENT_DGID       agent_faye           modou.faye@dgi.sn
  AUDITEUR_FISCAL  auditeur_fall        cheikh.fall@centif.sn
  AUDITEUR_FISCAL  auditeur_ndiaye      aissatou.ndiaye@centif.sn
  AUDITEUR_FISCAL  auditeur_gueye       pape.gueye@bceao.int
  AUDITEUR_FISCAL  auditeur_cisse       rokhaya.cisse@dgi.sn
  OPERATEUR_MOBILE wave_sn              ops@wave.sn
  OPERATEUR_MOBILE orange_money         ops@orangemoney.sn
  OPERATEUR_MOBILE free_money           ops@freemoney.sn
  OPERATEUR_MOBILE expresso             ops@expresso.sn
  CITOYEN          amadou_ba            amadou.ba@gmail.com
  CITOYEN          fatou_mbaye          fatou.mbaye@gmail.com
  CITOYEN          moussa_diop          moussa.diop@gmail.com
  CITOYEN          rokhaya_fall         rokhaya.fall@outlook.com
  CITOYEN          cheikh_ndiaye        cheikh.ndiaye@gmail.com
  CITOYEN          awa_diallo           awa.diallo@yahoo.fr
"""

import sys, os
sys.path.insert(0, "/app")

import asyncio, random, secrets, uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import asyncpg, httpx
from app.core.security import get_password_hash

# ── Config ────────────────────────────────────────────────────────────────────
BASE_URL = os.getenv("SEED_API_URL", "http://localhost:8000/api/v1")
PASSWORD  = "passer@123"
ADMIN_USERNAME = "admin"

# ── Téléphones sénégalais (+221 77/78 Orange-Wave, 76 Free, 70 Expresso) ──────
PHONES = [
    "+221771001001", "+221771001002", "+221771001003", "+221771001004",
    "+221771001005", "+221771001006", "+221771001007", "+221771001008",
    "+221781001001", "+221781001002", "+221781001003", "+221781001004",
    "+221761001001", "+221761001002", "+221761001003", "+221761001004",
    "+221701001001", "+221701001002", "+221701001003", "+221701001004",
    "+221772001001", "+221772001002", "+221772001003", "+221772001004",
    "+221773001001", "+221773001002", "+221773001003", "+221773001004",
    "+221774001001", "+221774001002",
]

# ── Noms sénégalais réalistes ─────────────────────────────────────────────────
PRENOMS_M = ["Mamadou", "Ibrahima", "Cheikh", "Oumar", "Modou", "Serigne",
             "Abdou", "Moussa", "Pape", "Babacar", "Lamine", "Alioune"]
PRENOMS_F = ["Fatou", "Mariama", "Aissatou", "Rokhaya", "Awa", "Sokhna",
             "Ndéye", "Astou", "Dieynaba", "Khady", "Bineta", "Coumba"]
NOMS    = ["Diallo", "Ba", "Sow", "Diop", "Ndiaye", "Fall", "Faye",
           "Gueye", "Mbaye", "Thiaw", "Cissé", "Sarr", "Diouf", "Touré",
           "Diagne", "Sy", "Kane", "Coulibaly", "Konaté", "Dramé"]

def rand_name(genre="M"):
    prenom = random.choice(PRENOMS_M if genre == "M" else PRENOMS_F)
    return f"{prenom} {random.choice(NOMS)}"

# ── Types et montants ─────────────────────────────────────────────────────────
TX_TYPES   = ["TRANSFERT", "PAIEMENT", "RETRAIT", "DEPOT", "REMBOURSEMENT"]
TX_WEIGHTS = [40, 25, 15, 15, 5]

NORMAL_AMOUNTS = [
    500, 1_000, 2_000, 2_500, 3_000, 5_000, 7_500, 10_000,
    15_000, 20_000, 25_000, 30_000, 50_000, 75_000, 100_000,
    150_000, 200_000, 250_000, 300_000, 400_000, 499_000,
]
SUSPICIOUS_AMOUNTS = [
    1_000_000, 1_200_000, 1_500_000, 2_000_000, 2_500_000,
    3_000_000, 5_000_000, 7_500_000, 10_000_000, 15_000_000, 25_000_000,
]

# ── Audits réalistes contexte sénégalais ─────────────────────────────────────
AUDIT_CASES = [
    ("Contrôle Wave Sénégal — vélocité anormale Dakar",          "FREQUENCE_ANORMALE"),
    ("Suspicion blanchiment — Orange Money Ziguinchor",            "BLANCHIMENT"),
    ("Transferts suspects vers Gambie — Free Money",               "MONTANT_SUSPECT"),
    ("Double transaction Expresso — réf. dupliquée",              "DOUBLE_TRANSACTION"),
    ("Structuring détecté — fractionnement sous 1M XOF",          "MONTANT_SUSPECT"),
    ("Évasion fiscale présumée — opérateur Touba",                "EVASION_FISCALE"),
    ("Identité douteuse — carte nationale expirée",               "IDENTITE_DOUTEUSE"),
    ("Contrôle CENTIF — opérations nocturnes répétitives",        "FREQUENCE_ANORMALE"),
    ("Aller-retour — même montant 24h — Dakar/Thiès",             "BLANCHIMENT"),
    ("Audit DGI — dépôts espèces > 5M XOF Saint-Louis",          "MONTANT_SUSPECT"),
    ("Contrôle mobile money — réseau Kaolack Q1 2026",            "FREQUENCE_ANORMALE"),
    ("Suspicion financement illicite — opérations transfrontières","BLANCHIMENT"),
    ("Anomalie fiscal — déclarations incomplètes Wave",            "EVASION_FISCALE"),
    ("Contrôle conformité BCEAO — rapport Q4 2025",               "AUTRE"),
    ("Alerte CENTIF — profil à risque élevé Mbour",              "MONTANT_SUSPECT"),
    ("Vérification identité — nouveau compte Free Money",          "IDENTITE_DOUTEUSE"),
    ("Fraude présumée — retrait multiples guichets Dakar",         "FREQUENCE_ANORMALE"),
    ("Audit annuel 2025 — Orange Money Sénégal",                 "AUTRE"),
    ("Structuring Expresso — série < 500k XOF",                   "MONTANT_SUSPECT"),
    ("Contrôle conformité Q2 2026 — bilan semestriel",            "AUTRE"),
]

# ── Helpers ───────────────────────────────────────────────────────────────────
def rand_past(min_d=1, max_d=180):
    m = random.randint(min_d * 1440, max_d * 1440)
    return datetime.now(timezone.utc) - timedelta(minutes=m)

def rand_phone():
    return random.choice(PHONES)

def rand_ref(pfx="TXN"):
    ts   = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    rnd  = secrets.token_hex(4).upper()
    return f"{pfx}-{ts}-{rnd}"

def get_db_url():
    url = os.getenv("DATABASE_URL", "")
    if not url:
        raise RuntimeError("DATABASE_URL non définie")
    return url.replace("postgresql+asyncpg://", "postgresql://").replace("postgres://", "postgresql://")

# ── Seed ─────────────────────────────────────────────────────────────────────
async def run():
    db = get_db_url()
    print(f"📦 DB : {db[:55]}...")
    conn = await asyncpg.connect(db)

    # 1. Nettoyage
    print("🗑  Nettoyage...")
    await conn.execute("""
        TRUNCATE notifications, fraud_alerts, audits, fiscal_receipts, transactions, users
        RESTART IDENTITY CASCADE
    """)

    # 2. Admin
    print("👤 Admin...")
    admin_id = uuid.uuid4()
    await conn.execute("""
        INSERT INTO users (id,username,email,hashed_password,full_name,role,
                           phone_number,organization,is_active,is_verified,api_key,created_at,updated_at)
        VALUES ($1,$2,$3,$4,$5,'ADMIN',$6,$7,true,true,$8,NOW(),NOW())
    """, admin_id, ADMIN_USERNAME, "admin@taxup.sn",
         get_password_hash(PASSWORD), "Administrateur Système",
         "+221771000000", "DGI — Direction Générale des Impôts",
         secrets.token_urlsafe(32))
    print(f"   ✓ admin@taxup.sn")
    await conn.close()

    # 3. Utilisateurs via API
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=60) as client:
        r = await client.post("/auth/login", json={"username": ADMIN_USERNAME, "password": PASSWORD})
        if r.status_code != 200:
            raise RuntimeError(f"Login admin échoué : {r.text}")
        ah = {"Authorization": f"Bearer {r.json()['access_token']}"}
        print("   ✓ Admin connecté")

        users = [
            # AGENTS DGI
            ("agent_diallo",   "ibrahima.diallo@dgi.sn",    "Ibrahima Diallo",    "AGENT_DGID",       "+221771001010", "DGI — Bureau Dakar Plateau"),
            ("agent_sow",      "mariama.sow@dgi.sn",         "Mariama Sow",        "AGENT_DGID",       "+221761001011", "DGI — Bureau Saint-Louis"),
            ("agent_toure",    "oumar.toure@dgi.sn",         "Oumar Touré",        "AGENT_DGID",       "+221771001012", "DGI — Bureau Ziguinchor"),
            ("agent_ba",       "cheikh.ba@dgi.sn",            "Cheikh Ba",          "AGENT_DGID",       "+221781001013", "DGI — Bureau Kaolack"),
            ("agent_faye",     "modou.faye@dgi.sn",           "Modou Faye",         "AGENT_DGID",       "+221701001014", "DGI — Bureau Thiès"),
            # AUDITEURS
            ("auditeur_fall",  "cheikh.fall@centif.sn",      "Cheikh Fall",        "AUDITEUR_FISCAL",  "+221771001020", "CENTIF — Dakar"),
            ("auditeur_ndiaye","aissatou.ndiaye@centif.sn",  "Aissatou Ndiaye",    "AUDITEUR_FISCAL",  "+221761001021", "CENTIF — Cellule Audit"),
            ("auditeur_gueye", "pape.gueye@bceao.int",        "Pape Gueye",         "AUDITEUR_FISCAL",  "+221771001022", "BCEAO — Dakar"),
            ("auditeur_cisse", "rokhaya.cisse@dgi.sn",        "Rokhaya Cissé",      "AUDITEUR_FISCAL",  "+221781001023", "DGI — Cellule Fraude Fiscale"),
            # OPERATEURS
            ("wave_sn",        "ops@wave.sn",                 "Wave Sénégal",        "OPERATEUR_MOBILE", "+221771002000", "Wave Mobile Money Sénégal"),
            ("orange_money",   "ops@orangemoney.sn",          "Orange Money Sénégal","OPERATEUR_MOBILE", "+221771002001", "Orange Money Sénégal SA"),
            ("free_money",     "ops@freemoney.sn",            "Free Money Sénégal", "OPERATEUR_MOBILE", "+221761002002", "Free Sénégal — Mobile Money"),
            ("expresso",       "ops@expresso.sn",             "Expresso Sénégal",   "OPERATEUR_MOBILE", "+221701002003", "Expresso Télécom Sénégal"),
            # CITOYENS
            ("amadou_ba",      "amadou.ba@gmail.com",         "Amadou Ba",          "CITOYEN",          "+221771003001", None),
            ("fatou_mbaye",    "fatou.mbaye@gmail.com",       "Fatou Mbaye",        "CITOYEN",          "+221761003002", None),
            ("moussa_diop",    "moussa.diop@gmail.com",       "Moussa Diop",        "CITOYEN",          "+221781003003", None),
            ("rokhaya_fall",   "rokhaya.fall@outlook.com",    "Rokhaya Fall",       "CITOYEN",          "+221771003004", None),
            ("cheikh_ndiaye",  "cheikh.ndiaye@gmail.com",     "Cheikh Ndiaye",      "CITOYEN",          "+221701003005", None),
            ("awa_diallo",     "awa.diallo@yahoo.fr",         "Awa Diallo",         "CITOYEN",          "+221771003006", None),
        ]

        operator_ids = {}
        print("\n👥 Création des utilisateurs...")
        for (uname, email, fname, role, phone, org) in users:
            payload = {"username": uname, "email": email, "password": PASSWORD,
                       "full_name": fname, "role": role, "phone_number": phone}
            if org:
                payload["organization"] = org
            r = await client.post("/users", headers=ah, json=payload)
            if r.status_code not in (200, 201):
                print(f"   ✗ {uname} : {r.status_code} — {r.text[:80]}")
            else:
                print(f"   ✓ {role:<20} {email}")

        # Récupérer IDs opérateurs
        r2 = await client.get("/users", headers=ah, params={"page_size": 100})
        if r2.status_code == 200:
            for u in r2.json().get("items", []):
                operator_ids[u["username"]] = u["id"]

        # Tokens agents/auditeurs pour les audits
        auditors = [("agent_diallo",   PASSWORD), ("agent_sow",    PASSWORD),
                    ("agent_toure",    PASSWORD), ("agent_ba",     PASSWORD),
                    ("agent_faye",     PASSWORD), ("auditeur_fall",PASSWORD),
                    ("auditeur_ndiaye",PASSWORD), ("auditeur_gueye",PASSWORD),
                    ("auditeur_cisse", PASSWORD)]
        auditor_tokens = []
        for (uname, pwd) in auditors:
            r = await client.post("/auth/login", json={"username": uname, "password": pwd})
            if r.status_code == 200:
                auditor_tokens.append(r.json()["access_token"])

    # 4. LOT A — Transactions normales (60/opérateur) directement en base
    print("\n💸 LOT A — Transactions normales (60 par opérateur)...")
    operators = ["wave_sn", "orange_money", "free_money", "expresso"]
    conn = await asyncpg.connect(get_db_url())
    tx_ids = []
    try:
        for uname in operators:
            op_id = operator_ids.get(uname)
            if not op_id:
                print(f"   ✗ {uname} introuvable")
                continue
            count = 0
            for _ in range(60):
                tid  = uuid.uuid4()
                past = rand_past(2, 180)
                amt  = random.choice(NORMAL_AMOUNTS)
                s    = rand_phone()
                r_   = random.choice([p for p in PHONES if p != s])
                await conn.execute("""
                    INSERT INTO transactions
                      (id,reference,operator_id,amount,currency,transaction_type,
                       sender_phone,receiver_phone,sender_name,receiver_name,
                       status,transaction_date,created_at,updated_at)
                    VALUES ($1,$2,$3,$4,'XOF',$5,$6,$7,$8,$9,'COMPLETED',$10,$11,$11)
                """, tid, rand_ref("TXN"), uuid.UUID(op_id),
                     Decimal(str(amt)),
                     random.choices(TX_TYPES, weights=TX_WEIGHTS)[0],
                     s, r_,
                     rand_name(random.choice(["M","F"])),
                     rand_name(random.choice(["M","F"])),
                     rand_past(2, 180), past)
                tx_ids.append(str(tid))
                count += 1
            print(f"   ✓ {uname:<15} {count}/60 transactions normales")
    finally:
        await conn.close()

    # 5. LOT B — Transactions suspectes (30/opérateur) + alertes fraude
    print("\n🚨 LOT B — Transactions suspectes (30 par opérateur)...")
    conn = await asyncpg.connect(get_db_url())
    susp_ids = []
    try:
        for uname in operators:
            op_id = operator_ids.get(uname)
            if not op_id:
                continue
            count = 0
            for _ in range(30):
                tid  = uuid.uuid4()
                past = rand_past(3, 60)
                amt  = random.choice(SUSPICIOUS_AMOUNTS)
                s    = rand_phone()
                r_   = random.choice([p for p in PHONES if p != s])

                await conn.execute("""
                    INSERT INTO transactions
                      (id,reference,operator_id,amount,currency,transaction_type,
                       sender_phone,receiver_phone,sender_name,receiver_name,
                       status,transaction_date,created_at,updated_at)
                    VALUES ($1,$2,$3,$4,'XOF',$5,$6,$7,$8,$9,'UNDER_REVIEW',$10,$11,$11)
                """, tid, rand_ref("SUSP"), uuid.UUID(op_id),
                     Decimal(str(amt)),
                     random.choices(TX_TYPES, weights=TX_WEIGHTS)[0],
                     s, r_,
                     rand_name(random.choice(["M","F"])),
                     rand_name(random.choice(["M","F"])),
                     rand_past(3, 90), past)

                # Alerte LARGE_AMOUNT
                risk = round(min(1.0, amt / 2_000_000), 4)
                await conn.execute("""
                    INSERT INTO fraud_alerts
                      (id,transaction_id,fraud_type,status,risk_score,description,details,detected_at)
                    VALUES ($1,$2,'LARGE_AMOUNT','DETECTED',$3,$4,$5,$6)
                """, uuid.uuid4(), tid, risk,
                     f"Montant {amt:,.0f} XOF dépasse le seuil réglementaire de 1 000 000 XOF",
                     f'{{"amount":{amt},"threshold":1000000,"operator":"{uname}"}}', past)

                # Alerte STRUCTURING (65%)
                if random.random() < 0.65:
                    cum = amt + random.randint(200_000, 800_000)
                    await conn.execute("""
                        INSERT INTO fraud_alerts
                          (id,transaction_id,fraud_type,status,risk_score,description,details,detected_at)
                        VALUES ($1,$2,'STRUCTURING','DETECTED',$3,$4,$5,$6)
                    """, uuid.uuid4(), tid,
                         round(min(1.0, cum/1_000_000), 4),
                         f"Cumul {cum:,.0f} XOF sur 24h — fractionnement probable",
                         f'{{"cumulative":{cum},"window_hours":24}}', past)

                # Alerte ROUND_TRIPPING (35%)
                if random.random() < 0.35:
                    await conn.execute("""
                        INSERT INTO fraud_alerts
                          (id,transaction_id,fraud_type,status,risk_score,description,details,detected_at)
                        VALUES ($1,$2,'ROUND_TRIPPING','DETECTED',0.88,$3,$4,$5)
                    """, uuid.uuid4(), tid,
                         "Transaction aller-retour détectée — mêmes parties sous 24h",
                         '{"reverse_count":1,"window_hours":24}', past)

                susp_ids.append(str(tid))
                count += 1
            print(f"   ✓ {uname:<15} {count}/30 transactions suspectes")
    finally:
        await conn.close()

    # 6. Audits
    print("\n🔍 Création des audits...")
    all_tx = tx_ids + susp_ids
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=60) as client:
        audit_ok = 0
        for i, (title, anom) in enumerate(AUDIT_CASES):
            if not auditor_tokens:
                break
            hdr = {"Authorization": f"Bearer {auditor_tokens[i % len(auditor_tokens)]}"}
            payload = {"title": title,
                       "description": f"{title}. Analyse en cours par les services compétents.",
                       "anomaly_type": anom}
            if all_tx and i < len(all_tx):
                payload["transaction_id"] = all_tx[i]
            r = await client.post("/audits", headers=hdr, json=payload)
            if r.status_code == 201:
                audit_ok += 1
        print(f"   ✓ {audit_ok}/{len(AUDIT_CASES)} audits créés")

    # 7. Résumé
    total = len(tx_ids) + len(susp_ids)
    print(f"\n{'='*68}")
    print("✅ BASE DE DONNÉES INITIALISÉE — CONTEXTE SÉNÉGALAIS")
    print(f"{'='*68}")
    print(f"  Utilisateurs            : {len(users)+1} (admin inclus)")
    print(f"  Transactions normales   : {len(tx_ids)} (COMPLETED)")
    print(f"  Transactions suspectes  : {len(susp_ids)} (UNDER_REVIEW + alertes fraude)")
    print(f"  Total transactions      : {total}")
    print(f"  Audits créés            : {audit_ok}")
    print()
    print(f"  {'Rôle':<20} {'Username':<18} {'Email':<35} Mdp")
    print(f"  {'-'*90}")
    comptes = [
        ("ADMIN",            "admin",           "admin@taxup.sn"),
        ("AGENT_DGID",       "agent_diallo",    "ibrahima.diallo@dgi.sn"),
        ("AGENT_DGID",       "agent_sow",       "mariama.sow@dgi.sn"),
        ("AGENT_DGID",       "agent_toure",     "oumar.toure@dgi.sn"),
        ("AGENT_DGID",       "agent_ba",        "cheikh.ba@dgi.sn"),
        ("AGENT_DGID",       "agent_faye",      "modou.faye@dgi.sn"),
        ("AUDITEUR_FISCAL",  "auditeur_fall",   "cheikh.fall@centif.sn"),
        ("AUDITEUR_FISCAL",  "auditeur_ndiaye", "aissatou.ndiaye@centif.sn"),
        ("AUDITEUR_FISCAL",  "auditeur_gueye",  "pape.gueye@bceao.int"),
        ("AUDITEUR_FISCAL",  "auditeur_cisse",  "rokhaya.cisse@dgi.sn"),
        ("OPERATEUR_MOBILE", "wave_sn",         "ops@wave.sn"),
        ("OPERATEUR_MOBILE", "orange_money",    "ops@orangemoney.sn"),
        ("OPERATEUR_MOBILE", "free_money",      "ops@freemoney.sn"),
        ("OPERATEUR_MOBILE", "expresso",        "ops@expresso.sn"),
        ("CITOYEN",          "amadou_ba",       "amadou.ba@gmail.com"),
        ("CITOYEN",          "fatou_mbaye",     "fatou.mbaye@gmail.com"),
        ("CITOYEN",          "moussa_diop",     "moussa.diop@gmail.com"),
        ("CITOYEN",          "rokhaya_fall",    "rokhaya.fall@outlook.com"),
        ("CITOYEN",          "cheikh_ndiaye",   "cheikh.ndiaye@gmail.com"),
        ("CITOYEN",          "awa_diallo",      "awa.diallo@yahoo.fr"),
    ]
    for (role, uname, email) in comptes:
        print(f"  {role:<20} {uname:<18} {email:<35} passer@123")
    print(f"{'='*68}\n")


if __name__ == "__main__":
    asyncio.run(run())
