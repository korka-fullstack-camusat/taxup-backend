import uuid
from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel
from decimal import Decimal
from app.models.fraud import FraudType, FraudStatus


class FraudAlertResponse(BaseModel):
    id: uuid.UUID
    transaction_id: uuid.UUID
    fraud_type: FraudType
    status: FraudStatus
    risk_score: Decimal
    details: Optional[Dict[str, Any]]
    description: Optional[str]
    detected_at: datetime
    resolved_at: Optional[datetime]

    model_config = {"from_attributes": True}


class FraudAlertUpdate(BaseModel):
    status: FraudStatus
    description: Optional[str] = None
