"""Sharded Layer 2 runner: python run_layer2_shard.py <role> <shard_idx> <n_shards>

Each shard uses its own HTTP session and keeps the unmodified 1.5s per-request
delay. Shards are resumable via their own checkpoint CSV, and skip any ceref
already captured by the single-threaded checkpoint.
"""
import csv, os, sys, requests, logging
import pandas as pd
import sfc_scraper as s

role, idx, n = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
log = logging.getLogger(f"shard{idx}")
logging.basicConfig(level=logging.INFO,
                    format=f"%(asctime)s [s{idx}] %(message)s")

ckpt = f"../output/layer2_{role}_s{idx}.csv"
ents = pd.read_csv("../output/sfc_list_raw.csv", dtype=str)
ents = ents[ents.role_type == role].reset_index(drop=True)

done = set()
main_ck = f"../output/layer2_{role}.csv"
if os.path.exists(main_ck):
    done |= set(pd.read_csv(main_ck, dtype=str)["ceref"])
if os.path.exists(ckpt) and os.path.getsize(ckpt) > 0:
    done |= set(pd.read_csv(ckpt, dtype=str)["ceref"])

FIELDS = ["ceref", "name_eng", "name_chi", "role_type", "licence_tags",
          "has_active_sfo", "has_active_amlo", "address_from_list",
          "co_tel", "co_fax", "co_email", "co_address",
          "company_email", "company_website", "company_address",
          "indi_principal_ceref", "indi_principal_name"]

todo = ents[(ents.index % n == idx) & (~ents.ceref.isin(done))]
log.info(f"shard {idx}/{n}: {len(todo)} to fetch")

sess = requests.Session()
sess.headers.update(s.HEADERS)
ROTATE = 200

with open(ckpt, "a", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
    if os.path.getsize(ckpt) == 0:
        w.writeheader()
    for i, (_, row) in enumerate(todo.iterrows(), 1):
        try:
            contact = s.fetch_contact(sess, row["ceref"], role)
        except Exception as e:
            log.warning(f"{row['ceref']}: {e}")
            contact = {}
        w.writerow({**row.to_dict(), **contact})
        f.flush()
        if i % 200 == 0:
            log.info(f"progress {i}/{len(todo)}")
        if i % ROTATE == 0:
            sess.close()
            sess = requests.Session()
            sess.headers.update(s.HEADERS)
        s.time.sleep(s.DETAIL_DELAY)

log.info(f"SHARD {idx} DONE")
