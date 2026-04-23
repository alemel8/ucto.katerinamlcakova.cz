import imaplib
import email
from email.header import decode_header as _decode_header
import re
import logging
import os
import socket
import threading
import time
from pathlib import Path
from datetime import datetime
from typing import Optional, Callable

from sqlalchemy.orm import Session

from .config import settings
from .models import Invoice
from .pdf_extractor import extract_invoice_data, extract_invoice_data_from_image

logger = logging.getLogger(__name__)

# Extensions treated as image attachments (OCR directly)
IMAGE_EXTENSIONS = frozenset([".jpg", ".jpeg", ".png"])
IMAGE_MIMETYPES = frozenset(["image/jpeg", "image/jpg", "image/png"])


def decode_mime_words(s: Optional[str]) -> str:
    if not s:
        return ""
    parts = []
    for encoded_bytes, charset in _decode_header(s):
        if isinstance(encoded_bytes, bytes):
            try:
                parts.append(encoded_bytes.decode(charset or "utf-8", errors="replace"))
            except (LookupError, UnicodeDecodeError):
                parts.append(encoded_bytes.decode("latin-1", errors="replace"))
        else:
            parts.append(encoded_bytes)
    return "".join(parts)


def parse_email_date(date_str: Optional[str]) -> Optional[datetime]:
    if not date_str:
        return None
    from email.utils import parsedate_to_datetime
    try:
        return parsedate_to_datetime(date_str).replace(tzinfo=None)
    except Exception:
        return None


