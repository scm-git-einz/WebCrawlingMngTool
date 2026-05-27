"""Musinsa 설정 확인"""
import sys
import json
sys.path.insert(0, "D:\\crawling")
from core.db import CrawlDB

db = CrawlDB()
site = db.get_site(4)
print("Site URL:", site["site_url"])
print("Site Name:", site["site_name"])
pid = site.get("platform_id")
if pid:
    p = db.get_platform(pid)
    print("Platform:", p.get("name"))
    print("Browser:", json.dumps(p.get("browser"), indent=2, ensure_ascii=False))
    templates = db.get_templates_for_platform(pid)
    for t in templates:
        print("---")
        print("Target:", t["target"], "/ Strategy:", t["strategy"])
        print("Config:", json.dumps(t["config"], indent=2, ensure_ascii=False))
db.close()
