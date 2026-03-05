"""
Digital signature service for fiscal receipts using RSA-SHA256.
Keys are loaded from Docker secrets or environment paths.
"""
import base64
import hashlib
import json
import qrcode
import io
from typing import Optional
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.backends import default_backend
from cryptography.exceptions import InvalidSignature
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)


class SignatureService:
    _private_key = None
    _public_key = None

    @classmethod
    def _load_keys(cls):
        """Load RSA keys lazily from file paths (Docker secrets)."""
        if cls._private_key is None:
            try:
                with open(settings.PRIVATE_KEY_PATH, "rb") as f:
                    cls._private_key = serialization.load_pem_private_key(
                        f.read(), password=None, backend=default_backend()
                    )
                with open(settings.PUBLIC_KEY_PATH, "rb") as f:
                    cls._public_key = serialization.load_pem_public_key(
                        f.read(), backend=default_backend()
                    )
            except FileNotFoundError:
                logger.warning("RSA key files not found, generating ephemeral keys for dev.")
                cls._private_key = rsa.generate_private_key(
                    public_exponent=65537, key_size=2048, backend=default_backend()
                )
                cls._public_key = cls._private_key.public_key()

    @classmethod
    def sign_receipt(cls, receipt_data: dict) -> str:
        """Sign receipt data and return base64-encoded signature."""
        cls._load_keys()
        payload = json.dumps(receipt_data, sort_keys=True, default=str).encode("utf-8")
        signature = cls._private_key.sign(
            payload,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH,
            ),
            hashes.SHA256(),
        )
        return base64.b64encode(signature).decode("utf-8")

    @classmethod
    def verify_signature(cls, receipt_data: dict, signature_b64: str) -> bool:
        """Verify a receipt signature. Returns True if valid."""
        cls._load_keys()
        try:
            payload = json.dumps(receipt_data, sort_keys=True, default=str).encode("utf-8")
            signature = base64.b64decode(signature_b64.encode("utf-8"))
            cls._public_key.verify(
                signature,
                payload,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH,
                ),
                hashes.SHA256(),
            )
            return True
        except (InvalidSignature, Exception):
            return False

    @staticmethod
    def generate_receipt_number(operator_id: str, transaction_ref: str) -> str:
        """Generate a unique, deterministic receipt number."""
        raw = f"TAXUP-{operator_id[:8]}-{transaction_ref}".upper()
        checksum = hashlib.sha256(raw.encode()).hexdigest()[:6].upper()
        return f"REC-{checksum}-{transaction_ref[:8].upper()}"

    @staticmethod
    def generate_qr_code(receipt_data: dict) -> str:
        """Generate QR code as base64 PNG for the fiscal receipt."""
        qr_payload = json.dumps({
            "receipt_number": receipt_data.get("receipt_number"),
            "transaction_ref": receipt_data.get("transaction_reference"),
            "tax_amount": str(receipt_data.get("tax_amount")),
            "issued_at": str(receipt_data.get("issued_at")),
            "verify_url": f"https://taxup.gov/verify/{receipt_data.get('receipt_number')}",
        })
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(qr_payload)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("utf-8")


signature_service = SignatureService()
