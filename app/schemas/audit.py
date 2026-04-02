import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from app.models.audit import AnomalyType, AuditStatus


class AuditCreate(BaseModel):
    transaction_id: Optional[uuid.UUID] = None
    anomaly_type: AnomalyType
    title: str
    description: str


class AuditUpdate(BaseModel):
    status: Optional[AuditStatus] = None
    findings: Optional[str] = None
    resolution: Optional[str] = None


class AuditResponse(BaseModel):
    id: uuid.UUID
    audit_number: str
    auditor_id: uuid.UUID
    transaction_id: Optional[uuid.UUID]
    anomaly_type: AnomalyType
    status: AuditStatus
    title: str
    description: str
    findings: Optional[str]
    resolution: Optional[str]
    created_at: datetime
    updated_at: datetime
    resolved_at: Optional[datetime]

    model_config = {"from_attributes": True}
