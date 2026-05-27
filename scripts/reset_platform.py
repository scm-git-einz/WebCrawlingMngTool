"""Reset a platform by ID for re-analysis"""
import sys
sys.path.insert(0, ".")
from core.db import CrawlDB

platform_id = int(sys.argv[1])
site_id = int(sys.argv[2]) if len(sys.argv) > 2 else None

db = CrawlDB()
db.conn.execute(f"DELETE FROM extraction_templates WHERE platform_id={platform_id}")
db.conn.execute(f"DELETE FROM platforms WHERE id={platform_id}")
if site_id:
    db.conn.execute(f"UPDATE crawl_sites SET platform_id=NULL WHERE id={site_id}")
else:
    db.conn.execute(f"UPDATE crawl_sites SET platform_id=NULL WHERE platform_id={platform_id}")
db.conn.commit()

print(f"platform_id={platform_id} deleted")

sites = db.conn.execute("SELECT id, site_name, platform_id FROM crawl_sites").fetchall()
for s in sites:
    print(f"  site_id={s[0]} name={s[1]} platform_id={s[2]}")
db.close()
