"""네이버 스마트스토어 심층 진단 - __PRELOADED_STATE__ 없어진 상태"""
import sys
import json
sys.path.insert(0, "D:\\crawling")

from core.browser import BrowserManager

bm = BrowserManager()
page = bm.create()

url = "https://brand.naver.com/esteelauder"
print(f"[diag] Loading: {url}")
page.goto(url, wait_until="networkidle", timeout=60000)
page.wait_for_timeout(5000)

# 1) 모든 window 키 중 state-like 변수
all_vars = page.evaluate("""() => {
    var found = [];
    var keys = Object.keys(window);
    for (var i = 0; i < keys.length; i++) {
        var k = keys[i];
        // 기본 브라우저 프로퍼티 제외
        if (k.length > 3 && (
            k.indexOf('__') >= 0 ||
            k.indexOf('_') === 0 ||
            k[0] === k[0].toUpperCase()
        )) {
            var t = typeof window[k];
            if (t === 'object' && window[k] !== null) {
                var size = 0;
                try { size = Object.keys(window[k]).length; } catch(e) {}
                found.push({key: k, type: t, size: size});
            }
        }
    }
    return found;
}""")
print(f"\n[diag] === Window object variables ===")
for v in all_vars:
    if v['size'] > 0:
        print(f"  {v['key']}: {v['type']} ({v['size']} keys)")

# 2) script 태그에서 데이터 변수 찾기
script_vars = page.evaluate("""() => {
    var scripts = document.querySelectorAll('script:not([src])');
    var found = [];
    for (var i = 0; i < scripts.length; i++) {
        var text = scripts[i].textContent || '';
        if (text.length < 50) continue;
        // 변수 할당 패턴 찾기
        var patterns = [
            '__PRELOADED_STATE__', '__NEXT_DATA__', '__NUXT__',
            'window.__', 'self.__', 'globalThis.__',
            'preloadedState', 'initialState', 'pageProps',
        ];
        for (var j = 0; j < patterns.length; j++) {
            if (text.indexOf(patterns[j]) >= 0) {
                found.push({
                    pattern: patterns[j],
                    scriptIdx: i,
                    textLen: text.length,
                    snippet: text.substring(0, 200),
                });
                break;
            }
        }
    }
    return found;
}""")
print(f"\n[diag] === Script tags with state patterns ===")
for s in script_vars:
    print(f"  Pattern: {s['pattern']}, script#{s['scriptIdx']}, len={s['textLen']}")
    print(f"    snippet: {s['snippet'][:150]}")

# 3) __NEXT_DATA__ 확인
has_next = page.evaluate("() => typeof window.__NEXT_DATA__")
print(f"\n[diag] __NEXT_DATA__ type: {has_next}")
if has_next != "undefined":
    next_keys = page.evaluate("() => Object.keys(window.__NEXT_DATA__)")
    print(f"  keys: {next_keys}")

# 4) id="__NEXT_DATA__" script 태그 확인
next_script = page.evaluate("""() => {
    var el = document.getElementById('__NEXT_DATA__');
    if (!el) return null;
    try {
        var data = JSON.parse(el.textContent);
        return {
            keys: Object.keys(data),
            propsKeys: data.props ? Object.keys(data.props) : [],
            pagePropsKeys: data.props && data.props.pageProps ? Object.keys(data.props.pageProps) : [],
        };
    } catch(e) {
        return {error: e.message, textLen: (el.textContent || '').length};
    }
}""")
print(f"[diag] #__NEXT_DATA__ script: {json.dumps(next_script, ensure_ascii=False)}")

# 5) 실제 상품이 DOM에 있는지 확인
product_counts = page.evaluate("""() => {
    var results = {};
    // 일반적인 상품 관련 셀렉터 시도
    var selectors = [
        '[class*="product"]', '[class*="Product"]',
        '[class*="item"]', '[class*="Item"]',
        '[class*="goods"]', '[class*="Goods"]',
        'a[href*="/products/"]',
        'li a[href*="smartstore"]',
        '[data-nclick]',
        'ul li a',
    ];
    for (var i = 0; i < selectors.length; i++) {
        try {
            var els = document.querySelectorAll(selectors[i]);
            results[selectors[i]] = els.length;
        } catch(e) {
            results[selectors[i]] = 'error: ' + e.message;
        }
    }
    return results;
}""")
print(f"\n[diag] === DOM product element counts ===")
for sel, cnt in product_counts.items():
    if cnt and cnt != 0:
        print(f"  {sel}: {cnt}")

# 6) 네이버의 React 하이드레이션 데이터 확인
react_data = page.evaluate("""() => {
    // __next_f 배열 (Next.js RSC)
    if (window.__next_f && Array.isArray(window.__next_f)) {
        return {type: '__next_f', length: window.__next_f.length};
    }
    return null;
}""")
print(f"\n[diag] React/Next.js streaming data: {json.dumps(react_data, ensure_ascii=False)}")

# 7) 페이지 전체 텍스트에서 상품 관련 내용 확인
page_text_info = page.evaluate("""() => {
    var body = document.body.innerText || '';
    var lines = body.split('\\n').filter(function(l) { return l.trim().length > 0; });
    // 가격 패턴 찾기
    var pricePattern = /[0-9,]+원/g;
    var prices = body.match(pricePattern);
    return {
        totalLines: lines.length,
        totalChars: body.length,
        priceCount: prices ? prices.length : 0,
        samplePrices: prices ? prices.slice(0, 5) : [],
        first500: body.substring(0, 500),
    };
}""")
print(f"\n[diag] === Page text info ===")
print(f"  Lines: {page_text_info['totalLines']}, Chars: {page_text_info['totalChars']}")
print(f"  Price count: {page_text_info['priceCount']}")
print(f"  Sample prices: {page_text_info['samplePrices']}")

bm.close()
print("\n[diag] Done")
