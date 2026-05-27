"""W Concept DOM 추출 직접 테스트"""
import sys
import json
sys.path.insert(0, "D:\\crawling")

from core.browser import BrowserManager
from core.db import CrawlDB
from core.strategies import get_strategy

db = CrawlDB()
site = db.get_site(6)
platform = db.get_platform(site["platform_id"])

# 브라우저 설정 확인
browser_config = platform.get("browser", {})
print(f"[test] Browser config: {json.dumps(browser_config, ensure_ascii=False)[:500]}")
print(f"[test] Allowed domains: {browser_config.get('allowed_domains', [])}")

# 1) 플랫폼 브라우저 설정으로 시작
bm = BrowserManager()
page = bm.create(browser_config)

url = site["site_url"]
print(f"\n[test] Loading: {url}")
resp = page.goto(url, wait_until="networkidle", timeout=60000)
print(f"[test] Status: {resp.status if resp else 'None'}")
print(f"[test] Final URL: {page.url}")

page.wait_for_timeout(5000)

# 스크롤
for i in range(3):
    page.evaluate("window.scrollBy(0, window.innerHeight)")
    page.wait_for_timeout(1000)

# 2) .product-item 확인
count = page.evaluate("() => document.querySelectorAll('.product-item').length")
print(f"\n[test] .product-item count: {count}")

# 3) DOM 템플릿으로 추출 테스트
tmpls = db.get_templates_for_platform(platform["id"])
dom_tmpl = None
for t in tmpls:
    if t["target"] == "product_list_dom":
        dom_tmpl = t
        break

if dom_tmpl:
    print(f"\n[test] Testing DOM template: {json.dumps(dom_tmpl['config'], ensure_ascii=False)[:300]}")
    strategy = get_strategy("dom")
    result = strategy.extract(page, dom_tmpl["config"])
    if result:
        items = result.get("items", []) if isinstance(result, dict) else result
        print(f"[test] Extracted items: {len(items) if isinstance(items, list) else 'not list'}")
        if items and len(items) > 0:
            for i, item in enumerate(items[:3]):
                try:
                    print(f"  Item {i+1}: {json.dumps(item, ensure_ascii=False)[:200]}")
                except:
                    print(f"  Item {i+1}: (encoding)")
    else:
        print("[test] Result is None/empty!")
else:
    print("[test] No product_list_dom template found!")

# 4) API 템플릿도 테스트
api_tmpl = None
for t in tmpls:
    if t["target"] == "product_list":
        api_tmpl = t
        break

if api_tmpl:
    print(f"\n[test] Testing API template...")
    api_strategy = get_strategy("api")
    result = api_strategy.extract(page, api_tmpl["config"])
    if result:
        items = result.get("items", []) if isinstance(result, dict) else result
        print(f"[test] API extracted items: {len(items) if isinstance(items, list) else type(result)}")
        if items and len(items) > 0:
            for i, item in enumerate(items[:3]):
                try:
                    print(f"  Item {i+1}: {json.dumps(item, ensure_ascii=False)[:200]}")
                except:
                    print(f"  Item {i+1}: (encoding)")
    else:
        print("[test] API result is None!")

bm.close()
db.close()
print("\n[test] Done")
