"""W Concept DOM 추출 진단"""
import sys
import json
import time
sys.path.insert(0, "D:\\crawling")

from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from core.strategies import get_strategy

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

    # 스크롤
    for _ in range(3):
        page.evaluate("window.scrollBy(0, window.innerHeight)")
        time.sleep(1)

    # 1) 직접 querySelectorAll로 확인
    el_check = page.evaluate("""() => {
        var tests = [
            '.sc-6eatg0-0',
            'span.title',
            'span.price',
        ];
        var results = {};
        for (var i = 0; i < tests.length; i++) {
            try {
                var els = document.querySelectorAll(tests[i]);
                results[tests[i]] = els.length;
            } catch(e) {
                results[tests[i]] = 'error: ' + e.message;
            }
        }
        return results;
    }""")
    print("=== 요소 개수 ===")
    for k, v in el_check.items():
        print(f"  {k}: {v}")

    # 2) 모든 반복 클래스 찾기
    repeat_classes = page.evaluate("""() => {
        var counts = {};
        var all = document.querySelectorAll('[class]');
        for (var i = 0; i < all.length; i++) {
            var cls = all[i].className;
            if (typeof cls !== 'string') continue;
            var classes = cls.trim().split(/\\s+/);
            for (var c = 0; c < classes.length; c++) {
                if (classes[c].startsWith('sc-')) {
                    counts[classes[c]] = (counts[classes[c]] || 0) + 1;
                }
            }
        }
        var result = [];
        for (var k in counts) {
            if (counts[k] >= 10) result.push({cls: k, count: counts[k]});
        }
        result.sort(function(a,b) { return b.count - a.count; });
        return result.slice(0, 15);
    }""")
    print("\n=== sc-* 클래스 (10+개) ===")
    for r in repeat_classes:
        print(f"  .{r['cls']}: {r['count']}개")

    # 3) DOM 전략으로 추출 테스트
    dom_config = {
        "container": "body",
        "item_selector": ".sc-6eatg0-0",
        "fields": {
            "product_name": {"selector": "span.title", "attr": "textContent"},
            "selling_price": {"selector": "span.price", "attr": "textContent", "regex": r"[\d,]+"},
            "product_url": {"selector": "a[href]", "attr": "href"},
            "image_url": {"selector": "img", "attr": "src"},
        },
    }

    dom_strategy = get_strategy("dom")
    raw = dom_strategy.extract(page, dom_config)
    if raw:
        items = raw if isinstance(raw, list) else raw.get("items", [])
        print(f"\n=== DOM 추출 결과: {len(items)}개 ===")
        for item in items[:3]:
            print(json.dumps(item, ensure_ascii=False)[:200])
    else:
        print(f"\n=== DOM 추출 실패: raw={raw}")

    browser.close()
    print("\n진단 완료")
