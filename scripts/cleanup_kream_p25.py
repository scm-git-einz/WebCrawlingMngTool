"""KREAM platform 25 정리"""
import sys
sys.path.insert(0, "D:\\crawling")
from core.db import CrawlDB

db = CrawlDB()
cur = db.conn.cursor()

# platform 25 삭제
cur.execute("DELETE FROM extraction_templates WHERE platform_id = 25")
cur.execute("DELETE FROM platforms WHERE id = 25")
cur.execute("UPDATE crawl_sites SET platform_id = NULL WHERE id = 7")
db.conn.commit()

site = db.get_site(7)
print(f"Site 7: {site}")
print("Cleanup done")
