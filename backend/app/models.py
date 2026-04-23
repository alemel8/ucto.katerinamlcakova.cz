from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Boolean, UniqueConstraint
from sqlalchemy.sql import func
from .database import Base


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    # Compound key: for email with multiple PDFs, email_uid = "{imap_uid}_{attachment_index}"
    # For single-attachment emails (legacy) email_uid equals the raw IMAP UID.
    email_uid = Column(String, unique=True, index=True, nullable=False)
    email_uid_original = Column(String, nullable=True, index=True)   # raw IMAP UID
    attachment_index = Column(Integer, nullable=False, default=0)     # 0-based attachment position
    email_subject = Column(String, nullable=True)
    email_from = Column(String, nullable=True)
    email_date = Column(DateTime, nullable=True)

    # Extracted invoice data
    ico = Column(String(8), nullable=True, index=True)
    dic = Column(String(15), nullable=True)
    company_name = Column(String(255), nullable=True, index=True)
    issue_date = Column(DateTime, nullable=True, index=True)
    fulfillment_date = Column(DateTime, nullable=True)
    due_date = Column(DateTime, nullable=True)
    description = Column(Text, nullable=True)

    # Amounts
    amount_base_12 = Column(Float, nullable=True)   # Základ DPH 12 %
    amount_vat_12 = Column(Float, nullable=True)    # DPH 12 %
    amount_base_21 = Column(Float, nullable=True)   # Základ DPH 21 %
    amount_vat_21 = Column(Float, nullable=True)    # DPH 21 %
    amount_total = Column(Float, nullable=True)     # Celkem

    # PDF
    pdf_filename = Column(String(255), nullable=True)
    pdf_path = Column(String(512), nullable=True)

    # Supplier details (dodavatel)
    supplier_address = Column(Text, nullable=True)

    # Customer details (odběratel)
    customer_name = Column(String(255), nullable=True)
    customer_ico = Column(String(8), nullable=True)
    customer_dic = Column(String(15), nullable=True)
    customer_address = Column(Text, nullable=True)

    # Document type tag: faktura | uctenka | dobropis | jine
    doc_type = Column(String(20), nullable=True, default="jine")

    # Meta
    extraction_success = Column(Boolean, default=False)
    extraction_notes = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
