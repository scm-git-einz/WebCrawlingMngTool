"""KREAM platform 26 정리"""
import sys
sys.path.insert(0, "D:\\crawling")
from core.db import CrawlDB

db = CrawlDB()
cur = db.conn.cursor()
cur.execute("DELETE FROM extraction_templates WHERE platform_id = 26")
cur.execute("DELETE FROM platforms WHERE id = 26")
cur.execute("UPDATE crawl_sites SET platform_id = NULL WHERE id = 7")
db.conn.commit()
print("Done")
