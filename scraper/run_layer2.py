"""Stage runner: Layer 2 contact enrichment with incremental checkpointing.

Usage: python run_layer2.py <role_type>   # corporation | individual
Delays untouched (DETAIL_DELAY=1.5s, SUB_DELAY=0.5s).
Resumable: skips cerefs already present in the checkpoint CSV.
"""
import csv, os, sys, requests, logging
import pandas as pd
import sfc_scraper as s

log = logging.getLogger("sfc_scraper")

role = sys.argv[1]
ckpt = f"../output/layer2_{role}.csv"

ents = pd.read_csv("../output/sfc_list_raw.csv")
ents = ents[ents.role_type == role]

done = set()
if os.path.exists(ckpt):
    done = set(pd.read_csv(ckpt)["ceref"].astype(str))
    log.info(f"Resuming: {len(done)} already done")

FIELDS = ["ceref", "name_eng", "name_chi", "role_type", "licence_tags",
          "has_active_sfo", "has_active_amlo", "address_from_list",
          "co_tel", "co_fax", "co_email", "co_address",
          "company_email", "company_website", "company_address",
          "indi_principal_ceref", "indi_principal_name"]

sess = requests.Session()
sess.headers.update(s.HEADERS)

todo = ents[~ents.ceref.astype(str).isin(done)]
total = len(todo)
log.info(f"Layer2 {role}: {total} to fetch")

new_file = not os.path.exists(ckpt)
with open(ckpt, "a", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
    if new_file:
        w.writeheader()
    for i, (_, row) in enumerate(todo.iterrows(), 1):
        try:
            contact = s.fetch_contact(sess, row["ceref"], role)
        except Exception as e:
            log.warning(f"[layer2] {row['ceref']}: {e}")
            contact = {}
        w.writerow({**row.to_dict(), **contact})
        f.flush()
        if i % 50 == 0:
            log.info(f"Layer2 {role} progress: {i}/{total}")
        s.time.sleep(s.DETAIL_DELAY)

log.info(f"LAYER2 {role} DONE -> {ckpt}")
