"""W Concept 플랫폼 완전 재설정"""
import sys
sys.path.insert(0, "D:\\crawling")
from core.db import CrawlDB

db = CrawlDB()

# 현재 platform_id 확인
site = db.get_site(6)
pid = site.get('platform_id')
print(f"Current platform_id: {pid}")

if pid:
    # 템플릿 삭제
    db.delete_templates_for_platform(pid)
    print(f"Templates for platform {pid} deleted")
    # 사이트 platform_id 해제
    cur = db.conn.cursor()
    cur.execute("UPDATE crawl_sites SET platform_id = NULL WHERE id = 6")
    db.conn.commit()
    print("Site platform_id set to NULL")

db.close()
print("Done")
