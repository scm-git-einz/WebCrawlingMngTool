"""W Concept: 안정적 셀렉터 탐색"""
import sys
import json
import time
sys.path.insert(0, "D:\\crawling")

from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

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

    # 상품 링크와 구조 분석
    products = page.evaluate(r"""() => {
        // 상품 링크 찾기
        var productLinks = document.querySelectorAll('a[href*="/Product/"], a[href*="/product/"]');
        var results = {
            productLinksCount: productLinks.length,
            samples: []
        };

        for (var i = 0; i < Math.min(productLinks.length, 5); i++) {
            var link = productLinks[i];
            var sample = {
                href: link.getAttribute('href'),
                text: (link.textContent || '').trim().substring(0, 100),
                tag: link.tagName,
                childTags: [],
                parentInfo: [],
            };

            // 자식 요소 정보
            var children = link.querySelectorAll('*');
            for (var c = 0; c < Math.min(children.length, 10); c++) {
                var child = children[c];
                var cls = typeof child.className === 'string' ? child.className : '';
                // sc- 제외한 클래스
                var stableCls = cls.split(/\s+/).filter(function(c) { return c && !c.startsWith('sc-'); });
                sample.childTags.push({
                    tag: child.tagName.toLowerCase(),
                    stableCls: stableCls.join(' '),
                    text: (child.textContent || '').trim().substring(0, 50),
                });
            }

            // 부모 계층 정보 (6단계)
            var parent = link.parentElement;
            for (var d = 0; d < 6 && parent; d++) {
                var pCls = typeof parent.className === 'string' ? parent.className : '';
                var stableParentCls = pCls.split(/\s+/).filter(function(c) { return c && !c.startsWith('sc-'); });
                sample.parentInfo.push({
                    tag: parent.tagName.toLowerCase(),
                    stableCls: stableParentCls.join(' '),
                    childCount: parent.children.length,
                });
                parent = parent.parentElement;
            }

            results.samples.push(sample);
        }

        // data- 속성 가진 요소들
        var dataEls = document.querySelectorAll('[data-product-id], [data-item-id], [data-goods-cd]');
        results.dataProductElements = dataEls.length;

        // aria/role 기반
        var listItems = document.querySelectorAll('[role="listitem"], [role="list"] > *');
        results.listItems = listItems.length;

        // 가격 패턴을 포함하는 안정적 클래스 요소
        var priceEls = document.querySelectorAll('.price, [class*="price"], [class*="Price"]');
        results.priceElements = priceEls.length;
        results.priceSamples = [];
        for (var p = 0; p < Math.min(priceEls.length, 5); p++) {
            var pe = priceEls[p];
            var pcls = typeof pe.className === 'string' ? pe.className : '';
            var stablePCls = pcls.split(/\s+/).filter(function(c) { return c && !c.startsWith('sc-'); });
            results.priceSamples.push({
                tag: pe.tagName.toLowerCase(),
                stableCls: stablePCls.join(' '),
                text: (pe.textContent || '').trim().substring(0, 50),
            });
        }

        // title/name 클래스 요소
        var titleEls = document.querySelectorAll('.title, [class*="title"], .name, [class*="name"]');
        results.titleElements = titleEls.length;

        return results;
    }""")

    print(f"=== 상품 링크: {products['productLinksCount']}개 ===")
    print(f"data-* 상품 요소: {products['dataProductElements']}개")
    print(f"role=listitem: {products['listItems']}개")
    print(f"price 클래스 요소: {products['priceElements']}개")
    print(f"title/name 클래스 요소: {products['titleElements']}개")

    print("\n=== 상품 링크 샘플 ===")
    for s in products.get('samples', []):
        print(f"\n  href: {s['href']}")
        print(f"  text: {s['text'][:80]}")
        print(f"  부모 계층:")
        for p in s['parentInfo']:
            print(f"    <{p['tag']} cls='{p['stableCls']}'> children={p['childCount']}")
        print(f"  자식 요소:")
        for c in s['childTags'][:5]:
            print(f"    <{c['tag']} cls='{c['stableCls']}'> '{c['text'][:40]}'")

    print("\n=== 가격 요소 샘플 ===")
    for p in products.get('priceSamples', []):
        print(f"  <{p['tag']} cls='{p['stableCls']}'> '{p['text']}'")

    browser.close()
    print("\n진단 완료")
