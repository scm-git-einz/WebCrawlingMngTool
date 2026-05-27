"""카드 필드 스캐너 직접 테스트"""
import sys
import json
import time
sys.path.insert(0, "D:\\crawling")

from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from core.rule_analyzer import _JS_DOM_CARD_FIELDS_SCAN

url = "https://www.wconcept.co.kr"

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context(
        viewport={"width": 1920, "height": 1080},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    )
    page = ctx.new_page()
    Stealth().apply_stealth_sync(page)

    page.goto(url, wait_until="networkidle", timeout=60000)
    time.sleep(3)
    for _ in range(3):
        page.evaluate("window.scrollBy(0, window.innerHeight)")
        time.sleep(1)

    # 카드 필드 스캐너 실행
    try:
        result = page.evaluate(_JS_DOM_CARD_FIELDS_SCAN, "product-item")
        print("=== 카드 필드 스캐너 결과 ===")
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"스캐너 오류: {e}")

    # 수동 검증
    manual_check = page.evaluate("""() => {
        var cards = document.querySelectorAll('.product-item');
        var selectors = ['span.price', 'span.prdc-price', 'span.final-price', 'span.title', 'span.prdc-title'];
        var results = {};
        for (var s = 0; s < selectors.length; s++) {
            var sel = selectors[s];
            var hits = 0;
            for (var i = 0; i < Math.min(cards.length, 10); i++) {
                if (cards[i].querySelector(sel)) hits++;
            }
            results[sel] = hits + '/' + Math.min(cards.length, 10);
        }
        results.totalCards = cards.length;
        return results;
    }""")
    print("\n=== 수동 셀렉터 검증 (처음 10개 카드) ===")
    for k, v in manual_check.items():
        print(f"  {k}: {v}")

    browser.close()
