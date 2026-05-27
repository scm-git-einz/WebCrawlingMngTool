"""모든 사이트의 현재 DB 상태 확인"""
import sys
import json
sys.path.insert(0, "D:\\crawling")
from core.db import CrawlDB

db = CrawlDB()
sites = db.get_active_sites()

for site in sites:
    print(f"\n{'='*60}")
    print(f"  site_id={site['id']}: {site['site_name']}")
    print(f"  URL: {site['site_url']}")
    print(f"  platform_id: {site.get('platform_id', 'None')}")

    if site.get('platform_id'):
        platform = db.get_platform(site['platform_id'])
        if platform:
            print(f"  Platform: {platform['display_name']} (framework: {platform.get('framework', 'N/A')})")
            tmpls = db.get_templates_for_platform(platform['id'])
            print(f"  Templates: {len(tmpls)}")
            for t in tmpls:
                cfg_str = json.dumps(t["config"], ensure_ascii=False)
                print(f"    target={t['target']}, strategy={t['strategy']}")
                print(f"      config: {cfg_str[:200]}")
        else:
            print(f"  Platform: NOT FOUND (id={site['platform_id']})")
    else:
        print("  Platform: None assigned")

print(f"\n{'='*60}")
print(f"Total active sites: {len(sites)}")
