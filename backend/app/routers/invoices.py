import os
from typing import Optional, List
from datetime import datetime
from urllib.parse import quote
from xml.etree import ElementTree as ET

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from sqlalchemy import or_, extract as sql_extract

from ..config import settings
from ..database import get_db
from ..models import Invoice
from ..schemas import InvoiceResponse, SyncResponse, InvoiceUpdate
from ..email_fetcher import EmailFetcher

router = APIRouter(prefix="/api/invoices", tags=["invoices"])


async def get_user_flexible(request: Request) -> str:
    """Accept token from Authorization header OR ?token= query param (for iframe)."""
    token: Optional[str] = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1]
    else:
        token = request.query_params.get("token")
    if not token:
        raise HTTPException(status_code=401, detail="Není přihlášen")
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        sub: Optional[str] = payload.get("sub")
        if not sub:
            raise HTTPException(status_code=401, detail="Neplatný token")
        return sub
    except JWTError:
        raise HTTPException(status_code=401, detail="Neplatný token")


@router.get("", response_model=List[InvoiceResponse])
def list_invoices(
    search: Optional[str] = Query(None),
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    client_ico: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: str = Depends(get_user_flexible),
):
    q = db.query(Invoice)

    if client_ico:
        q = q.filter(Invoice.customer_ico == client_ico)

    if search:
        term = f"%{search}%"
        q = q.filter(
            or_(
                Invoice.company_name.ilike(term),
                Invoice.ico.ilike(term),
                Invoice.dic.ilike(term),
                Invoice.description.ilike(term),
                Invoice.email_subject.ilike(term),
            )
        )

    if year:
        q = q.filter(
            or_(
                Invoice.issue_date.between(
                    datetime(year, 1, 1), datetime(year, 12, 31, 23, 59, 59)
                ),
                (Invoice.issue_date == None)
                & Invoice.email_date.between(
                    datetime(year, 1, 1), datetime(year, 12, 31, 23, 59, 59)
                ),
            )
        )

    if month:
        q = q.filter(
            or_(
                sql_extract("month", Invoice.issue_date) == month,
                (Invoice.issue_date == None)
                & (sql_extract("month", Invoice.email_date) == month),
            )
        )

    if date_from:
        q = q.filter(
            or_(
                Invoice.issue_date >= date_from,
                (Invoice.issue_date == None) & (Invoice.email_date >= date_from),
            )
        )

    if date_to:
        q = q.filter(
            or_(
                Invoice.issue_date <= date_to,
                (Invoice.issue_date == None) & (Invoice.email_date <= date_to),
            )
        )

    q = q.order_by(Invoice.issue_date.desc().nullslast(), Invoice.email_date.desc())
    return q.all()


@router.post("/sync", response_model=SyncResponse)
def sync_emails(
    fetch_all: bool = Query(False, description="Stáhnout všechny emaily, ne jen nové"),
    db: Session = Depends(get_db),
    _: str = Depends(get_user_flexible),
):
    fetcher = EmailFetcher()
    try:
        result = fetcher.sync(db, fetch_all=fetch_all)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

    return SyncResponse(
        message=f"Synchronizace dokončena. Nových faktur: {result['new_invoices']}, chyb: {result['errors']}",
        new_invoices=result["new_invoices"],
        errors=result["errors"],
    )


@router.get("/export/pohoda")
def export_pohoda(
    ids: Optional[str] = Query(None, description="Čárkami oddělená ID faktur, prázdné = vše"),
    db: Session = Depends(get_db),
    _: str = Depends(get_user_flexible),
):
    q = db.query(Invoice)
    if ids:
        id_list = [int(i.strip()) for i in ids.split(",") if i.strip().isdigit()]
        q = q.filter(Invoice.id.in_(id_list))

    invoices = q.all()
    xml_content = _generate_pohoda_xml(invoices)
    return Response(
        content=xml_content,
        media_type="application/xml",
        headers={"Content-Disposition": "attachment; filename=pohoda_export.xml"},
    )


@router.get("/{invoice_id}", response_model=InvoiceResponse)
def get_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    _: str = Depends(get_user_flexible),
):
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Faktura nenalezena")
    return inv


@router.patch("/{invoice_id}", response_model=InvoiceResponse)
def update_invoice(
    invoice_id: int,
    data: InvoiceUpdate,
    db: Session = Depends(get_db),
    _: str = Depends(get_user_flexible),
):
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Faktura nenalezena")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(inv, field, value)

    db.commit()
    db.refresh(inv)
    return inv


