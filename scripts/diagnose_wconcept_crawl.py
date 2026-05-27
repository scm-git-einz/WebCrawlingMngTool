"""W Concept: 크롤링 세션 시뮬레이션 - DOM 추출 테스트"""
import sys
import json
import time
sys.path.insert(0, "D:\\crawling")

from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from core.strategies import get_strategy

url = "https://www.wconcept.co.kr"

with sync_playwright() as pw:
    # 엔진과 동일 조건: headless
    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context(
        viewport={"width": 1920, "height": 1080},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    )
    page = ctx.new_page()
    Stealth().apply_stealth_sync(page)

    # 1단계: store 추출과 동일하게 네비게이션
    print("[1] domcontentloaded + 3초 대기")
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(3000)

    count1 = page.evaluate("document.querySelectorAll('.product-item').length")
    print(f"  .product-item: {count1}개")

    # 2단계: networkidle 로 다시 네비게이션
    print("[2] networkidle + 3초 대기 + 스크롤")
    page.goto(url, wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(3000)

    for i in range(3):
        page.evaluate("window.scrollBy(0, window.innerHeight)")
        page.wait_for_timeout(1000)

    count2 = page.evaluate("document.querySelectorAll('.product-item').length")
    print(f"  .product-item: {count2}개")

    # 3단계: 현재 페이지 URL 확인
    print(f"  현재 URL: {page.url}")

    # 4단계: span.title, span.price 확인
    other = page.evaluate("""() => {
        return {
            'span.title': document.querySelectorAll('span.title').length,
            'span.price': document.querySelectorAll('span.price').length,
            '.prdc-price': document.querySelectorAll('.prdc-price').length,
            '.prdc-title': document.querySelectorAll('.prdc-title').length,
            '.final-price': document.querySelectorAll('.final-price').length,
        }
    }""")
    print(f"  요소 개수: {other}")

    # 5단계: DOM 전략 테스트
    dom_config = {
        "container": "body",
        "item_selector": ".product-item",
        "fields": {
            "product_name": {"selector": "span.title", "attr": "textContent"},
            "selling_price": {"selector": "span.price", "attr": "textContent", "regex": r"[\d,]+"},
            "image_url": {"selector": "img", "attr": "src"},
        },
    }

    dom_strategy = get_strategy("dom")
    raw = dom_strategy.extract(page, dom_config)
    items = []
    if raw:
        items = raw.get("items", []) if isinstance(raw, dict) else raw
    print(f"\n[결과] DOM 추출: {len(items)}개")
    for item in items[:3]:
        print(f"  {json.dumps(item, ensure_ascii=False)[:150]}")

    # 6단계: 직접 JS로 .product-item 내부 확인
    if count2 > 0:
        sample = page.evaluate("""() => {
            var el = document.querySelector('.product-item');
            if (!el) return null;
            return {
                innerHTML: el.innerHTML.substring(0, 500),
                outerHTML: el.outerHTML.substring(0, 200),
            }
        }""")
        if sample:
            print(f"\n[샘플] .product-item HTML:")
            print(f"  outer: {sample['outerHTML']}")

    browser.close()
    print("\n진단 완료")
