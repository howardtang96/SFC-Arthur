# SFC-Arthur — SFC Public Register Scraper

Private repo. Scrapes [SFC Public Register](https://apps.sfc.hk/publicregWeb/searchByRa) for licensed persons/corporations contact data.

---

## ⚠️ Compliance Notice

`robots.txt` at `https://apps.sfc.hk/robots.txt` explicitly disallows:
```
Disallow: /publicregWeb/
```
SFC legal notice states register data is for **verification purposes only**.
**Run in supervised batches only. Do NOT run unattended at high frequency.**

---

## Verified Architecture (all facts confirmed by live HTTP tests 2026-08-01)

### Layer 1 — Entity List

**Endpoint:** `POST https://apps.sfc.hk/publicregWeb/searchByRaJson?_dc={timestamp}`

**Loop A (SFO Licences):**
```
for role_type in [individual, corporation]
  for ratype in [1,2,3,4,5,6,7,8,9,10,13]
    for letter in A..Z
      POST {licstatus:active, roleType, ratype, nameStartLetter:letter, limit:1000}
```

**Loop B (AMLO Virtual Asset — independent loop):**
```
for role_type in [individual, corporation]
  for letter in A..Z
    POST {licstatus:active, roleType, ratypeamlo:101, nameStartLetter:letter, limit:1000}
```

> ⚠️ `ratype` and `ratypeamlo` use AND logic if sent together.
> Always run as **separate loops**.

**Response fields used:**
```json
{
  "ceref": "BUC628",
  "name": "Company English Name",
  "nameChi": "公司中文名",
  "hasActiveLicence": "Y",
  "hasActiveLicenceAmlo": "N",
  "address": {"fullAddressChin": "...", "addrPrin": "Y"}
}
```

**Dedup:** group by `ceref`, merge `licence_tags` as comma list (e.g. `RA1,RA9,AMLO101`).

---

### Layer 2 — Contact Extraction

#### Corporation (`role_type = corporation`)

**2a. Complaints Officer**
```
GET /publicregWeb/corp/{ceref}/co
Extract JS var: cofficerData = [{tel, fax, email, address:{fullAddressChin}}]
```
Tab label on site: **"Complaints Officers"** — this is NOT a general contact,
it is the designated complaints handling officer. Still the most reliable
direct email in the register.

**2b. Company Address / Email / Website**
```
GET /publicregWeb/corp/{ceref}/addresses
Extract JS vars:
  emailData   = [{email}]
  websiteData = [{website}]
  addressData = [{fullAddressChin, addrPrin:"Y"}]
```
Pick address where `addrPrin == "Y"` as principal business address.

#### Individual (`role_type = individual`)

```
GET /publicregWeb/indi/{ceref}/addresses
Extract JS var: indData = [{prinCeref, prinCeName, prinCeNameChin, prinBusinessAddress}]
```
> Individuals have **NO** email or website in the register.
> Only their associated licensed corporation (`prinCeref`) is available.
> Individuals have **NO** `/co` tab — do not call it.

---

### Session / Cookie
- `requests.Session()` is sufficient — **no warm-up GET required**.
- Server auto-sets `BIGipServerPOOL_*` and `TS*` load balancer cookies on first response.
- Confirmed: 15 consecutive POSTs with no prior page load = 0 failures.

---

## Output Excel Schema

| Column | Source | Notes |
|---|---|---|
| `ceref` | Layer 1 | SFC Central Entity Reference |
| `name_eng` | Layer 1 | English name |
| `name_chi` | Layer 1 | Chinese name |
| `role_type` | Layer 1 | `individual` / `corporation` |
| `licence_tags` | Layer 1 | e.g. `RA1,RA9,AMLO101` |
| `has_active_sfo` | Layer 1 | `Y`/`N` |
| `has_active_amlo` | Layer 1 | `Y`/`N` |
| `co_email` | Layer 2a | Complaints Officer email |
| `co_tel` | Layer 2a | Complaints Officer tel |
| `co_fax` | Layer 2a | Complaints Officer fax |
| `co_address` | Layer 2a | Complaints Officer address |
| `company_email` | Layer 2b | Company general email |
| `company_website` | Layer 2b | Company website |
| `company_address` | Layer 2b | Principal business address |
| `address_from_list` | Layer 1 | Address returned in list response |
| `indi_principal_ceref` | Layer 2c | For individuals: employer corp ceref |
| `indi_principal_name` | Layer 2c | For individuals: employer corp name |

---

## Rate Limiting

| Delay | Value | Applied between |
|---|---|---|
| `LIST_DELAY` | 1.5s | Each list POST (Loop A / B) |
| `DETAIL_DELAY` | 1.5s | Each entity's Layer 2 fetch cycle |
| `SUB_DELAY` | 0.5s | Between `/co` and `/addresses` for same ceref |

---

## Setup

```bash
cd scraper
pip install -r requirements.txt
python sfc_scraper.py
```

Output saved to `output/sfc_licensed_YYYYMMDD_HHMM.xlsx`

---

## Repo Structure

```
SFC-Arthur/
├── README.md
├── .gitignore
├── scraper/
│   ├── sfc_scraper.py
│   └── requirements.txt
└── output/          ← gitignored, Excel files saved here
    └── .gitkeep
```
