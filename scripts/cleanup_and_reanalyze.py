"""W Concept(site_id=6)과 Musinsa(site_id=4) 플랫폼 정리 후 재분석"""
import sys
sys.path.insert(0, "D:\\crawling")
from core.db import CrawlDB

db = CrawlDB()

# 1) W Concept 정리 (platform_id=23)
print("=== W Concept (site_id=6) 정리 ===")
db.delete_templates_for_platform(23)
print("  templates 삭제 완료")
cur = db.conn.cursor()
cur.execute("UPDATE crawl_sites SET platform_id = NULL WHERE id = 6")
db.conn.commit()
print("  platform_id = NULL 설정 완료")

# 2) Musinsa 정리 (platform_id=8)
print("\n=== Musinsa (site_id=4) 정리 ===")
db.delete_templates_for_platform(8)
print("  templates 삭제 완료")
cur.execute("UPDATE crawl_sites SET platform_id = NULL WHERE id = 4")
db.conn.commit()
print("  platform_id = NULL 설정 완료")

# 확인
for site_id in [4, 6]:
    site = db.get_site(site_id)
    print(f"\n  site_id={site_id}: platform_id={site.get('platform_id')}")

db.close()
print("\n정리 완료. 엔진 실행으로 재분석이 트리거됩니다.")
