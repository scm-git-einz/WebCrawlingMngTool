"""KREAM 사이트 URL을 루트로 변경"""
import sys
sys.path.insert(0, "D:\\crawling")
from core.db import CrawlDB

db = CrawlDB()

# 현재 상태 확인
site = db.get_site(7)
print(f"Before: {site}")

# URL 변경 + platform_id 해제
cur = db.conn.cursor()
cur.execute(
    "UPDATE crawl_sites SET site_url = ?, platform_id = NULL, updated_at = datetime('now') WHERE id = 7",
    ("https://kream.co.kr",),
)
db.conn.commit()

site = db.get_site(7)
print(f"After: {site}")
print("Done")
