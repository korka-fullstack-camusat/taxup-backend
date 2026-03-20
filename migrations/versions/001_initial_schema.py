"""Initial schema - all TAXUP tables

Revision ID: 001
Revises:
Create Date: 2026-03-05 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Users ──────────────────────────────────────────────────────────────────
    # Note: SQLAlchemy creates PostgreSQL enum types automatically before
    # each CREATE TABLE when create_type is not set to False.
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("username", sa.String(100), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column(
            "role",
            sa.Enum(
                "OPERATEUR_MOBILE", "AUDITEUR_FISCAL", "CITOYEN", "AGENT_DGID", "ADMIN",
                name="userrole",
            ),
            nullable=False,
        ),
        sa.Column("phone_number", sa.String(20), nullable=True),
        sa.Column("organization", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("api_key", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("api_key"),
    )
    op.create_index("ix_users_username", "users", ["username"])
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_api_key", "users", ["api_key"])

    # ── Transactions ───────────────────────────────────────────────────────────
    op.create_table(
        "transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reference", sa.String(100), nullable=False),
        sa.Column("operator_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="XOF"),
        sa.Column(
            "transaction_type",
            sa.Enum(
                "TRANSFERT", "PAIEMENT", "RETRAIT", "DEPOT", "REMBOURSEMENT",
                name="transactiontype",
            ),
            nullable=False,
        ),
        sa.Column("sender_phone", sa.String(20), nullable=False),
        sa.Column("receiver_phone", sa.String(20), nullable=False),
        sa.Column("sender_name", sa.String(255), nullable=True),
        sa.Column("receiver_name", sa.String(255), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING", "COMPLETED", "FAILED", "CANCELLED", "UNDER_REVIEW",
                name="transactionstatus",
            ),
            nullable=False,
        ),
        sa.Column("external_reference", sa.String(100), nullable=True),
        sa.Column("metadata", postgresql.JSON(), nullable=True),
        sa.Column("transaction_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["operator_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reference"),
    )
    op.create_index("ix_transactions_reference", "transactions", ["reference"])
    op.create_index("ix_transactions_sender_phone", "transactions", ["sender_phone"])
    op.create_index("ix_transactions_receiver_phone", "transactions", ["receiver_phone"])
    op.create_index("ix_transactions_operator_date", "transactions", ["operator_id", "transaction_date"])
    op.create_index("ix_transactions_status_date", "transactions", ["status", "transaction_date"])

    # ── Fiscal Receipts ────────────────────────────────────────────────────────
    op.create_table(
        "fiscal_receipts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("receipt_number", sa.String(50), nullable=False),
        sa.Column("transaction_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operator_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tax_base", sa.Numeric(15, 2), nullable=False),
        sa.Column("tax_rate", sa.Numeric(5, 4), nullable=False),
        sa.Column("tax_amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("total_amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="XOF"),
        sa.Column("digital_signature", sa.Text(), nullable=False),
        sa.Column("signature_algorithm", sa.String(50), nullable=False),
        sa.Column("qr_code_data", sa.Text(), nullable=True),
        sa.Column("fiscal_year", sa.Integer(), nullable=False),
        sa.Column("fiscal_period", sa.String(10), nullable=False),
        sa.Column("is_certified", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("is_cancelled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"]),
        sa.ForeignKeyConstraint(["operator_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("receipt_number"),
        sa.UniqueConstraint("transaction_id"),
    )
    op.create_index("ix_fiscal_receipts_receipt_number", "fiscal_receipts", ["receipt_number"])

    # ── Audits ─────────────────────────────────────────────────────────────────
    op.create_table(
        "audits",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("audit_number", sa.String(50), nullable=False),
        sa.Column("auditor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("transaction_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "anomaly_type",
            sa.Enum(
                "MONTANT_SUSPECT", "FREQUENCE_ANORMALE", "IDENTITE_DOUTEUSE",
                "DOUBLE_TRANSACTION", "EVASION_FISCALE", "BLANCHIMENT", "AUTRE",
                name="anomalytype",
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("OUVERT", "EN_COURS", "RESOLU", "ESCALADE", "CLOS", name="auditstatus"),
            nullable=False,
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("findings", sa.Text(), nullable=True),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["auditor_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("audit_number"),
    )
    op.create_index("ix_audits_audit_number", "audits", ["audit_number"])

    # ── Fraud Alerts ───────────────────────────────────────────────────────────
    op.create_table(
        "fraud_alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("transaction_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "fraud_type",
            sa.Enum(
                "VELOCITY", "LARGE_AMOUNT", "ROUND_TRIPPING", "STRUCTURING",
                "UNUSUAL_PATTERN", "BLACKLISTED",
                name="fraudtype",
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "DETECTED", "INVESTIGATING", "CONFIRMED", "FALSE_POSITIVE", "RESOLVED",
                name="fraudstatus",
            ),
            nullable=False,
        ),
        sa.Column("risk_score", sa.Numeric(5, 4), nullable=False),
        sa.Column("details", postgresql.JSON(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── Notifications ──────────────────────────────────────────────────────────
    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recipient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "notification_type",
            sa.Enum(
                "FRAUD_ALERT", "AUDIT_UPDATE", "RECEIPT_GENERATED", "SYSTEM", "TAX_COMPLIANCE",
                name="notificationtype",
            ),
            nullable=False,
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSON(), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["recipient_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("notifications")
    op.drop_table("fraud_alerts")
    op.drop_table("audits")
    op.drop_table("fiscal_receipts")
    op.drop_table("transactions")
    op.drop_table("users")

    for enum_name in [
        "notificationtype", "fraudstatus", "fraudtype",
        "auditstatus", "anomalytype", "transactionstatus",
        "transactiontype", "userrole",
    ]:
        op.execute(sa.text(f"DROP TYPE IF EXISTS {enum_name}"))
