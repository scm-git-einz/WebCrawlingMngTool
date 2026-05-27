"""W Concept 새 템플릿 확인"""
import sys
import json
sys.path.insert(0, "D:\\crawling")
from core.db import CrawlDB

db = CrawlDB()
site = db.get_site(6)
print(f"Site: {site['site_name']}, platform_id: {site.get('platform_id')}")

if site.get('platform_id'):
    tmpls = db.get_templates_for_platform(site["platform_id"])
    print(f"Templates: {len(tmpls)}")
    for t in tmpls:
        print(f"\n  target={t['target']}, strategy={t['strategy']}")
        cfg_str = json.dumps(t["config"], ensure_ascii=False, indent=2)
        print(f"    config: {cfg_str}")
else:
    print("No platform assigned!")

db.close()
