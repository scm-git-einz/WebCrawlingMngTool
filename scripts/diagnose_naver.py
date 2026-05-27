"""네이버 스마트스토어 0 products 진단"""
import sys
import json
sys.path.insert(0, "D:\\crawling")

from core.browser import BrowserManager

bm = BrowserManager()
page = bm.create()

url = "https://brand.naver.com/esteelauder"
print(f"[diag] Loading: {url}")
page.goto(url, wait_until="domcontentloaded")
page.wait_for_timeout(5000)

# 1) __PRELOADED_STATE__ 존재 확인
has_state = page.evaluate("() => typeof window.__PRELOADED_STATE__")
print(f"[diag] __PRELOADED_STATE__ type: {has_state}")

if has_state == "undefined":
    print("[diag] __PRELOADED_STATE__ 없음!")
    # 페이지 소스에서 찾기
    html = page.content()
    idx = html.find("__PRELOADED_STATE__")
    if idx >= 0:
        print(f"[diag] HTML에는 __PRELOADED_STATE__ 있음 (위치: {idx})")
        snippet = html[idx:idx+200]
        print(f"[diag] snippet: {snippet}")
    else:
        print("[diag] HTML에도 __PRELOADED_STATE__ 없음")

    # 다른 state 변수 확인
    state_vars = page.evaluate("""() => {
        var found = [];
        var keys = Object.keys(window);
        for (var i = 0; i < keys.length; i++) {
            var k = keys[i];
            if (k.indexOf('__') === 0 || k.indexOf('NEXT') >= 0 || k.indexOf('NUXT') >= 0) {
                found.push(k);
            }
        }
        return found;
    }""")
    print(f"[diag] State-like window vars: {state_vars}")
else:
    # 2) 최상위 키 확인
    top_keys = page.evaluate("""() => {
        var state = window.__PRELOADED_STATE__;
        if (!state) return [];
        return Object.keys(state);
    }""")
    print(f"[diag] Top keys: {top_keys}")

    # 3) categoryMenu 확인
    cat_info = page.evaluate("""() => {
        var state = window.__PRELOADED_STATE__;
        if (!state) return null;
        var cm = state.categoryMenu;
        if (!cm) return {error: 'no categoryMenu'};
        var keys = Object.keys(cm);
        var fc = cm.firstCategories;
        return {
            keys: keys,
            hasFirstCategories: !!fc,
            firstCategoriesType: fc ? (Array.isArray(fc) ? 'array' : typeof fc) : 'none',
            firstCategoriesLen: fc && Array.isArray(fc) ? fc.length : 0,
            sample: fc && fc.length > 0 ? JSON.stringify(fc[0]).substring(0, 200) : 'none',
        };
    }""")
    print(f"[diag] categoryMenu info: {json.dumps(cat_info, ensure_ascii=False, indent=2)}")

    # 4) categoryProducts 확인
    prod_info = page.evaluate("""() => {
        var state = window.__PRELOADED_STATE__;
        if (!state) return null;
        var cp = state.categoryProducts;
        if (!cp) return {error: 'no categoryProducts'};
        var keys = Object.keys(cp);
        var sp = cp.simpleProducts;
        return {
            keys: keys,
            hasSimpleProducts: !!sp,
            simpleProductsLen: sp ? (Array.isArray(sp) ? sp.length : 'not array') : 0,
            totalCount: cp.totalCount || 'N/A',
        };
    }""")
    print(f"[diag] categoryProducts info: {json.dumps(prod_info, ensure_ascii=False, indent=2)}")

    # 5) channel 확인
    ch_info = page.evaluate("""() => {
        var state = window.__PRELOADED_STATE__;
        if (!state || !state.channel) return null;
        var ch = state.channel;
        return {
            channelName: ch.channelName || 'N/A',
            channelNo: ch.channelNo || 'N/A',
        };
    }""")
    print(f"[diag] channel info: {json.dumps(ch_info, ensure_ascii=False, indent=2)}")

# 5) 페이지 URL 확인 (리다이렉트 여부)
print(f"[diag] Current URL: {page.url}")
print(f"[diag] Page title: {page.title()}")

bm.close()
print("[diag] Done")
