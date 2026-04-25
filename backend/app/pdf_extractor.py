import os
import re
import logging
from typing import Optional, Tuple
from datetime import datetime
from io import BytesIO

import pdfplumber
from dateutil import parser as date_parser

logger = logging.getLogger(__name__)

# ─── Known accounting clients (odběratelé) ───────────────────────────────────

KNOWN_CUSTOMERS = frozenset([
    "restart - pubs s.r.o.",
    "restart - beer s.r.o.",
    "restart-bar s.r.o.",
    "restart pubs s.r.o.",
    "restart beer s.r.o.",
    "restart bar s.r.o.",
    "restart-bar",
])

# ─── Regex patterns ──────────────────────────────────────────────────────────

ICO_PATTERN = re.compile(
    r'(?:IČO?|ICO?)\s*[:\s]\s*(\d{8})\b',
    re.IGNORECASE,
)

DIC_PATTERN = re.compile(
    r'(?:DIČ|DIC)\s*[:\s]\s*(CZ\d{8,10})\b',
    re.IGNORECASE,
)

DATE_PATTERNS = [
    # Labeled Czech dates
    (re.compile(r'(?:datum\s+vystavení|datum\s+vystaveni|vystaveno)\s*[:\s]+(\d{1,2}[.\-/]\d{1,2}[.\-/]\d{4})', re.IGNORECASE), 'issue'),
    (re.compile(r'(?:datum\s+(?:zdanitelného\s+)?plnění|datum\s+(?:zdanitelneho\s+)?plneni|datum\s+uskut\.?\s+zda[nň]\.?(?:\s+pln[eě]n[ií])?|uskutečnění|uskutecneni)\s*[:\s]+(\d{1,2}[.\-/]\d{1,2}[.\-/]\d{4})', re.IGNORECASE), 'fulfillment'),
    (re.compile(r'(?:datum\s+splatnosti|splatnost)\s*[:\s]+(\d{1,2}[.\-/]\d{1,2}[.\-/]\d{4})', re.IGNORECASE), 'due'),
]

# Generic date finder for fallback
GENERIC_DATE_PATTERN = re.compile(r'\b(\d{1,2}[.]\d{1,2}[.]\d{4})\b')

# Amount patterns for Czech locale (e.g. "1 500,00" or "1500,00" or "1500.00")
AMOUNT_PATTERN = re.compile(
    r'(\d{1,3}(?:[\s\u00a0]\d{3})*(?:[,.]\d{2})?)',
)

VAT_SECTION_PATTERNS = [
    # "základ 12 % ... 1 000,00 ... 120,00"
    re.compile(r'(?:základ|zaklad)\s+(?:DPH\s+)?12\s*%[^\n]*?([\d\s]+[,.]\d{2})', re.IGNORECASE),
    re.compile(r'(?:základ|zaklad)\s+(?:DPH\s+)?21\s*%[^\n]*?([\d\s]+[,.]\d{2})', re.IGNORECASE),
    re.compile(r'(?:DPH|dph)\s+12\s*%[^\n]*?([\d\s]+[,.]\d{2})', re.IGNORECASE),
    re.compile(r'(?:DPH|dph)\s+21\s*%[^\n]*?([\d\s]+[,.]\d{2})', re.IGNORECASE),
    re.compile(r'celkem\s+(?:k\s+úhradě|k\s+uhrade|s\s+DPH)?[^\n]*?([\d\s]+[,.]\d{2})', re.IGNORECASE),
]

TOTAL_PATTERN = re.compile(
    r'(?:celkem\s+(?:k\s+úhradě|k\s+uhrade|s\s+DPH|včetně\s+DPH|vcetne\s+dph)?)\s*[:\s]?\s*([\d\s]+[,.]\d{2})',
    re.IGNORECASE,
)

DESCRIPTION_KEYWORDS = re.compile(
    r'(?:předmět\s+plnění|predmet\s+plneni|popis\s+(?:plnění|prací|zboží|služeb)|popis)',
    re.IGNORECASE,
)

