"""네이버 스마트스토어 템플릿 확인"""
import sys
import json
sys.path.insert(0, "D:\\crawling")
from core.db import CrawlDB

db = CrawlDB()
site = db.get_site(1)
print(f"Site: {site['site_url']}, platform_id: {site['platform_id']}")

tmpls = db.get_templates_for_platform(site["platform_id"])
print(f"Templates: {len(tmpls)}")
for t in tmpls:
    print(f"\n  target={t['target']}, strategy={t['strategy']}")
    cfg_str = json.dumps(t["config"], ensure_ascii=False)
    print(f"    config: {cfg_str[:300]}")
