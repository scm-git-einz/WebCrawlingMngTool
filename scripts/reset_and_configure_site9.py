"""Site 9 기존 데이터 삭제 + crawl_config 재설정"""
import sys, json
sys.path.insert(0, "D:\\crawling")
from core.db import CrawlDB

db = CrawlDB()
cur = db.conn.cursor()

# 1. 기존 crawl_results 삭제
cur.execute("DELETE FROM crawl_results WHERE site_id=9")
deleted = cur.rowcount
print(f"Deleted {deleted} crawl_results for site 9")

# 2. crawl_config 업데이트: 오늘 날짜만 수집, OCR 활성화
cfg = {
    "collect_body": True,
    "collect_links": True,
    "collect_images": True,
    "date_from": "2026-05-25",
    "date_to": "2026-05-25",
    "collect_ocr": True,
}
new_cfg = json.dumps(cfg, ensure_ascii=False)
cur.execute(
    "UPDATE crawl_sites SET crawl_config=?, updated_at=datetime('now') WHERE id=?",
    (new_cfg, 9),
)
db.conn.commit()

# 3. 확인
site = db.get_site(9)
print(f"Updated config: {site['crawl_config']}")
cur.execute("SELECT COUNT(*) FROM crawl_results WHERE site_id=9")
print(f"Remaining results: {cur.fetchone()[0]}")
print("Done!")