# Supplier keywords — we want the DODAVATEL's IČ/DIČ, not ours
SUPPLIER_KEYWORDS = re.compile(
    r'(?:dodavatel|prodávající|vystavil|fakturujeme|vystavuje)',
    re.IGNORECASE,
)
CUSTOMER_KEYWORDS = re.compile(
    r'(?:odběratel|odberatel|kupující|kupujici|fakturujeme\s+v[aá]m|fakturujeme\s+vam'
    r'|příjemce\s+faktury|prijemce\s+faktury|zákazník|zakaznik|komu\s+fakturujeme'
    r'|faktura\s+pro|fakturováno|fakturovano)',
    re.IGNORECASE,
)

# ─── Document type detection keywords ────────────────────────────────────────
# Filename patterns checked first (most reliable signal)
DOC_TYPE_FILENAME_PATTERNS = [
    ("dobropis",        re.compile(r'dobropis|opravny|credit', re.IGNORECASE)),
    ("uctenka",         re.compile(r'u[c\u010d]tenk|paragon|stvrzenk|receipt|pokladn', re.IGNORECASE)),
    ("faktura_vydana",  re.compile(r'vydana|vydan[aá]|issued', re.IGNORECASE)),
    ("faktura_prijata", re.compile(r'prijata|p[rř]ijat[aá]|received|fakt[uo]r|invoice', re.IGNORECASE)),
]
# Text content patterns (checked second)
DOC_TYPE_TEXT_PATTERNS = [
    ("dobropis", re.compile(r'\b(?:dobropis|opravný\s+daňový\s+doklad|credit\s+note|storno\s+faktura)\b', re.IGNORECASE)),
    ("uctenka",  re.compile(r'\b(?:u\u010dtenka|paragon|pokladní\s+(?:doklad|blok)|receipt|stvrzenka)\b', re.IGNORECASE)),
    # plain "faktura" in text — vydana/prijata resolved in detect_doc_type
    ("faktura",  re.compile(r'\b(?:faktura|daňový\s+doklad|invoice)\b', re.IGNORECASE)),
]

# Czech ZIP code pattern (123 45 or 12345)
ZIP_CITY_RE = re.compile(
    r'\b(\d{3}\s?\d{2})\s+([\w\s\u00C0-\u024F\-]+?)(?:\s*\n|,|$)',
    re.UNICODE,
)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def parse_czech_amount(text: str) -> Optional[float]:
    """Convert Czech-formatted number string to float."""
    if not text:
        return None
    cleaned = re.sub(r'[\s\u00a0]', '', text)  # remove space/nbsp thousand separators
    cleaned = cleaned.replace(',', '.')
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_czech_date(text: str) -> Optional[datetime]:
    """Parse date from Czech DD.MM.YYYY or ISO format."""
    if not text:
        return None
    text = text.strip()
    # Try DD.MM.YYYY
    m = re.match(r'(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})', text)
    if m:
        try:
            return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            pass
    try:
        return date_parser.parse(text, dayfirst=True)
    except Exception:
        return None


def extract_text_from_pdf(pdf_bytes: bytes) -> Tuple[str, bool]:
    """
    Extract full text from PDF bytes.
    Returns (text, ocr_used).
    Falls back to OCR via Tesseract when the PDF contains no selectable text.
    """
    # ── 1. Native text extraction via pdfplumber ──────────────────────────────
    try:
        with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
            pages_text = []
            for page in pdf.pages:
                text = page.extract_text(x_tolerance=3, y_tolerance=3)
                if text:
                    pages_text.append(text)
            native_text = "\n".join(pages_text)
    except Exception as e:
        logger.error(f"pdfplumber extraction failed: {e}")
        native_text = ""

    if len(native_text.strip()) > 50:
        return native_text, False

    # ── 2. OCR fallback (scanned PDFs / receipts) ─────────────────────────────
    logger.info("Native PDF text too short — attempting OCR")
    try:
        import pytesseract
        from pdf2image import convert_from_bytes
        import shutil

        # Locate poppler binaries (macOS Homebrew may not be on PATH)
        poppler_path: Optional[str] = None
        if not shutil.which("pdftoppm"):
            for candidate in ["/opt/homebrew/bin", "/usr/local/bin"]:
                if os.path.exists(os.path.join(candidate, "pdftoppm")):
                    poppler_path = candidate
                    break

        convert_kwargs: dict = {"dpi": 300}
        if poppler_path:
            convert_kwargs["poppler_path"] = poppler_path

        images = convert_from_bytes(pdf_bytes, **convert_kwargs)
        ocr_pages = []
        for img in images:
            text = pytesseract.image_to_string(img, lang="ces+eng", config="--psm 3")
            if text:
                ocr_pages.append(text)
        ocr_text = "\n".join(ocr_pages)
        if ocr_text.strip():
            logger.info(f"OCR produced {len(ocr_text)} chars")
            return ocr_text, True
    except Exception as e:
        logger.warning(f"OCR fallback failed: {e}")

    return native_text, False


