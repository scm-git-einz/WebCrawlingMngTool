"""Site 9 crawl_config에 collect_ocr 추가"""
import sys, json
sys.path.insert(0, "D:\\crawling")
from core.db import CrawlDB

db = CrawlDB()
site = db.get_site(9)
cfg = json.loads(site["crawl_config"])

print("Before:", json.dumps(cfg, ensure_ascii=False))

cfg["collect_ocr"] = True

new_cfg = json.dumps(cfg, ensure_ascii=False)
db.conn.execute(
    "UPDATE crawl_sites SET crawl_config=?, updated_at=datetime('now') WHERE id=?",
    (new_cfg, 9),
)
db.conn.commit()

s2 = db.get_site(9)
print("After:", s2["crawl_config"])
print("Done!")
