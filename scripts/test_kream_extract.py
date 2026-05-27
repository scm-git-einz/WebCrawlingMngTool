"""KREAM 상품 추출 테스트 - 엔진과 동일 조건"""
import sys
import json
sys.path.insert(0, "D:\\crawling")

from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from core.strategies import get_strategy
from core.browser import DEFAULT_BROWSER_CONFIG

url = "https://kream.co.kr"

with sync_playwright() as pw:
    # 엔진과 동일하게 브라우저 설정
    browser = pw.chromium.launch(
        headless=True,
        args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
    )
    ctx = browser.new_context(
        user_agent=DEFAULT_BROWSER_CONFIG["user_agent"],
        viewport=DEFAULT_BROWSER_CONFIG["viewport"],
        extra_http_headers=DEFAULT_BROWSER_CONFIG["headers"],
        locale="ko-KR",
        timezone_id="Asia/Seoul",
    )
    page = ctx.new_page()
    Stealth().apply_stealth_sync(page)

    # 스토어 크롤링과 동일: domcontentloaded + 5초 대기
    resp = page.goto(url, wait_until="domcontentloaded")
    print(f"Status: {resp.status}")
    page.wait_for_timeout(5000)

    # .product_card 요소 수 확인
    count = page.evaluate("document.querySelectorAll('.product_card').length")
    print(f".product_card 요소: {count}개")

    # 스크롤 없이 추출 시도
    dom_config = {
        "container": "body",
        "item_selector": ".product_card",
        "fields": {
            "product_name": {"selector": ":self", "attr": "textContent"},
            "product_url": {"selector": ":self", "attr": "href"},
            "image_url": {"selector": "img", "attr": "src"},
            "selling_price": {"selector": "*", "attr": "textContent", "regex": r"[\d,]+"},
        },
    }

    strategy = get_strategy("dom")
    raw = strategy.extract(page, dom_config)
    items = raw.get("items", []) if isinstance(raw, dict) else []
    print(f"추출된 상품 (스크롤 전): {len(items)}개")
    if items:
        print(f"  첫 상품: {json.dumps(items[0], ensure_ascii=False)[:200]}")

    # 스크롤 후 재시도
    for _ in range(5):
        page.evaluate("window.scrollBy(0, window.innerHeight)")
        page.wait_for_timeout(2000)

    count2 = page.evaluate("document.querySelectorAll('.product_card').length")
    print(f"\n스크롤 후 .product_card 요소: {count2}개")

    raw2 = strategy.extract(page, dom_config)
    items2 = raw2.get("items", []) if isinstance(raw2, dict) else []
    print(f"추출된 상품 (스크롤 후): {len(items2)}개")
    if items2:
        for i, item in enumerate(items2[:3]):
            print(f"  [{i+1}] {json.dumps(item, ensure_ascii=False)[:200]}")

    browser.close()
    print("\n완료")
