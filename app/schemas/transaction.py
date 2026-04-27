import uuid
from datetime import datetime
from typing import Optional, Dict, Any, Union
from pydantic import BaseModel, Field, field_validator
from decimal import Decimal
from app.models.transaction import TransactionType, TransactionStatus


class TransactionBase(BaseModel):
    amount: Decimal
    currency: str = "XOF"
    transaction_type: TransactionType
    sender_phone: str
    receiver_phone: str
    sender_name: Optional[str] = None
    receiver_name: Optional[str] = None
    external_reference: Optional[str] = None
    metadata_: Optional[Dict[str, Any]] = Field(None, alias="metadata")
    transaction_date: datetime

    model_config = {"populate_by_name": True}

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Amount must be positive")
        if v > Decimal("999999999.99"):
            raise ValueError("Amount exceeds maximum allowed value")
        return v

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        allowed = {"XOF", "XAF", "EUR", "USD", "GBP"}
        if v.upper() not in allowed:
            raise ValueError(f"Currency must be one of {allowed}")
        return v.upper()


class TransactionCreate(TransactionBase):
    pass


class TransactionUpdate(BaseModel):
    status: Optional[TransactionStatus] = None
    metadata_: Optional[Dict[str, Any]] = Field(None, alias="metadata")

    model_config = {"populate_by_name": True}


class TransactionResponse(BaseModel):
    id: uuid.UUID
    reference: str
    operator_id: uuid.UUID
    amount: Decimal
    currency: str
    transaction_type: TransactionType
    sender_phone: str
    receiver_phone: str
    sender_name: Optional[str] = None
    receiver_name: Optional[str] = None
    external_reference: Optional[str] = None
    transaction_date: datetime
    status: TransactionStatus
    created_at: datetime
    updated_at: datetime
    metadata_: Optional[Dict[str, Any]] = Field(None, alias="metadata", validation_alias="metadata_")

    @field_validator("metadata_", mode="before")
    @classmethod
    def discard_sqlalchemy_metadata(cls, v):
        if type(v).__name__ == 'MetaData':
            return None
        return v

    model_config = {"from_attributes": True, "populate_by_name": True}


class TransactionDetailResponse(TransactionResponse):
    receipt: Optional[Any] = None
    fraud_alerts: Optional[list] = None