def extract_text_from_image(image_bytes: bytes) -> Tuple[str, bool]:
    """Extract text from an image file (JPG/PNG) via OCR."""
    try:
        import pytesseract
        from PIL import Image
        img = Image.open(BytesIO(image_bytes))
        text = pytesseract.image_to_string(img, lang="ces+eng", config="--psm 3")
        logger.info(f"Image OCR produced {len(text)} chars")
        return text, True
    except Exception as e:
        logger.warning(f"Image OCR failed: {e}")
        return "", False


def detect_doc_type(text: str, filename: str = "") -> str:
    """
    Classify document: faktura_prijata | faktura_vydana | dobropis | uctenka | jine.
    Filename is checked first (most reliable signal), then document text.
    """
    fn_clean = filename.lower().replace("_", " ").replace("-", " ")
    for doc_type, pattern in DOC_TYPE_FILENAME_PATTERNS:
        if pattern.search(fn_clean):
            return doc_type
    for doc_type, pattern in DOC_TYPE_TEXT_PATTERNS:
        if pattern.search(text):
            if doc_type == "faktura":
                # Distinguish vydana vs prijata by checking if a known customer appears
                text_lower = text.lower()
                for customer in KNOWN_CUSTOMERS:
                    if customer in text_lower:
                        return "faktura_vydana"
                return "faktura_prijata"
            return doc_type
    return "jine"


# ─── Main extraction ─────────────────────────────────────────────────────────

def extract_invoice_data(pdf_bytes: bytes, filename: str = "") -> dict:
    """Extract structured invoice data from PDF bytes."""
    text, ocr_used = extract_text_from_pdf(pdf_bytes)
    return _build_result(text, ocr_used, filename)


def extract_invoice_data_from_image(image_bytes: bytes, filename: str = "") -> dict:
    """Extract invoice data from an image attachment (JPG/PNG)."""
    text, ocr_used = extract_text_from_image(image_bytes)
    return _build_result(text, ocr_used, filename, default_doc_type="uctenka")


