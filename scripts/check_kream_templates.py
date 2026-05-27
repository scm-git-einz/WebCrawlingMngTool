"""KREAM 현재 템플릿 확인"""
import sys
import json
sys.path.insert(0, "D:\\crawling")
from core.db import CrawlDB

db = CrawlDB()
site = db.get_site(7)
print(f"Site: {site}")

if site and site.get("platform_id"):
    tmpls = db.get_templates_for_platform(site["platform_id"])
    print(f"\nTemplates: {len(tmpls)}")
    for t in tmpls:
        print(f"\n--- {t['target']} ({t['strategy']}) ---")
        print(json.dumps(t['config'], indent=2, ensure_ascii=False))
