"""Musinsa 전체 진단 - 리다이렉트된 URL 기반"""
import sys
import json
sys.path.insert(0, "D:\\crawling")
from core.browser import BrowserManager
from core.network_interceptor import NetworkInterceptor

bm = BrowserManager()
interceptor = NetworkInterceptor()
page = bm.create()
interceptor.start(page)

# musinsa.com으로 접속 (www 리다이렉트)
url = "https://www.musinsa.com/main/musinsa/ranking"
print(f"[diag] Loading: {url}")
try:
    resp = page.goto(url, wait_until="domcontentloaded", timeout=30000)
    print(f"[diag] Status: {resp.status if resp else 'None'}")
except Exception as e:
    print(f"[diag] Error with ranking URL: {e}")
    print("[diag] Trying base URL...")
    resp = page.goto("https://musinsa.com", wait_until="domcontentloaded", timeout=30000)
    print(f"[diag] Status: {resp.status if resp else 'None'}")

print(f"[diag] Final URL: {page.url}")
page.wait_for_timeout(8000)

# 스크롤
for i in range(5):
    page.evaluate("window.scrollBy(0, window.innerHeight)")
    page.wait_for_timeout(1500)

interceptor.stop(page)
captured = list(interceptor.captured)

# 1) 프레임워크
framework_info = page.evaluate("""() => {
    var result = {};
    if (window.__NEXT_DATA__) result.nextjs = true;
    if (document.getElementById('__NEXT_DATA__')) result.nextjs_script = true;
    if (window.__NUXT__) result.nuxt = true;
    if (window.__next_f) result.nextjs_rsc = true;
    return result;
}""")
print(f"\n[diag] Framework: {json.dumps(framework_info)}")

# 2) 기존 셀렉터 확인
old_sel = ".UIProductColumn__Wrap-sc-1t5ihy5-0"
old_count = page.evaluate(f"() => document.querySelectorAll('{old_sel}').length")
print(f"\n[diag] Old selector: {old_count} elements")

# 3) 가격 + 상품 요소 탐색
analysis = page.evaluate("""() => {
    var body = document.body.innerText || '';
    var pricePattern = /[0-9,]+원/g;
    var prices = body.match(pricePattern);

    var selectors = [
        '[class*="product"]', '[class*="Product"]',
        '[class*="item"]', '[class*="Item"]',
        '[class*="goods"]', '[class*="Goods"]',
        '[class*="ranking"]', '[class*="Ranking"]',
        '[class*="card"]', '[class*="Card"]',
        'a[href*="/products/"]', 'a[href*="/app/goods/"]',
        'a[href*="/product/"]',
        '[data-item-id]', '[data-product-id]',
        '[data-goods-id]', '[data-goods-no]',
    ];
    var domCounts = {};
    for (var i = 0; i < selectors.length; i++) {
        try {
            var cnt = document.querySelectorAll(selectors[i]).length;
            if (cnt > 0) domCounts[selectors[i]] = cnt;
        } catch(e) {}
    }

    return {
        priceCount: prices ? prices.length : 0,
        samplePrices: prices ? prices.slice(0, 5) : [],
        bodyLen: body.length,
        domCounts: domCounts,
    };
}""")
print(f"\n[diag] Price count: {analysis['priceCount']}")
print(f"[diag] Sample prices: {analysis['samplePrices']}")
print(f"[diag] Body length: {analysis['bodyLen']}")
print(f"\n[diag] DOM counts:")
for sel, cnt in analysis['domCounts'].items():
    print(f"  {sel}: {cnt}")

# 4) 가격 요소 기반 카드 감지
card_detect = page.evaluate("""() => {
    var allEls = document.querySelectorAll('*');
    var priceEls = [];
    for (var i = 0; i < allEls.length; i++) {
        var el = allEls[i];
        if (el.children.length > 0) continue;
        var text = (el.textContent || '').trim();
        if (/^[0-9,]+원$/.test(text)) {
            priceEls.push(el);
        }
    }

    if (priceEls.length === 0) return {priceEls: 0};

    // 부모 클래스 카운팅
    var classCounts = {};
    for (var i = 0; i < priceEls.length; i++) {
        var parent = priceEls[i].parentElement;
        for (var d = 0; d < 6 && parent; d++) {
            var cls = (parent.className || '').toString();
            var classes = cls.split(/\\s+/).filter(function(c) { return c.length > 2; });
            for (var j = 0; j < classes.length; j++) {
                // 해시 클래스 제외
                if (/^[a-z]{2,3}-[a-zA-Z0-9]{6,}$/.test(classes[j])) continue;
                if (classes[j].indexOf('sc-') === 0) continue;
                var key = d + ':' + classes[j];
                classCounts[key] = (classCounts[key] || 0) + 1;
            }
            parent = parent.parentElement;
        }
    }

    var sorted = Object.keys(classCounts).sort(function(a, b) {
        return classCounts[b] - classCounts[a];
    });

    return {
        priceEls: priceEls.length,
        topClasses: sorted.slice(0, 15).map(function(k) {
            return {cls: k, count: classCounts[k]};
        }),
    };
}""")
print(f"\n[diag] Price-based card detection:")
print(f"  Price elements: {card_detect.get('priceEls', 0)}")
for tc in card_detect.get('topClasses', []):
    print(f"  {tc['cls']}: {tc['count']}")

# 5) 상품 카드 샘플 (있다면)
if analysis['domCounts'].get('a[href*="/products/"]', 0) > 0:
    samples = page.evaluate("""() => {
        var links = document.querySelectorAll('a[href*="/products/"]');
        var results = [];
        for (var i = 0; i < Math.min(3, links.length); i++) {
            var el = links[i];
            results.push({
                href: el.getAttribute('href') || '',
                text: (el.textContent || '').trim().substring(0, 100),
                cls: (el.className || '').toString().substring(0, 80),
                parentCls: el.parentElement ? (el.parentElement.className || '').toString().substring(0, 80) : '',
            });
        }
        return results;
    }""")
    print(f"\n[diag] Product link samples:")
    for s in samples:
        try:
            print(f"  href={s['href'][:60]}, cls={s['cls'][:40]}")
            print(f"    text={s['text'][:80]}")
        except:
            print(f"  href={s['href'][:60]}")

# 6) API 요청 분석
print(f"\n[diag] Captured API requests: {len(captured)}")
api_reqs = [r for r in captured if any(kw in r.get('url', '').lower() for kw in ['api', 'ranking', 'product', 'goods'])]
for req in api_reqs[:10]:
    url_short = req.get("url", "")[:120]
    body_len = len(req.get("body", "") or "")
    print(f"  [{req.get('status')}] body={body_len:>6} {url_short}")

bm.close()
print("\n[diag] Done")
