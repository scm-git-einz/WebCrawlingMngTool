"""29CM 사이트 진단 스크립트: DOM 및 네트워크 분석"""
import sys
import json
import time
sys.path.insert(0, "D:\\crawling")

from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from core.network_interceptor import NetworkInterceptor

url = "https://www.29cm.co.kr"

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
    time.sleep(3)

    # 스크롤해서 더 많은 콘텐츠 로딩
    for _ in range(3):
        page.evaluate("window.scrollBy(0, window.innerHeight)")
        time.sleep(1)

    # 1) 네트워크 요청 분석
    candidates = interceptor.get_api_candidates()
    print(f"\n=== 네트워크 API 후보: {len(candidates)}개 ===")
    for c in candidates:
        print(f"  target={c['target_type']} score={c['score']} "
              f"method={c.get('method','GET')} path={c['path']}")
        if c.get('request_body'):
            print(f"    body_keys={list(c['request_body'].keys()) if isinstance(c['request_body'], dict) else 'non-dict'}")
        analysis = c.get('analysis', {})
        if analysis.get('field_mapping'):
            print(f"    fields={list(analysis['field_mapping'].keys())}")
        if analysis.get('list_path'):
            print(f"    list_path={analysis['list_path']}")

    # 2) 가격 요소 분석
    price_info = page.evaluate("""() => {
        var priceEls = [];
        var allEls = document.querySelectorAll('*');
        for (var i = 0; i < allEls.length; i++) {
            var el = allEls[i];
            var text = (el.textContent || '').trim();
            if (/\\d{1,3}(,\\d{3})+/.test(text) && el.children.length < 5) {
                priceEls.push({
                    tag: el.tagName.toLowerCase(),
                    cls: (typeof el.className === 'string' ? el.className : '').substring(0, 80),
                    text: text.substring(0, 50),
                    parentCls: el.parentElement ? (typeof el.parentElement.className === 'string' ? el.parentElement.className : '').substring(0, 80) : ''
                });
            }
        }
        return {count: priceEls.length, samples: priceEls.slice(0, 10)};
    }""")
    print(f"\n=== 가격 요소: {price_info['count']}개 ===")
    for s in price_info['samples']:
        print(f"  <{s['tag']} class='{s['cls']}'> text='{s['text']}'")
        print(f"    parent class='{s['parentCls']}'")

    # 3) 상품 카드 후보 분석 (더 넓은 조건)
    cards_info = page.evaluate("""() => {
        var priceEls = [];
        var allEls = document.querySelectorAll('*');
        for (var i = 0; i < allEls.length; i++) {
            var el = allEls[i];
            var text = (el.textContent || '').trim();
            if (/\\d{1,3}(,\\d{3})+/.test(text) && el.children.length < 5) {
                priceEls.push(el);
            }
        }

        var parentClasses = {};
        for (var p = 0; p < priceEls.length; p++) {
            var parent = priceEls[p].parentElement;
            for (var depth = 0; depth < 8 && parent; depth++) {
                var cls = parent.className;
                if (typeof cls === 'string' && cls.trim()) {
                    var classes = cls.trim().split(/\\s+/);
                    for (var ci = 0; ci < classes.length; ci++) {
                        var clsName = classes[ci];
                        var key = parent.tagName.toLowerCase() + '.' + clsName;
                        if (!parentClasses[key]) parentClasses[key] = {count: 0, tag: parent.tagName};
                        parentClasses[key].count++;
                    }
                }
                parent = parent.parentElement;
            }
        }

        var results = [];
        for (var ck in parentClasses) {
            var info = parentClasses[ck];
            if (info.count >= 3) {
                var dotIdx = ck.indexOf('.');
                var clsName = ck.substring(dotIdx + 1);
                var sampleEls;
                try { sampleEls = document.querySelectorAll('.' + CSS.escape(clsName)); }
                catch(e) { continue; }
                var totalEls = sampleEls.length;
                var ratio = totalEls / info.count;

                var hasImg = false, hasLink = false;
                if (sampleEls[0]) {
                    hasImg = sampleEls[0].querySelectorAll('img').length > 0;
                    hasLink = sampleEls[0].querySelectorAll('a[href]').length > 0;
                }

                results.push({
                    key: ck,
                    cls: clsName,
                    count: info.count,
                    totalEls: totalEls,
                    ratio: Math.round(ratio * 100) / 100,
                    hasImg: hasImg,
                    hasLink: hasLink,
                    cssUnsafe: /[^a-zA-Z0-9_-]/.test(clsName)
                });
            }
        }
        results.sort(function(a, b) { return b.count - a.count; });
        return results.slice(0, 20);
    }""")
    print(f"\n=== 상품 카드 후보 (모든 클래스) ===")
    for c in cards_info:
        flag = ""
        if c['cssUnsafe']: flag += " [CSS-UNSAFE]"
        if not c['hasImg'] and not c['hasLink']: flag += " [NO-IMG/LINK]"
        if c['ratio'] < 0.15: flag += " [CONTAINER]"
        if c['totalEls'] < 3: flag += " [TOO-FEW]"
        print(f"  .{c['cls']}: count={c['count']} total={c['totalEls']} "
              f"ratio={c['ratio']} img={c['hasImg']} link={c['hasLink']}{flag}")

    # 4) product/item 링크 탐색
    product_links = page.evaluate("""() => {
        var links = document.querySelectorAll('a[href*="product"], a[href*="goods"], a[href*="item"]');
        var results = [];
        for (var i = 0; i < Math.min(links.length, 10); i++) {
            results.push({
                href: links[i].getAttribute('href'),
                text: (links[i].textContent || '').trim().substring(0, 60),
                parentCls: (links[i].parentElement && typeof links[i].parentElement.className === 'string') ? links[i].parentElement.className.substring(0, 80) : ''
            });
        }
        return {count: links.length, samples: results};
    }""")
    print(f"\n=== 상품 링크: {product_links['count']}개 ===")
    for l in product_links['samples']:
        print(f"  href={l['href']}")
        print(f"    text={l['text']}")
        print(f"    parentCls={l['parentCls']}")

    browser.close()
    print("\n진단 완료")
