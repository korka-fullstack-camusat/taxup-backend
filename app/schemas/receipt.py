import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from decimal import Decimal


class FiscalReceiptResponse(BaseModel):
    id: uuid.UUID
    receipt_number: str
    transaction_id: uuid.UUID
    operator_id: uuid.UUID
    tax_base: Decimal
    tax_rate: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    currency: str
    digital_signature: str
    signature_algorithm: str
    qr_code_data: Optional[str]
    fiscal_year: int
    fiscal_period: str
    is_certified: bool
    is_cancelled: bool
    cancellation_reason: Optional[str]
    issued_at: datetime
    cancelled_at: Optional[datetime]

    model_config = {"from_attributes": True}


class ReceiptVerifyRequest(BaseModel):
    receipt_number: str
    digital_signature: str


class ReceiptVerifyResponse(BaseModel):
    is_valid: bool
    receipt_number: str
    message: str
    receipt: Optional[FiscalReceiptResponse] = None
