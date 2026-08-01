"""Merge Layer 1 list + Layer 2 checkpoints into one master Excel sheet."""
import os, glob
from datetime import datetime
import pandas as pd

OUT = "../output"
base = pd.read_csv(f"{OUT}/sfc_list_raw.csv", dtype=str)

frames = []
for f in glob.glob(f"{OUT}/layer2_*.csv"):
    frames.append(pd.read_csv(f, dtype=str))
enrich = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

CONTACT = ["co_tel", "co_fax", "co_email", "co_address",
           "company_email", "company_website", "company_address",
           "indi_principal_ceref", "indi_principal_name"]
if len(enrich):
    enrich = enrich.drop_duplicates(subset=["ceref"], keep="last")
    enrich = enrich[["ceref"] + [c for c in CONTACT if c in enrich.columns]]
    df = base.merge(enrich, on="ceref", how="left")
else:
    df = base
    for c in CONTACT:
        df[c] = None

for c in CONTACT:
    if c not in df.columns:
        df[c] = None

df["detail_url"] = df.apply(
    lambda r: f"https://apps.sfc.hk/publicregWeb/"
              f"{'corp' if r['role_type'] == 'corporation' else 'indi'}/{r['ceref']}/details",
    axis=1)

cols = ["ceref", "name_eng", "name_chi", "role_type", "licence_tags",
        "has_active_sfo", "has_active_amlo",
        "co_tel", "co_fax", "co_email", "co_address",
        "company_email", "company_website", "company_address",
        "indi_principal_ceref", "indi_principal_name",
        "address_from_list", "detail_url"]
df = df[[c for c in cols if c in df.columns]]
df = df.sort_values(["role_type", "ceref"], ascending=[False, True])

ts = datetime.now().strftime("%Y%m%d_%H%M")
path = f"{OUT}/sfc_licensed_{ts}.xlsx"
with pd.ExcelWriter(path, engine="openpyxl") as w:
    df.to_excel(w, sheet_name="SFC_Licensed_Master", index=False)
    ws = w.sheets["SFC_Licensed_Master"]
    ws.freeze_panes = "A2"
    widths = {"A": 10, "B": 46, "C": 24, "D": 14, "E": 16, "F": 14, "G": 14,
              "H": 16, "I": 16, "J": 34, "K": 52, "L": 34, "M": 30, "N": 52,
              "O": 14, "P": 34, "Q": 52, "R": 56}
    for k, v in widths.items():
        ws.column_dimensions[k].width = v

print("rows:", len(df))
print("corporations:", (df.role_type == "corporation").sum())
print("individuals:", (df.role_type == "individual").sum())
print("with co_email:", df.co_email.notna().sum())
print("with company_email:", df.company_email.notna().sum())
print("with company_website:", df.company_website.notna().sum())
print("with principal corp (indi):", df.indi_principal_name.notna().sum())
print("AMLO tagged:", df.licence_tags.str.contains("AMLO101", na=False).sum())
print("saved:", os.path.abspath(path))
