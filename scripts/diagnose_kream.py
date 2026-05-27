"""KREAM 사이트 진단"""
import sys
import json
import time
sys.path.insert(0, "D:\\crawling")

from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from core.network_interceptor import NetworkInterceptor

url = "https://kream.co.kr"

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context(
        viewport={"width": 1920, "height": 1080},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    )
    page = ctx.new_page()
    Stealth().apply_stealth_sync(page)

    interceptor = NetworkInterceptor()
    interceptor.start(page)

    page.goto(url, wait_until="networkidle", timeout=60000)
    time.sleep(5)

    # 스크롤
    for _ in range(5):
        page.evaluate("window.scrollBy(0, window.innerHeight)")
        time.sleep(2)

    interceptor.stop(page)

    # 1) 네트워크 분석
    print(f"=== 캡처된 요청: {len(interceptor.captured)}개 ===")
    candidates = interceptor.get_api_candidates()
    print(f"API 후보: {len(candidates)}개")
    for c in candidates[:5]:
        print(f"  target={c['target_type']} score={c['score']} path={c['path']}")

    # 모든 캡처된 요청 URL 출력
    print(f"\n=== 캡처된 요청 URL (상위 20개) ===")
    for req in interceptor.captured[:20]:
        print(f"  {req.get('method','GET')} {req.get('url','')[:100]}")

    # 2) DOM 분석
    dom_info = page.evaluate(r"""() => {
        // 가격 요소
        var priceEls = [];
        var allEls = document.querySelectorAll('*');
        for (var i = 0; i < allEls.length; i++) {
            var el = allEls[i];
            var text = (el.textContent || '').trim();
            if (/\d{1,3}(,\d{3})+/.test(text) && el.children.length < 5) {
                priceEls.push({
                    tag: el.tagName.toLowerCase(),
                    cls: (typeof el.className === 'string' ? el.className : '').substring(0, 60),
                    text: text.substring(0, 50),
                });
            }
        }

        // 상품 링크
        var productLinks = document.querySelectorAll('a[href*="product"], a[href*="products"]');

        // 클래스 반복 패턴
        var classCounts = {};
        var classEls = document.querySelectorAll('[class]');
        for (var i = 0; i < classEls.length; i++) {
            var cls = classEls[i].className;
            if (typeof cls !== 'string') continue;
            var classes = cls.trim().split(/\s+/);
            for (var c = 0; c < classes.length; c++) {
                if (classes[c].length > 2 && /product|item|card|goods/i.test(classes[c])) {
                    classCounts[classes[c]] = (classCounts[classes[c]] || 0) + 1;
                }
            }
        }

        return {
            priceCount: priceEls.length,
            priceSamples: priceEls.slice(0, 5),
            productLinks: productLinks.length,
            productLinkSamples: Array.from(productLinks).slice(0, 5).map(function(l) {
                return {href: l.getAttribute('href'), text: (l.textContent || '').trim().substring(0, 60)};
            }),
            productClasses: classCounts,
        };
    }""")

    print(f"\n=== DOM 분석 ===")
    print(f"가격 요소: {dom_info['priceCount']}개")
    for s in dom_info['priceSamples']:
        print(f"  <{s['tag']} class='{s['cls']}'> '{s['text']}'")
    print(f"\n상품 링크: {dom_info['productLinks']}개")
    for l in dom_info['productLinkSamples']:
        print(f"  href={l['href']}")
        print(f"    text={l['text']}")
    print(f"\n상품 관련 클래스:")
    for k, v in sorted(dom_info['productClasses'].items(), key=lambda x: -x[1])[:10]:
        print(f"  .{k}: {v}개")

    # 3) Nuxt 상태 확인
    nuxt_info = page.evaluate("""() => {
        if (window.__NUXT__) {
            var keys = Object.keys(window.__NUXT__);
            var result = {hasNuxt: true, keys: keys};
            // data/state 확인
            if (window.__NUXT__.data) {
                result.dataKeys = Object.keys(window.__NUXT__.data).slice(0, 10);
            }
            if (window.__NUXT__.state) {
                result.stateKeys = Object.keys(window.__NUXT__.state).slice(0, 10);
            }
            return result;
        }
        if (window.__pinia) {
            return {hasPinia: true, keys: Object.keys(window.__pinia._s || {}).slice(0, 10)};
        }
        return {hasNuxt: false};
    }""")
    print(f"\n=== Nuxt 상태 ===")
    print(json.dumps(nuxt_info, indent=2, ensure_ascii=False))

    browser.close()
    print("\n진단 완료")
