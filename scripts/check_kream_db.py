"""KREAM DB 상태 확인 및 재분석 준비"""
import sys
sys.path.insert(0, "D:\\crawling")
from core.db import CrawlDB

db = CrawlDB()
site = db.get_site(7)
print(f"KREAM site: {site}")

if site and site.get("platform_id"):
    pid = site["platform_id"]
    print(f"Platform ID: {pid}")
    tmpls = db.get_templates_for_platform(pid)
    print(f"Templates: {len(tmpls)}")
    for t in tmpls:
        print(f"  target={t['target']}, strategy={t['strategy']}")

    # 재분석을 위해 platform_id 해제
    db.update_site_platform(7, None)
    print("\nplatform_id 해제 완료 → 재분석 가능")
else:
    print("platform_id 없음 → 바로 분석 가능")