def _build_result(text: str, ocr_used: bool, filename: str = "", default_doc_type: str = "jine") -> dict:
    result = {
        "ico": None,
        "dic": None,
        "company_name": None,
        "supplier_address": None,
        "customer_name": None,
        "customer_ico": None,
        "customer_dic": None,
        "customer_address": None,
        "issue_date": None,
        "fulfillment_date": None,
        "due_date": None,
        "description": None,
        "amount_base_12": None,
        "amount_vat_12": None,
        "amount_base_21": None,
        "amount_vat_21": None,
        "amount_total": None,
        "doc_type": default_doc_type,
        "extraction_success": False,
        "extraction_notes": "",
    }

    if not text.strip():
        result["extraction_notes"] = "Dokument neobsahuje extrahovatelný text"
        return result

    notes = []
    if ocr_used:
        notes.append("OCR použito")

    lines = text.splitlines()

    # ── Document type ─────────────────────────────────────────────────────────
    detected = detect_doc_type(text, filename)
    result["doc_type"] = detected if detected != "jine" else default_doc_type

    # ── IČ / DIČ (supplier) ───────────────────────────────────────────────────
    all_icos = ICO_PATTERN.findall(text)
    all_dics = DIC_PATTERN.findall(text)

    supplier_ico = _find_near_keyword(text, ICO_PATTERN, SUPPLIER_KEYWORDS, CUSTOMER_KEYWORDS)
    result["ico"] = supplier_ico or (all_icos[0] if all_icos else None)

    supplier_dic = _find_near_keyword(text, DIC_PATTERN, SUPPLIER_KEYWORDS, CUSTOMER_KEYWORDS)
    result["dic"] = supplier_dic or (all_dics[0] if all_dics else None)

    if not result["ico"]:
        notes.append("IČ nenalezeno")
    if not result["dic"]:
        notes.append("DIČ nenalezeno")

    # ── Company name + address (supplier) ─────────────────────────────────────
    result["company_name"] = _extract_company_name(text, lines, result["ico"])
    result["supplier_address"] = _extract_address_near_ico(text, result["ico"])

    # ── Customer info ──────────────────────────────────────────────────────────
    customer = _extract_customer_info(text, lines)
    result["customer_name"] = customer["name"]
    result["customer_ico"] = customer["ico"]
    result["customer_dic"] = customer["dic"]
    result["customer_address"] = customer["address"]

    # ── Dates ─────────────────────────────────────────────────────────────────
    for pattern, date_type in DATE_PATTERNS:
        match = pattern.search(text)
        if match:
            parsed = parse_czech_date(match.group(1))
            if date_type == 'issue':
                result["issue_date"] = parsed
            elif date_type == 'fulfillment':
                result["fulfillment_date"] = parsed
            elif date_type == 'due':
                result["due_date"] = parsed

    if not any([result["issue_date"], result["fulfillment_date"], result["due_date"]]):
        generic_dates = GENERIC_DATE_PATTERN.findall(text)
        unique_dates = list(dict.fromkeys(generic_dates))
        parsed_dates = [parse_czech_date(d) for d in unique_dates if parse_czech_date(d)]
        if len(parsed_dates) >= 1:
            result["issue_date"] = parsed_dates[0]
        if len(parsed_dates) >= 2:
            result["fulfillment_date"] = parsed_dates[1]
        if len(parsed_dates) >= 3:
            result["due_date"] = parsed_dates[2]

    if not result["issue_date"]:
        notes.append("Datum vystavení nenalezeno")

    # ── Description / Předmět plnění ──────────────────────────────────────────
    result["description"] = _extract_description(text, lines)

    # ── Amounts ───────────────────────────────────────────────────────────────
    _extract_amounts(text, result)

    if result["amount_total"] is None:
        notes.append("Celková částka nenalezena")

    result["extraction_success"] = bool(result["ico"] or result["company_name"] or result["amount_total"])
    result["extraction_notes"] = "; ".join(notes) if notes else "OK"

    return result


# ─── Private helpers ─────────────────────────────────────────────────────────

def _find_near_keyword(text: str, value_pattern: re.Pattern,
                       positive_kw: re.Pattern, negative_kw: re.Pattern) -> Optional[str]:
    """Find value_pattern match that appears near positive keywords but not near negative ones."""
    for match in value_pattern.finditer(text):
        start = max(0, match.start() - 300)
        end = min(len(text), match.end() + 100)
        context = text[start:end]
        if positive_kw.search(context) and not negative_kw.search(context):
            return match.group(1)
    return None


def _extract_company_name(text: str, lines: list, ico: Optional[str]) -> Optional[str]:
    """Try to extract supplier company name."""
    # Strategy 1: look for line immediately before IČ
    if ico:
        ico_match = re.search(re.escape(ico), text)
        if ico_match:
            before = text[:ico_match.start()]
            before_lines = [l.strip() for l in before.splitlines() if l.strip()]
            # Walk back to find a plausible company name line
            for line in reversed(before_lines[-5:]):
                # Skip lines that look like labels or addresses
                if re.match(r'^(?:IČ|DIČ|ulice|č\.|PSČ|tel|email|www|dodavatel|odběratel)', line, re.IGNORECASE):
                    continue
                if len(line) > 3 and not re.match(r'^\d', line):
                    return line
    # Strategy 2: look after "dodavatel:" keyword
    m = re.search(r'(?:dodavatel|prodávající)\s*:?\s*\n?(.+)', text, re.IGNORECASE)
    if m:
        candidate = m.group(1).strip().splitlines()[0].strip()
        if candidate:
            return candidate

    return None