class EmailFetcher:
    def __init__(self):
        self.host = settings.IMAP_HOST
        self.port = settings.IMAP_PORT
        self.user = settings.EMAIL_ADDRESS
        self.password = settings.EMAIL_PASSWORD
        self.pdf_dir = Path(settings.PDF_STORAGE_PATH)
        self.pdf_dir.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> imaplib.IMAP4_SSL:
        imap = imaplib.IMAP4_SSL(self.host, self.port)
        imap.login(self.user, self.password)
        return imap

    def sync(self, db: Session, fetch_all: bool = False) -> dict:
        """
        Connect to IMAP, fetch emails with PDF attachments, extract invoice
        data, and persist to the database.

        Args:
            db: SQLAlchemy session
            fetch_all: if True fetch ALL messages, otherwise only UNSEEN

        Returns:
            {"new_invoices": int, "errors": int}
        """
        new_count = 0
        error_count = 0

        try:
            imap = self._connect()
        except Exception as e:
            logger.error(f"IMAP connection failed: {e}")
            raise RuntimeError(f"Nelze se připojit k poštovnímu serveru: {e}")

        try:
            imap.select("INBOX")
            criteria = "ALL" if fetch_all else "UNSEEN"
            status, data = imap.uid("search", None, criteria)
            if status != "OK" or not data or not data[0]:
                return {"new_invoices": 0, "errors": 0}

            uids = data[0].split()
            logger.info(f"Found {len(uids)} messages (criteria={criteria})")

            for uid_bytes in uids:
                uid = uid_bytes.decode()
                try:
                    result = self._process_email(imap, uid, db)
                    if result == "new":
                        new_count += 1
                    elif result == "error":
                        error_count += 1
                except Exception as e:
                    logger.error(f"Error processing UID {uid}: {e}")
                    error_count += 1

        finally:
            try:
                imap.logout()
            except Exception:
                pass

        return {"new_invoices": new_count, "errors": error_count}

    def _process_email(self, imap: imaplib.IMAP4_SSL, uid: str, db: Session) -> str:
        """
        Process a single email by UID.
        Creates one Invoice row per PDF attachment.
        Returns 'new' (at least one new invoice saved), 'skip', or 'error'.
        """

        # Fetch full message
        status, data = imap.uid("fetch", uid, "(RFC822)")
        if status != "OK" or not data or data[0] is None:
            return "error"

        raw = data[0][1]
        msg = email.message_from_bytes(raw)

        subject = decode_mime_words(msg.get("Subject"))
        from_header = decode_mime_words(msg.get("From"))
        date_str = msg.get("Date")
        email_date = parse_email_date(date_str)

        # Collect all PDF and image attachments
        pdf_attachments = []
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disp = part.get_content_disposition() or ""
            filename = decode_mime_words(part.get_filename() or "")
            fn_lower = filename.lower()
            ext = os.path.splitext(fn_lower)[1]

            is_pdf = (
                content_type == "application/pdf"
                or fn_lower.endswith(".pdf")
                or ("attachment" in content_disp and fn_lower.endswith(".pdf"))
            )
            # Only treat images as invoice attachments when they are explicit
            # attachments — never inline (logos, signature buttons, etc.)
            is_image = (
                "attachment" in content_disp
                and (content_type in IMAGE_MIMETYPES or ext in IMAGE_EXTENSIONS)
                and not part.get("Content-ID")  # inline embedded images have a cid
            )

            if is_pdf or is_image:
                payload = part.get_payload(decode=True)
                if payload:
                    pdf_attachments.append({
                        "filename": filename or ("priloha.jpg" if is_image else "faktura.pdf"),
                        "data": payload,
                        "is_image": is_image,
                    })

        if not pdf_attachments:
            return "skip"

        saved = 0
        for idx, attachment in enumerate(pdf_attachments):
            # Compound key: uid for first attachment, uid_1 / uid_2 etc. for extras
            compound_uid = uid if idx == 0 else f"{uid}_{idx}"

            # Skip if already processed
            existing = db.query(Invoice).filter(Invoice.email_uid == compound_uid).first()
            if existing:
                continue

            pdf_bytes = attachment["data"]
            original_filename = attachment["filename"]
            is_image = attachment.get("is_image", False)

            # Save attachment to disk
            safe_name = re.sub(r"[^\w\-_.]", "_", original_filename)
            stored_filename = f"{uid}_{idx}_{safe_name}" if len(pdf_attachments) > 1 else f"{uid}_{safe_name}"
            pdf_path = self.pdf_dir / stored_filename
            with open(pdf_path, "wb") as f:
                f.write(pdf_bytes)

            # Extract invoice data (OCR path for images, PDF path for PDFs)
            if is_image:
                extracted = extract_invoice_data_from_image(pdf_bytes, filename=original_filename)
            else:
                extracted = extract_invoice_data(pdf_bytes, filename=original_filename)

            invoice = Invoice(
                email_uid=compound_uid,
                email_uid_original=uid,
                attachment_index=idx,
                email_subject=subject[:500] if subject else None,
                email_from=from_header[:255] if from_header else None,
                email_date=email_date,
                ico=extracted.get("ico"),
                dic=extracted.get("dic"),
                company_name=extracted.get("company_name"),
                supplier_address=extracted.get("supplier_address"),
                customer_name=extracted.get("customer_name"),
                customer_ico=extracted.get("customer_ico"),
                customer_dic=extracted.get("customer_dic"),
                customer_address=extracted.get("customer_address"),
                issue_date=extracted.get("issue_date"),
                fulfillment_date=extracted.get("fulfillment_date"),
                due_date=extracted.get("due_date"),
                description=extracted.get("description"),
                amount_base_12=extracted.get("amount_base_12"),
                amount_vat_12=extracted.get("amount_vat_12"),
                amount_base_21=extracted.get("amount_base_21"),
                amount_vat_21=extracted.get("amount_vat_21"),
                amount_total=extracted.get("amount_total"),
                pdf_filename=stored_filename,
                pdf_path=str(pdf_path),
                doc_type=extracted.get("doc_type", "jine"),
                extraction_success=extracted.get("extraction_success", False),
                extraction_notes=extracted.get("extraction_notes"),
            )

            db.add(invoice)
            db.commit()
            db.refresh(invoice)
            logger.info(
                f"Saved invoice id={invoice.id} uid={compound_uid} "
                f"attachment={idx}/{len(pdf_attachments)-1} "
                f"company={invoice.company_name} type={invoice.doc_type}"
            )
            saved += 1

        if saved > 0:
            return "new"
        # All attachments were already present
        return "skip"


