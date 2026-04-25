from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class InvoiceBase(BaseModel):
    ico: Optional[str] = None
    dic: Optional[str] = None
    company_name: Optional[str] = None
    issue_date: Optional[datetime] = None
    fulfillment_date: Optional[datetime] = None
    due_date: Optional[datetime] = None
    description: Optional[str] = None
    amount_base_12: Optional[float] = None
    amount_vat_12: Optional[float] = None
    amount_base_21: Optional[float] = None
    amount_vat_21: Optional[float] = None
    amount_total: Optional[float] = None


class InvoiceResponse(InvoiceBase):
    id: int
    email_uid: str
    email_uid_original: Optional[str] = None
    attachment_index: int = 0
    email_subject: Optional[str] = None
    email_from: Optional[str] = None
    email_date: Optional[datetime] = None
    pdf_filename: Optional[str] = None
    invoice_number: Optional[str] = None
    doc_type: Optional[str] = "jine"
    supplier_address: Optional[str] = None
    customer_name: Optional[str] = None
    customer_ico: Optional[str] = None
    customer_dic: Optional[str] = None
    customer_address: Optional[str] = None
    extraction_success: bool
    extraction_notes: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str


class LoginRequest(BaseModel):
    username: str
    password: str


class SyncResponse(BaseModel):
    message: str
    new_invoices: int
    errors: int


class InvoiceUpdate(BaseModel):
    ico: Optional[str] = None
    dic: Optional[str] = None
    company_name: Optional[str] = None
    supplier_address: Optional[str] = None
    customer_name: Optional[str] = None
    customer_ico: Optional[str] = None
    customer_dic: Optional[str] = None
    customer_address: Optional[str] = None
    issue_date: Optional[datetime] = None
    fulfillment_date: Optional[datetime] = None
    due_date: Optional[datetime] = None
    description: Optional[str] = None
    amount_base_12: Optional[float] = None
    amount_vat_12: Optional[float] = None
    amount_base_21: Optional[float] = None
    amount_vat_21: Optional[float] = None
    amount_total: Optional[float] = None
    doc_type: Optional[str] = None
    invoice_number: Optional[str] = None


class ClientCreate(BaseModel):
    ico: str
    name: Optional[str] = None


class ClientResponse(BaseModel):
    id: int
    ico: str
    name: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True
