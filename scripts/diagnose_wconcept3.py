"""W Concept 상품 URL 추출 방법 탐색"""
import sys
import json
sys.path.insert(0, "D:\\crawling")
from core.browser import BrowserManager
from core.network_interceptor import NetworkInterceptor

bm = BrowserManager()
interceptor = NetworkInterceptor()
page = bm.create()
interceptor.start(page)

url = "https://www.wconcept.co.kr/Women"
page.goto(url, wait_until="domcontentloaded", timeout=60000)
page.wait_for_timeout(8000)

# 스크롤
for i in range(3):
    page.evaluate("window.scrollBy(0, window.innerHeight)")
    page.wait_for_timeout(1500)

interceptor.stop(page)

# 1) 버튼의 data attributes 및 부모 구조 확인
btn_analysis = page.evaluate("""() => {
    var cards = document.querySelectorAll('.product-item');
    var results = [];
    for (var i = 0; i < Math.min(5, cards.length); i++) {
        var card = cards[i];
        var btn = card.querySelector('button.btn');
        var cardAttrs = {};
        for (var j = 0; j < card.attributes.length; j++) {
            var attr = card.attributes[j];
            if (attr.name.indexOf('data-') === 0 || attr.name === 'id') {
                cardAttrs[attr.name] = attr.value.substring(0, 100);
            }
        }

        var btnAttrs = {};
        if (btn) {
            for (var j = 0; j < btn.attributes.length; j++) {
                var attr = btn.attributes[j];
                cardAttrs['btn_' + attr.name] = attr.value.substring(0, 100);
            }
        }

        // 부모에 data 속성 확인
        var parent = card.parentElement;
        var parentAttrs = {};
        if (parent) {
            for (var j = 0; j < parent.attributes.length; j++) {
                var attr = parent.attributes[j];
                if (attr.name.indexOf('data-') === 0) {
                    parentAttrs[attr.name] = attr.value.substring(0, 100);
                }
            }
        }

        results.push({
            cardAttrs: cardAttrs,
            parentAttrs: parentAttrs,
            cardOuterHTML_start: card.outerHTML.substring(0, 300),
        });
    }
    return results;
}""")

print("[diag] === Card/Button data attributes ===")
for i, r in enumerate(btn_analysis):
    print(f"\n  Card {i+1}:")
    for k, v in r['cardAttrs'].items():
        print(f"    {k}: {v}")
    if r['parentAttrs']:
        print(f"    Parent attrs: {r['parentAttrs']}")
    print(f"    HTML start: {r['cardOuterHTML_start'][:200]}")

# 2) __NEXT_DATA__ 에서 상품 정보 확인
next_data_info = page.evaluate("""() => {
    var el = document.getElementById('__NEXT_DATA__');
    if (!el) return null;
    try {
        var data = JSON.parse(el.textContent);
        var pp = data.props && data.props.pageProps;
        if (!pp) return {keys: Object.keys(data), noPageProps: true};

        var ppKeys = Object.keys(pp);
        // 상품 관련 키 찾기
        var productKeys = {};
        for (var i = 0; i < ppKeys.length; i++) {
            var key = ppKeys[i];
            var val = pp[key];
            var valType = Array.isArray(val) ? 'array(' + val.length + ')' : typeof val;
            if (typeof val === 'object' && val !== null && !Array.isArray(val)) {
                valType = 'object(' + Object.keys(val).length + ' keys)';
            }
            productKeys[key] = valType;
        }
        return {pagePropsKeys: productKeys};
    } catch(e) {
        return {error: e.message};
    }
}""")
print(f"\n[diag] __NEXT_DATA__: {json.dumps(next_data_info, ensure_ascii=False, indent=2)}")

# 3) __NEXT_DATA__.props.pageProps 에서 상품 데이터 추출 시도
product_from_next = page.evaluate("""() => {
    var el = document.getElementById('__NEXT_DATA__');
    if (!el) return null;
    try {
        var data = JSON.parse(el.textContent);
        var pp = data.props && data.props.pageProps;
        if (!pp) return null;

        // 배열인 키 찾기
        var arrays = {};
        for (var key in pp) {
            if (Array.isArray(pp[key]) && pp[key].length > 0) {
                var sample = pp[key][0];
                if (typeof sample === 'object' && sample !== null) {
                    arrays[key] = {
                        length: pp[key].length,
                        sampleKeys: Object.keys(sample),
                        sample: JSON.stringify(sample).substring(0, 300),
                    };
                }
            }
        }

        // 중첩 객체에서 배열 찾기
        for (var key in pp) {
            if (typeof pp[key] === 'object' && pp[key] !== null && !Array.isArray(pp[key])) {
                for (var subKey in pp[key]) {
                    if (Array.isArray(pp[key][subKey]) && pp[key][subKey].length > 0) {
                        var sample = pp[key][subKey][0];
                        if (typeof sample === 'object' && sample !== null) {
                            arrays[key + '.' + subKey] = {
                                length: pp[key][subKey].length,
                                sampleKeys: Object.keys(sample),
                                sample: JSON.stringify(sample).substring(0, 300),
                            };
                        }
                    }
                }
            }
        }

        return arrays;
    } catch(e) {
        return {error: e.message};
    }
}""")
print(f"\n[diag] Product arrays in __NEXT_DATA__:")
if product_from_next:
    for key, info in product_from_next.items():
        print(f"\n  {key}: {info['length']} items")
        print(f"    keys: {info['sampleKeys']}")
        try:
            print(f"    sample: {info['sample'][:200]}")
        except:
            print(f"    sample: (encoding)")

# 4) 캡처된 API 응답 분석
captured = list(interceptor.captured)
product_apis = [r for r in captured if 'product' in r.get('url', '').lower() or 'item' in r.get('url', '').lower()]
print(f"\n[diag] Product-related API responses: {len(product_apis)}")
for req in product_apis:
    url_short = req.get("url", "")[:120]
    body = req.get("body", "") or ""
    print(f"  [{req.get('status')}] body_len={len(body)} {url_short}")
    if body:
        try:
            data = json.loads(body)
            if isinstance(data, dict):
                print(f"    top keys: {list(data.keys())[:10]}")
                # data 안의 배열 찾기
                for k, v in data.items():
                    if isinstance(v, list) and len(v) > 0:
                        if isinstance(v[0], dict):
                            print(f"    {k}: {len(v)} items, keys={list(v[0].keys())[:8]}")
                            print(f"    sample: {json.dumps(v[0], ensure_ascii=False)[:200]}")
        except:
            pass

bm.close()
print("\n[diag] Done")