# ─── IMAP IDLE watcher ────────────────────────────────────────────────────────

class ImapIdleWatcher:
    """
    Keeps a persistent IMAP connection using IDLE command.
    When the server signals EXISTS (new mail), immediately fetches & processes it.
    Reconnects automatically on any error.
    Calls on_new_invoice() (if set) after saving each new invoice.
    """

    def __init__(self, db_factory: Callable[[], Session]):
        self._db_factory = db_factory
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.on_new_invoice: Optional[Callable] = None  # hook for WebSocket notify

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="imap-idle")
        self._thread.start()
        logger.info("IMAP IDLE watcher thread started")

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=10)
        logger.info("IMAP IDLE watcher stopped")

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._idle_loop()
            except Exception as e:
                logger.error(f"IMAP IDLE error, reconnecting in 30s: {e}")
                self._stop.wait(30)

    def _idle_loop(self) -> None:
        imap = imaplib.IMAP4_SSL(settings.IMAP_HOST, settings.IMAP_PORT)
        imap.login(settings.EMAIL_ADDRESS, settings.EMAIL_PASSWORD)
        imap.select("INBOX")
        logger.info("IMAP IDLE: connected and INBOX selected")

        # Set socket timeout so we can detect stale connections
        imap.socket().settimeout(600)  # 10 min — we'll re-IDLE before then

        while not self._stop.is_set():
            # Start IDLE
            imap.send(b"A001 IDLE\r\n")
            line = imap.readline()
            if b"+ idling" not in line.lower() and b"+ idle" not in line.lower():
                logger.warning(f"Unexpected IDLE response: {line}")
                break

            # Wait up to 25 minutes (RFC 2177 max is 29 min; we stay safe)
            new_mail = False
            deadline = time.monotonic() + 25 * 60
            while time.monotonic() < deadline and not self._stop.is_set():
                try:
                    imap.socket().settimeout(5)
                    line = imap.readline()
                    if line:
                        if b"EXISTS" in line:
                            logger.info(f"IMAP IDLE: new mail signal: {line.strip()}")
                            new_mail = True
                            break
                        # BYE / server disconnect
                        if line.startswith(b"* BYE"):
                            logger.info("IMAP IDLE: server sent BYE")
                            raise ConnectionError("Server sent BYE")
                except socket.timeout:
                    continue

            # End IDLE
            try:
                imap.send(b"A001 DONE\r\n")
                # Consume the OK response
                imap.readline()
            except Exception:
                pass

            if new_mail:
                self._fetch_new(imap)

        try:
            imap.logout()
        except Exception:
            pass

    def _fetch_new(self, imap: imaplib.IMAP4_SSL) -> None:
        """Fetch and process all UNSEEN messages."""
        try:
            status, data = imap.uid("search", None, "UNSEEN")
            if status != "OK" or not data[0]:
                return
            uids = data[0].split()
            logger.info(f"IMAP IDLE: processing {len(uids)} new message(s)")
            db = self._db_factory()
            fetcher = EmailFetcher()
            try:
                for uid_bytes in uids:
                    uid = uid_bytes.decode()
                    try:
                        result = fetcher._process_email(imap, uid, db)
                        if result == "new":
                            logger.info(f"IMAP IDLE: saved new invoice uid={uid}")
                            if self.on_new_invoice:
                                try:
                                    self.on_new_invoice()
                                except Exception as notify_err:
                                    logger.warning(f"on_new_invoice notify error: {notify_err}")
                    except Exception as e:
                        logger.error(f"IMAP IDLE: error processing uid={uid}: {e}")
            finally:
                db.close()
        except Exception as e:
            logger.error(f"IMAP IDLE fetch_new error: {e}")
