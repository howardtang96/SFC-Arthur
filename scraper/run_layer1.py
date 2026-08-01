"""Stage runner: Layer 1 only (Loop A + Loop B). Delays untouched."""
import requests, logging
from datetime import datetime
import sfc_scraper as s

sess = requests.Session()
sess.headers.update(s.HEADERS)
ents = s.collect_all_entities(sess)
out = "../output/sfc_list_raw.csv"
ents.to_csv(out, index=False)
logging.getLogger("sfc_scraper").info(f"LAYER1 DONE: {len(ents)} unique -> {out}")
