"""
SFC Public Register Scraper — v2
=================================
Layer 1a (Loop A): SFO licences (ratype 1-10,13) via searchByRaJson
Layer 1b (Loop B): AMLO Virtual Asset Service licence (ratypeamlo=101) via searchByRaJson
Layer 2a: /corp|indi/{ceref}/co           -> cofficerData (Complaints Officer tel/fax/email)
Layer 2b: /corp/{ceref}/addresses         -> emailData / websiteData / addressData
Layer 2c: /indi/{ceref}/addresses         -> indData (principal corp ceref only, NO email)
Output:   Single consolidated Excel sheet

============================================================
COMPLIANCE WARNING — READ BEFORE RUNNING AT SCALE
============================================================
robots.txt at https://apps.sfc.hk/robots.txt explicitly disallows:
    Disallow: /publicregWeb/
This script's entire target path falls under this disallowed path.
SFC's public register legal notice states data is for verification
purposes only. Run in small batches, throttle heavily (>=1.5s per
request), supervise manually. Do NOT run unattended 24/7.

============================================================
VERIFIED FACTS (tested 2026-08-01)
============================================================
- roleType          : "individual" | "corporation"              [CONFIRMED]
- ratype            : "1".."9","10","13" (SFO Loop A)          [CONFIRMED]
- ratypeamlo        : "101" (AMLO virtual asset, Loop B)        [CONFIRMED]
- ratype + ratypeamlo sent together = AND logic (not OR)        [CONFIRMED]
  -> MUST run as two separate loops, never combine
- nameStartLetter   : A-Z, REQUIRED (empty = 0 results)         [CONFIRMED]
- licstatus         : "active" | "all"                          [CONFIRMED]
- limit             : 1000, no pagination cap hit at this size  [CONFIRMED]
- Session/cookie    : NO warm-up GET needed. requests.Session()
  auto-handles BIGipServerPOOL_* / TS* cookies. 15 rapid calls  [CONFIRMED]
  all succeeded without prior page load.
- /corp/{ceref}/co  : tab label = "Complaints Officers"
  JS var: cofficerData = [{tel, fax, email, address}]            [CONFIRMED]
- /corp/{ceref}/addresses: JS vars emailData/websiteData/        [CONFIRMED]
  addressData (company-level email + website + principal address)
- /indi/{ceref}/addresses: JS var indData only. NO email/        [CONFIRMED]
  website. Only prinCeref/prinCeName/prinBusinessAddress.
- Individuals have NO /co tab. Do not call it.                   [CONFIRMED]
"""

import requests
import re
import json
import time
import logging
import pandas as pd
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("sfc_scraper")

# ── Constants ────────────────────────────────────────────────
BASE = "https://apps.sfc.hk/publicregWeb"
LIST_URL = f"{BASE}/searchByRaJson"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    ),
    "X-Requested-With": "XMLHttpRequest",
    "Referer": f"{BASE}/searchByRa",
}

ROLE_TYPES   = ["individual", "corporation"]
RA_TYPES     = ["1","2","3","4","5","6","7","8","9","10","13"]  # Loop A (SFO)
AMLO_RATYPE  = "101"                                                # Loop B (AMLO)
LETTERS      = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
LICSTATUS    = "active"

LIST_DELAY   = 1.5   # seconds between list requests
DETAIL_DELAY = 1.5   # seconds between detail page requests
SUB_DELAY    = 0.5   # seconds between /co and /addresses within same ceref
LIST_LIMIT   = 1000


# ── Helpers ──────────────────────────────────────────────────
def clean_val(v):
    """Return None for null-byte / empty values from SFC register."""
    if v in (None, "\u0000", "\x00", ""):
        return None
    return str(v).strip()


