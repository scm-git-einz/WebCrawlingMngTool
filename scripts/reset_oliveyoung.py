"""Reset oliveyoung platform data for re-analysis"""
from core.db import CrawlDB

db = CrawlDB()

# platform_id=2 (www_oliveyoung_co_kr) 의 템플릿 삭제
db.conn.execute("DELETE FROM extraction_templates WHERE platform_id=2")
# 플랫폼 삭제
db.conn.execute("DELETE FROM platforms WHERE id=2")
# site 의 platform_id 초기화
db.conn.execute("UPDATE crawl_sites SET platform_id=NULL WHERE id=3")
db.conn.commit()

print("oliveyoung platform data deleted")

# 확인
sites = db.conn.execute("SELECT id, site_url, platform_id FROM crawl_sites").fetchall()
for s in sites:
    print(f"  site_id={s[0]} url={s[1][:60]} platform_id={s[2]}")

platforms = db.conn.execute("SELECT id, name FROM platforms").fetchall()
for p in platforms:
    print(f"  platform_id={p[0]} name={p[1]}")
