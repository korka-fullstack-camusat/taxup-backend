import uuid
import math
import io
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT

from app.api.deps import get_current_active_user, require_roles
from app.core.database import get_db
from app.models.user import User, UserRole
from app.models.receipt import FiscalReceipt
from app.models.transaction import Transaction
from app.schemas.receipt import FiscalReceiptResponse, ReceiptVerifyRequest, ReceiptVerifyResponse
from app.schemas.common import PaginatedResponse, MessageResponse
from app.services.receipt_service import ReceiptService

router = APIRouter(prefix="/receipts", tags=["Fiscal Receipts"])


@router.post(
    "/generate/{transaction_id}",
    response_model=FiscalReceiptResponse,
    status_code=201,
    dependencies=[Depends(require_roles(UserRole.OPERATEUR_MOBILE, UserRole.AGENT_DGID, UserRole.ADMIN))],
)
async def generate_receipt(
    transaction_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Generate a certified digital fiscal receipt for a transaction."""
    result = await db.execute(select(Transaction).where(Transaction.id == transaction_id))
    transaction = result.scalar_one_or_none()
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return await ReceiptService.generate_receipt(db, transaction, current_user)


@router.get("", response_model=PaginatedResponse[FiscalReceiptResponse])
async def list_receipts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    fiscal_year: Optional[int] = None,
    fiscal_period: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List fiscal receipts with optional filtering."""
    query = select(FiscalReceipt)

    if current_user.role == UserRole.OPERATEUR_MOBILE:
        query = query.where(FiscalReceipt.operator_id == current_user.id)

    if fiscal_year:
        query = query.where(FiscalReceipt.fiscal_year == fiscal_year)
    if fiscal_period:
        query = query.where(FiscalReceipt.fiscal_period == fiscal_period)

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar()

    query = query.order_by(FiscalReceipt.issued_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    items = result.scalars().all()

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=math.ceil(total / page_size) if total else 1,
    )


@router.get("/{receipt_id}/download")
async def download_receipt(
    receipt_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Download a fiscal receipt as a PDF file."""
    receipt = await ReceiptService.get_receipt(db, receipt_id, current_user)
    status_label = "ANNULÉ" if receipt.is_cancelled else "VALIDE"
    issued = str(receipt.issued_at)[:19].replace("T", " ")

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("title", parent=styles["Normal"], fontSize=18, fontName="Helvetica-Bold", alignment=TA_CENTER, spaceAfter=4)
    subtitle_style = ParagraphStyle("subtitle", parent=styles["Normal"], fontSize=10, alignment=TA_CENTER, textColor=colors.HexColor("#6B7280"), spaceAfter=16)
    label_style = ParagraphStyle("label", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor("#6B7280"), fontName="Helvetica")
    value_style = ParagraphStyle("value", parent=styles["Normal"], fontSize=11, fontName="Helvetica-Bold", textColor=colors.HexColor("#111827"))
    status_valid_style = ParagraphStyle("status_valid", parent=styles["Normal"], fontSize=11, fontName="Helvetica-Bold", textColor=colors.HexColor("#065F46"))
    status_cancel_style = ParagraphStyle("status_cancel", parent=styles["Normal"], fontSize=11, fontName="Helvetica-Bold", textColor=colors.HexColor("#991B1B"))
    amount_label_style = ParagraphStyle("amount_label", parent=styles["Normal"], fontSize=10, textColor=colors.HexColor("#6B7280"))
    amount_value_style = ParagraphStyle("amount_value", parent=styles["Normal"], fontSize=14, fontName="Helvetica-Bold", textColor=colors.HexColor("#1D4ED8"), alignment=TA_CENTER)
    footer_style = ParagraphStyle("footer", parent=styles["Normal"], fontSize=8, textColor=colors.HexColor("#9CA3AF"), alignment=TA_CENTER)

    story = []

    # Header
    story.append(Paragraph("REÇU FISCAL", title_style))
    story.append(Paragraph("Plateforme Nationale d'Audit Digital Fiscal — TAXUP", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#1D4ED8")))
    story.append(Spacer(1, 10 * mm))

    # Info table
    status_style = status_cancel_style if receipt.is_cancelled else status_valid_style
    info_data = [
        [Paragraph("N° Reçu", label_style),       Paragraph(receipt.receipt_number, value_style),
         Paragraph("Statut", label_style),         Paragraph(status_label, status_style)],
        [Paragraph("Période fiscale", label_style), Paragraph(receipt.fiscal_period, value_style),
         Paragraph("Émis le", label_style),        Paragraph(issued, value_style)],
        [Paragraph("Transaction", label_style),    Paragraph(str(receipt.transaction_id), ParagraphStyle("small", parent=styles["Normal"], fontSize=8, textColor=colors.HexColor("#374151"))),
         Paragraph("", label_style),               Paragraph("", label_style)],
    ]
    info_table = Table(info_data, colWidths=[35 * mm, 65 * mm, 30 * mm, 40 * mm])
    info_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 8 * mm))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#E5E7EB")))
    story.append(Spacer(1, 8 * mm))

    # Amounts
    amounts_data = [
        [Paragraph("Montant total", amount_label_style), Paragraph(f"Taxe ({receipt.tax_rate * 100:.1f}%)", amount_label_style)],
        [Paragraph(f"{receipt.total_amount:,.0f} XOF", amount_value_style), Paragraph(f"{receipt.tax_amount:,.0f} XOF", ParagraphStyle("tax_val", parent=styles["Normal"], fontSize=14, fontName="Helvetica-Bold", textColor=colors.HexColor("#059669"), alignment=TA_CENTER))],
    ]
    amounts_table = Table(amounts_data, colWidths=[85 * mm, 85 * mm])
    amounts_table.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, 0), (0, 1), colors.HexColor("#EFF6FF")),
        ("BACKGROUND", (1, 0), (1, 1), colors.HexColor("#ECFDF5")),
        ("ROUNDEDCORNERS", [6, 6, 6, 6]),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(amounts_table)
    story.append(Spacer(1, 12 * mm))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#E5E7EB")))
    story.append(Spacer(1, 6 * mm))

    # Footer
    story.append(Paragraph("Ce document est un reçu fiscal officiel généré par la plateforme TAXUP.", footer_style))
    story.append(Paragraph("Plateforme Nationale d'Audit Digital Fiscal — République de Guinée", footer_style))

    doc.build(story)
    pdf_bytes = buffer.getvalue()

    filename = f"recu-{receipt.receipt_number}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=\"{filename}\""},
    )


@router.get("/{receipt_id}", response_model=FiscalReceiptResponse)
async def get_receipt(
    receipt_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get a fiscal receipt by ID."""
    return await ReceiptService.get_receipt(db, receipt_id, current_user)


@router.post("/verify", response_model=ReceiptVerifyResponse)
async def verify_receipt(
    request: ReceiptVerifyRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Publicly verify the authenticity of a fiscal receipt by its number and digital signature.
    No authentication required.
    """
    return await ReceiptService.verify_receipt(db, request.receipt_number, request.digital_signature)


@router.delete(
    "/{receipt_id}",
    response_model=FiscalReceiptResponse,
    dependencies=[Depends(require_roles(UserRole.AGENT_DGID, UserRole.ADMIN))],
)
async def cancel_receipt(
    receipt_id: uuid.UUID,
    reason: str = Query(..., min_length=10),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Cancel a fiscal receipt (DGID agents only)."""
    return await ReceiptService.cancel_receipt(db, receipt_id, reason, current_user)