def _extract_address_near_ico(text: str, ico: Optional[str]) -> Optional[str]:
    """Extract supplier address - ZIP code + street near the IČO block."""
    if not ico:
        return None
    ico_match = re.search(re.escape(ico), text)
    if not ico_match:
        return None
    surrounding = text[max(0, ico_match.start() - 400):ico_match.end() + 200]
    m = ZIP_CITY_RE.search(surrounding)
    if m:
        before_zip = surrounding[:m.start()].strip()
        street_lines = [
            l.strip() for l in before_zip.splitlines()
            if l.strip() and not re.match(r'^(?:IČ|DIČ|tel|e-?mail|www)', l.strip(), re.IGNORECASE)
        ]
        street = street_lines[-1] if street_lines else ""
        city_part = f"{m.group(1)} {m.group(2).strip()}"
        return f"{street}, {city_part}" if street else city_part
    return None


def _extract_customer_info(text: str, lines: list) -> dict:
    """Extract odběratel (customer) info using keyword blocks and known-company list."""
    result: dict = {"name": None, "ico": None, "dic": None, "address": None}

    customer_m = CUSTOMER_KEYWORDS.search(text)
    if customer_m:
        block_start = customer_m.end()
        next_section = re.search(
            r'\b(?:dodavatel|prodávající|vystavuje|předmět\s+plnění|faktura\s+č|číslo\s+faktury|datum)\b',
            text[block_start:block_start + 600], re.IGNORECASE,
        )
        block_end = block_start + (next_section.start() if next_section else 600)
        block = text[block_start:block_end]

        ico_m = ICO_PATTERN.search(block)
        if ico_m:
            result["ico"] = ico_m.group(1)
        dic_m = DIC_PATTERN.search(block)
        if dic_m:
            result["dic"] = dic_m.group(1)

        for line in block.splitlines():
            line = line.strip()
            # Strip leading colon/spaces — handles "Odběratel: Firma XYZ" on same line
            line = re.sub(r'^[:\s]+', '', line).strip()
            if line and len(line) > 3 and not re.match(
                r'^(?:IČ|DIČ|tel|e-?mail|www|odběratel|\d)', line, re.IGNORECASE
            ):
                result["name"] = line
                break

        zip_m = ZIP_CITY_RE.search(block)
        if zip_m:
            before_zip = block[:zip_m.start()].strip()
            street_lines = [
                l.strip() for l in before_zip.splitlines()
                if l.strip() and not re.match(
                    r'^(?:IČ|DIČ|tel|e-?mail|www|odběratel)', l.strip(), re.IGNORECASE
                )
            ]
            street = street_lines[-1] if len(street_lines) > 1 else ""
            city_part = f"{zip_m.group(1)} {zip_m.group(2).strip()}"
            result["address"] = f"{street}, {city_part}" if street else city_part

    # Fallback: scan for known customer company names
    if not result["name"]:
        text_lower = text.lower()
        for customer in KNOWN_CUSTOMERS:
            if customer in text_lower:
                idx = text_lower.find(customer)
                result["name"] = text[idx: idx + len(customer)]
                # Also look for IČO / DIČ in vicinity (300 chars around the name)
                vicinity = text[max(0, idx - 100): idx + len(customer) + 300]
                if not result["ico"]:
                    ico_m = ICO_PATTERN.search(vicinity)
                    if ico_m:
                        result["ico"] = ico_m.group(1)
                if not result["dic"]:
                    dic_m = DIC_PATTERN.search(vicinity)
                    if dic_m:
                        result["dic"] = dic_m.group(1)
                if not result["address"]:
                    zip_m = ZIP_CITY_RE.search(vicinity)
                    if zip_m:
                        result["address"] = f"{zip_m.group(1)} {zip_m.group(2).strip()}"
                break

    return result


def _extract_description(text: str, lines: list) -> Optional[str]:
    """Extract předmět plnění / description."""
    # Look for labeled description
    m = DESCRIPTION_KEYWORDS.search(text)
    if m:
        rest = text[m.end():].strip()
        # Take next non-empty line
        for line in rest.splitlines():
            line = line.strip()
            if line and len(line) > 2:
                return line[:500]

    # Fallback: find line items table — look for first line that looks like a product/service
    in_items = False
    for line in lines:
        line_stripped = line.strip()
        # Detect start of line items section
        if re.match(r'(?:položka|popis|název|služba|zboží)', line_stripped, re.IGNORECASE):
            in_items = True
            continue
        if in_items and line_stripped and not re.match(r'^\d+[\s,.]', line_stripped):
            if len(line_stripped) > 5:
                return line_stripped[:500]

    return None