@router.get("/{invoice_id}/pdf")
def get_invoice_pdf(
    invoice_id: int,
    db: Session = Depends(get_db),
    _: str = Depends(get_user_flexible),
):
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Faktura nenalezena")
    if not inv.pdf_path or not os.path.exists(inv.pdf_path):
        raise HTTPException(status_code=404, detail="Soubor nenalezen")

    filename = inv.pdf_filename or "priloha"
    ext = os.path.splitext(filename.lower())[1]
    media_map = {
        ".pdf": "application/pdf",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
    }
    media_type = media_map.get(ext, "application/octet-stream")

    # RFC 5987: encode non-ASCII filename so HTTP headers don't choke on Czech chars
    encoded_filename = quote(filename, safe="")
    content_disposition = f"inline; filename*=UTF-8''{encoded_filename}"

    return FileResponse(
        path=inv.pdf_path,
        media_type=media_type,
        headers={"Content-Disposition": content_disposition},
    )


# ─── POHODA XML generator ─────────────────────────────────────────────────────

def _fmt_date(d: Optional[datetime]) -> str:
    return d.strftime("%Y-%m-%d") if d else ""


def _fmt_amount(v: Optional[float]) -> str:
    return f"{v:.2f}" if v is not None else "0.00"


def _generate_pohoda_xml(invoices: list) -> bytes:
    NS_DAT = "http://www.stormware.cz/schema/version_2/data.xsd"
    NS_INV = "http://www.stormware.cz/schema/version_2/invoice.xsd"
    NS_TYP = "http://www.stormware.cz/schema/version_2/type.xsd"

    ET.register_namespace("dat", NS_DAT)
    ET.register_namespace("inv", NS_INV)
    ET.register_namespace("typ", NS_TYP)

    root = ET.Element(f"{{{NS_DAT}}}dataPack")
    root.set("version", "2.0")
    root.set("application", "FakturaVytezovani")
    root.set("note", f"Export {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    for idx, inv in enumerate(invoices, start=1):
        item_el = ET.SubElement(root, f"{{{NS_DAT}}}dataPackItem")
        item_el.set("id", str(idx))
        item_el.set("version", "2.0")

        invoice_el = ET.SubElement(item_el, f"{{{NS_INV}}}invoice")
        invoice_el.set("version", "2.0")

        header = ET.SubElement(invoice_el, f"{{{NS_INV}}}invoiceHeader")
        _sub(header, NS_INV, "invoiceType", "receivedInvoice")
        if inv.issue_date:
            _sub(header, NS_INV, "date", _fmt_date(inv.issue_date))
        if inv.fulfillment_date:
            _sub(header, NS_INV, "dateTax", _fmt_date(inv.fulfillment_date))
        if inv.due_date:
            _sub(header, NS_INV, "dateDue", _fmt_date(inv.due_date))
        if inv.description:
            _sub(header, NS_INV, "text", inv.description[:240])

        if inv.company_name or inv.ico or inv.dic:
            partner = ET.SubElement(header, f"{{{NS_INV}}}partnerIdentity")
            addr = ET.SubElement(partner, f"{{{NS_TYP}}}address")
            if inv.company_name:
                _sub(addr, NS_TYP, "company", inv.company_name)
            if inv.ico:
                _sub(addr, NS_TYP, "ico", inv.ico)
            if inv.dic:
                _sub(addr, NS_TYP, "dic", inv.dic)

        summary = ET.SubElement(invoice_el, f"{{{NS_INV}}}invoiceSummary")
        _sub(summary, NS_INV, "roundingDocument", "math2one")
        home_currency = ET.SubElement(summary, f"{{{NS_INV}}}homeCurrency")
        _sub(home_currency, NS_TYP, "priceNone", "0")
        _sub(home_currency, NS_TYP, "priceLow", _fmt_amount(inv.amount_base_12))
        _sub(home_currency, NS_TYP, "priceLowVAT", _fmt_amount(inv.amount_vat_12))
        _sub(
            home_currency, NS_TYP, "priceLowSum",
            _fmt_amount((inv.amount_base_12 or 0) + (inv.amount_vat_12 or 0)),
        )
        _sub(home_currency, NS_TYP, "priceHigh", _fmt_amount(inv.amount_base_21))
        _sub(home_currency, NS_TYP, "priceHighVAT", _fmt_amount(inv.amount_vat_21))
        _sub(
            home_currency, NS_TYP, "priceHighSum",
            _fmt_amount((inv.amount_base_21 or 0) + (inv.amount_vat_21 or 0)),
        )

    return ET.tostring(root, encoding="windows-1250", xml_declaration=True)


def _sub(parent: ET.Element, ns: str, tag: str, text: str) -> ET.Element:
    el = ET.SubElement(parent, f"{{{ns}}}{tag}")
    el.text = text
    return el
