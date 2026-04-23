"""ARES (Czech business registry) proxy with in-memory cache."""
import re
import logging
from typing import Optional, Dict

import httpx
from fastapi import APIRouter, Depends, HTTPException

from .invoices import get_user_flexible

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ares", tags=["ares"])

# Module-level cache: ico -> structured dict or None (not found / error)
_cache: Dict[str, Optional[Dict]] = {}


def _parse_ares(data: dict) -> dict:
    """Extract POHODA-relevant fields from raw ARES v2 response."""
    ico = data.get("ico") or ""
    dic = data.get("dic") or ""
    name = data.get("obchodniJmeno") or ""

    sidlo = data.get("sidlo") or {}

    # Street + house number
    ulice = sidlo.get("nazevUlice") or sidlo.get("nazevCastiObce") or ""
    cp = sidlo.get("cisloDomovni") or ""
    co = sidlo.get("cisloOrientacni") or ""
    if cp and co:
        cislo = f"{cp}/{co}"
    elif cp or co:
        cislo = str(cp or co)
    else:
        cislo = ""
    street = f"{ulice} {cislo}".strip() if ulice else cislo

    # City + ZIP
    obec = sidlo.get("nazevObce") or ""
    psc_raw = str(sidlo.get("psc") or "").replace(" ", "")
    psc = f"{psc_raw[:3]} {psc_raw[3:]}" if len(psc_raw) == 5 else psc_raw

    city_line = f"{psc} {obec}".strip()
    address_parts = [p for p in [street, city_line] if p]
    full_address = ", ".join(address_parts)

    # Fallback: use adresaDorucovaci radky
    if not full_address:
        dorucovaci = data.get("adresaDorucovaci") or {}
        radky = [dorucovaci.get(f"radekAdresy{i}") for i in range(1, 6)]
        full_address = ", ".join(r for r in radky if r)

    return {
        "ico": ico,
        "dic": dic,
        "company_name": name,
        "street": street,
        "city": obec,
        "zip": psc,
        "full_address": full_address,
        "country": "CZ",
    }


@router.get("/{ico}")
async def get_ares(
    ico: str,
    _: str = Depends(get_user_flexible),
):
    ico = ico.strip()
    if not re.fullmatch(r"\d{8}", ico):
        raise HTTPException(status_code=422, detail="IČO musí mít 8 číslic")

    if ico in _cache:
        cached = _cache[ico]
        if cached is None:
            raise HTTPException(status_code=404, detail="Subjekt nenalezen v ARES")
        return cached

    url = f"https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty/{ico}"
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(url, headers={"Accept": "application/json"})
    except Exception as e:
        logger.warning(f"ARES request failed for {ico}: {e}")
        raise HTTPException(status_code=502, detail="ARES nedostupný")

    if resp.status_code == 404:
        _cache[ico] = None
        raise HTTPException(status_code=404, detail="Subjekt nenalezen v ARES")

    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"ARES chyba: HTTP {resp.status_code}")

    try:
        parsed = _parse_ares(resp.json())
    except Exception as e:
        logger.error(f"ARES parse error for {ico}: {e}")
        raise HTTPException(status_code=502, detail="Chyba při zpracování dat z ARES")

    _cache[ico] = parsed
    return parsed
