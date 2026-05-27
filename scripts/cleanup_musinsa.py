"""Musinsa 플랫폼 정리"""
import sys
sys.path.insert(0, "D:\\crawling")
from core.db import CrawlDB

db = CrawlDB()
site = db.get_site(4)
pid = site.get('platform_id')
if pid:
    db.delete_templates_for_platform(pid)
    cur = db.conn.cursor()
    cur.execute("UPDATE crawl_sites SET platform_id = NULL WHERE id = 4")
    db.conn.commit()
    print(f"Cleaned platform {pid}")
else:
    print("Already clean")
db.close()