def _extract_amounts(text: str, result: dict) -> None:
    """Extract VAT breakdown amounts from text."""

    def find_amount_after(pattern: re.Pattern) -> Optional[float]:
        m = pattern.search(text)
        if m:
            # Try to find the first proper number after the match
            rest = text[m.end():m.end() + 200]
            nums = re.findall(r'([\d\s\u00a0]+[,.]\d{2})', rest)
            if nums:
                return parse_czech_amount(nums[0])
        return None

    # ── Pattern: table with columns Základ / DPH / Celkem by sazba ────────────
    # Try structured extraction: find 12% and 21% rows
    base12_p = re.compile(r'(?:12\s*%|sníž[ea]ná)[^\n]{0,60}?([\d\s\u00a0]+[,.]\d{2})', re.IGNORECASE)
    base21_p = re.compile(r'(?:21\s*%|základní|zákl\.)[^\n]{0,60}?([\d\s\u00a0]+[,.]\d{2})', re.IGNORECASE)
    vat12_p  = re.compile(r'(?:DPH\s+)?12\s*%[^\n]{0,60}?([\d\s\u00a0]+[,.]\d{2})[^\n]{0,60}?([\d\s\u00a0]+[,.]\d{2})', re.IGNORECASE)
    vat21_p  = re.compile(r'(?:DPH\s+)?21\s*%[^\n]{0,60}?([\d\s\u00a0]+[,.]\d{2})[^\n]{0,60}?([\d\s\u00a0]+[,.]\d{2})', re.IGNORECASE)

    # Try to find a VAT summary table
    # Common format:
    # Sazba  Základ  DPH    Celkem
    # 21 %   1000    210    1210
    # 12 %   500     60     560

    # Search for 21% row with 2-3 numbers
    m21 = vat21_p.search(text)
    if m21:
        result["amount_base_21"] = parse_czech_amount(m21.group(1))
        result["amount_vat_21"]  = parse_czech_amount(m21.group(2))

    m12 = vat12_p.search(text)
    if m12:
        result["amount_base_12"] = parse_czech_amount(m12.group(1))
        result["amount_vat_12"]  = parse_czech_amount(m12.group(2))

    # Fallback: look for základ DPH 12/21 labeled lines
    if result["amount_base_12"] is None:
        m = re.search(r'základ\s+(?:DPH\s+)?12\s*%\s*[:\s]*([\d\s\u00a0]+[,.]\d{2})', text, re.IGNORECASE)
        if m:
            result["amount_base_12"] = parse_czech_amount(m.group(1))

    if result["amount_base_21"] is None:
        m = re.search(r'základ\s+(?:DPH\s+)?21\s*%\s*[:\s]*([\d\s\u00a0]+[,.]\d{2})', text, re.IGNORECASE)
        if m:
            result["amount_base_21"] = parse_czech_amount(m.group(1))

    if result["amount_vat_12"] is None:
        m = re.search(r'(?:výše\s+)?DPH\s+12\s*%\s*[:\s]*([\d\s\u00a0]+[,.]\d{2})', text, re.IGNORECASE)
        if m:
            result["amount_vat_12"] = parse_czech_amount(m.group(1))

    if result["amount_vat_21"] is None:
        m = re.search(r'(?:výše\s+)?DPH\s+21\s*%\s*[:\s]*([\d\s\u00a0]+[,.]\d{2})', text, re.IGNORECASE)
        if m:
            result["amount_vat_21"] = parse_czech_amount(m.group(1))

    # ── Total amount ──────────────────────────────────────────────────────────
    m_total = TOTAL_PATTERN.search(text)
    if m_total:
        result["amount_total"] = parse_czech_amount(m_total.group(1))

    # Fallback: sum up what we have
    if result["amount_total"] is None:
        parts = [
            result.get("amount_base_12") or 0,
            result.get("amount_vat_12") or 0,
            result.get("amount_base_21") or 0,
            result.get("amount_vat_21") or 0,
        ]
        if any(parts):
            result["amount_total"] = round(sum(parts), 2)