def extract_var(html, var_name):
    """Extract inline JS array: var <var_name> = [...];  Returns list or None."""
    m = re.search(rf"{var_name}\s*=\s*(\[.*?\])\s*;", html, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


# ── Layer 1 ── List scraping ──────────────────────────────────
def fetch_list(session, role_type, letter, ratype=None, ratypeamlo=None):
    payload = {
        "licstatus": LICSTATUS,
        "roleType": role_type,
        "nameStartLetter": letter,
        "page": 1, "start": 0, "limit": LIST_LIMIT,
    }
    if ratype     is not None: payload["ratype"]     = ratype
    if ratypeamlo is not None: payload["ratypeamlo"] = ratypeamlo

    dc   = int(time.time() * 1000)
    resp = session.post(f"{LIST_URL}?_dc={dc}", data=payload, timeout=20)
    resp.raise_for_status()
    return resp.json()


def collect_all_entities(session):
    """
    Loop A (SFO ratype 1-10,13) + Loop B (AMLO ratypeamlo=101).
    Returns deduplicated DataFrame; licence tags merged per ceref.
    """
    rows = []

    # ── Loop A: SFO ──
    for role_type in ROLE_TYPES:
        for ratype in RA_TYPES:
            for letter in LETTERS:
                try:
                    data  = fetch_list(session, role_type, letter, ratype=ratype)
                    items = data.get("items", [])
                except Exception as e:
                    log.warning(f"[LoopA] FAIL role={role_type} ra={ratype} L={letter}: {e}")
                    continue
                for it in items:
                    rows.append(_item_row(it, role_type, f"RA{ratype}"))
                log.info(f"[LoopA] role={role_type} ra={ratype} L={letter} -> {len(items)}")
                time.sleep(LIST_DELAY)

    # ── Loop B: AMLO ──
    for role_type in ROLE_TYPES:
        for letter in LETTERS:
            try:
                data  = fetch_list(session, role_type, letter, ratypeamlo=AMLO_RATYPE)
                items = data.get("items", [])
            except Exception as e:
                log.warning(f"[LoopB] FAIL role={role_type} L={letter}: {e}")
                continue
            for it in items:
                rows.append(_item_row(it, role_type, "AMLO101"))
            log.info(f"[LoopB] role={role_type} L={letter} -> {len(items)}")
            time.sleep(LIST_DELAY)

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    # Dedupe ceref; merge licence tags into comma list
    agg = (
        df.groupby(["ceref","name_eng","name_chi","role_type"], as_index=False)
        .agg(
            licence_tags      = ("licence_tag",  lambda s: ",".join(sorted(set(s)))),
            has_active_sfo    = ("has_active_licence",      "first"),
            has_active_amlo   = ("has_active_licence_amlo", "first"),
            address_from_list = ("address_from_list",       "first"),
        )
    )
    log.info(f"Unique entities after dedup: {len(agg)}")
    return agg


def _item_row(it, role_type, licence_tag):
    return {
        "ceref":                 it.get("ceref"),
        "name_eng":              it.get("name"),
        "name_chi":              it.get("nameChi"),
        "role_type":             role_type,
        "licence_tag":           licence_tag,
        "has_active_licence":    it.get("hasActiveLicence"),
        "has_active_licence_amlo": it.get("hasActiveLicenceAmlo"),
        "address_from_list":     (it.get("address") or {}).get("fullAddressChin"),
    }


# ── Layer 2 ── Contact extraction ────────────────────────────
def fetch_contact(session, ceref, role_type):
    """
    Corporation  : calls /co (cofficerData) + /addresses (emailData/websiteData/addressData)
    Individual   : calls /addresses only -> indData (prinCeref/prinCeName), NO email.
                   Does NOT call /co (tab does not exist for individuals).
    """
    path   = "corp" if role_type == "corporation" else "indi"
    result = {
        "co_tel":               None,
        "co_fax":               None,
        "co_email":             None,
        "co_address":           None,
        "company_email":        None,
        "company_website":      None,
        "company_address":      None,
        "indi_principal_ceref": None,
        "indi_principal_name":  None,
    }

    if role_type == "individual":
        # /addresses -> indData only; no email/website for individuals (CONFIRMED)
        try:
            r0 = session.get(f"{BASE}/{path}/{ceref}/addresses", timeout=20)
            ind = extract_var(r0.text, "indData")
            ind = [x for x in (ind or []) if isinstance(x, dict)]
            if ind:
                result["indi_principal_ceref"] = ind[0].get("prinCeref")
                result["indi_principal_name"]  = (
                    ind[0].get("prinCeNameChin") or ind[0].get("prinCeName")
                )
        except Exception as e:
            log.warning(f"[indi/addresses] {ceref}: {e}")
        return result

    # ── Corporation: /co ──
    try:
        r1      = session.get(f"{BASE}/{path}/{ceref}/co", timeout=20)
        coff    = extract_var(r1.text, "cofficerData")
        coff    = [c for c in (coff or []) if isinstance(c, dict)]
        if coff:
            c = coff[0]
            result["co_tel"]     = clean_val(c.get("tel"))
            result["co_fax"]     = clean_val(c.get("fax"))
            result["co_email"]   = clean_val(c.get("email"))
            addr = c.get("address") or {}
            result["co_address"] = addr.get("fullAddressChin") or addr.get("fullAddress")
    except Exception as e:
        log.warning(f"[corp/co] {ceref}: {e}")

    time.sleep(SUB_DELAY)

    # ── Corporation: /addresses ──
    try:
        r2       = session.get(f"{BASE}/{path}/{ceref}/addresses", timeout=20)
        emails   = extract_var(r2.text, "emailData")
        websites = extract_var(r2.text, "websiteData")
        addrs    = extract_var(r2.text, "addressData")
        # SFC returns [None] for absent email/website blocks -> filter out None elems
        emails   = [e for e in (emails   or []) if isinstance(e, dict)]
        websites = [w for w in (websites or []) if isinstance(w, dict)]
        addrs    = [a for a in (addrs    or []) if isinstance(a, dict)]
        if emails:   result["company_email"]   = clean_val(emails[0].get("email"))
        if websites: result["company_website"] = clean_val(websites[0].get("website"))
        if addrs:
            principal = next(
                (a for a in addrs if a.get("addrPrin") == "Y"), addrs[0]
            )
            result["company_address"] = (
                principal.get("fullAddressChin") or principal.get("fullAddress")
            )
    except Exception as e:
        log.warning(f"[corp/addresses] {ceref}: {e}")

    return result


def enrich_with_contacts(session, entities_df):
    records = []
    total   = len(entities_df)
    for i, (_, row) in enumerate(entities_df.iterrows(), 1):
        contact = fetch_contact(session, row["ceref"], row["role_type"])
        records.append({**row.to_dict(), **contact})
        if i % 50 == 0:
            log.info(f"Layer2 progress: {i}/{total}")
        time.sleep(DETAIL_DELAY)
    return pd.DataFrame(records)


# ── Output ───────────────────────────────────────────────────
EXCEL_COLUMNS = [
    "ceref",
    "name_eng",
    "name_chi",
    "role_type",
    "licence_tags",
    "has_active_sfo",
    "has_active_amlo",
    "co_email",
    "co_tel",
    "co_fax",
    "co_address",
    "company_email",
    "company_website",
    "company_address",
    "address_from_list",
    "indi_principal_ceref",
    "indi_principal_name",
]

def save_excel(df, filename=None):
    if filename is None:
        filename = f"../output/sfc_licensed_{datetime.now():%Y%m%d_%H%M}.xlsx"
    # reorder columns, keep any extras at end
    cols = [c for c in EXCEL_COLUMNS if c in df.columns]
    extras = [c for c in df.columns if c not in cols]
    df[cols + extras].to_excel(filename, index=False)
    log.info(f"Saved {len(df)} rows -> {filename}")
    return filename


# ── Main ─────────────────────────────────────────────────────
def main():
    session = requests.Session()
    session.headers.update(HEADERS)

    log.info("=== Layer 1: collecting entities (Loop A SFO + Loop B AMLO) ===")
    entities = collect_all_entities(session)
    raw_csv  = f"../output/sfc_list_raw_{datetime.now():%Y%m%d_%H%M}.csv"
    entities.to_csv(raw_csv, index=False)
    log.info(f"Raw list saved: {raw_csv} ({len(entities)} unique entities)")

    log.info("=== Layer 2: enriching contacts ===")
    full_df  = enrich_with_contacts(session, entities)

    save_excel(full_df)
    log.info("=== Done ===")


if __name__ == "__main__":
    main()
