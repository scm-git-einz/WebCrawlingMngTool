"""W Concept 플랫폼 브라우저 설정 확인 + DOM 렌더링 테스트"""
import sys
import json
sys.path.insert(0, "D:\\crawling")
from core.db import CrawlDB
from core.browser import BrowserManager

db = CrawlDB()
site = db.get_site(6)
pid = site.get("platform_id")
print(f"Platform ID: {pid}")

if pid:
    platform = db.get_platform(pid)
    browser_config = platform.get("browser", {})
    allowed = browser_config.get("allowed_domains", [])
    print(f"Allowed domains ({len(allowed)}):")
    for d in allowed:
        print(f"  {d}")

    # 실제 렌더링 테스트
    bm = BrowserManager()
    page = bm.create(browser_config)

    url = "https://www.wconcept.co.kr/Women"
    resp = page.goto(url, wait_until="domcontentloaded", timeout=60000)
    print(f"\nStatus: {resp.status}, URL: {page.url}")
    page.wait_for_timeout(8000)

    # 스크롤
    for i in range(3):
        page.evaluate("window.scrollBy(0, window.innerHeight)")
        page.wait_for_timeout(1000)

    count = page.evaluate("() => document.querySelectorAll('.product-item').length")
    body_len = page.evaluate("() => (document.body.innerText || '').length")
    all_scripts = page.evaluate("() => document.querySelectorAll('script[src]').length")

    print(f"\n.product-item: {count}")
    print(f"Body text length: {body_len}")
    print(f"Script tags with src: {all_scripts}")

    # 차단된 요청 확인 (body가 빈 경우)
    all_els = page.evaluate("() => document.querySelectorAll('*').length")
    print(f"Total DOM elements: {all_els}")

    bm.close()
else:
    print("No platform!")

db.close()
