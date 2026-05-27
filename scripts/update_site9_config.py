"""Site 9 crawl_config 업데이트"""
import sys
import json
sys.path.insert(0, "D:\\crawling")
from core.db import CrawlDB

db = CrawlDB()
site = db.get_site(9)
cfg = json.loads(site["crawl_config"])

print("Before:", json.dumps(cfg, ensure_ascii=False))

# 고정 날짜 제거, date_range_days로 자동 계산
for key in ["max_posts", "date_from", "date_to"]:
    cfg.pop(key, None)
cfg["date_range_days"] = 3

new_cfg = json.dumps(cfg, ensure_ascii=False)
db.conn.execute(
    "UPDATE crawl_sites SET crawl_config=?, updated_at=datetime('now') WHERE id=?",
    (new_cfg, 9),
)
db.conn.commit()

s2 = db.get_site(9)
print("After:", s2["crawl_config"])
print("Done!")
