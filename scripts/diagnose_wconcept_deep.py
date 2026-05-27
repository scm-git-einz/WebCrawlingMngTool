"""W Concept 심층 진단: __NEXT_DATA__ + API 테스트"""
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

    # 1) __NEXT_DATA__ 구조 분석
    next_data = page.evaluate("""() => {
        if (!window.__NEXT_DATA__) return null;
        var d = window.__NEXT_DATA__;
        var pp = d.props && d.props.pageProps;
        if (!pp) return {keys: Object.keys(d)};

        var result = {pagePropsKeys: Object.keys(pp)};

        // initialData 구조 확인
        if (pp.initialData) {
            if (typeof pp.initialData === 'object') {
                result.initialDataKeys = Object.keys(pp.initialData);
                // 상품 데이터 탐색
                for (var k in pp.initialData) {
                    var v = pp.initialData[k];
                    if (Array.isArray(v) && v.length > 0 && typeof v[0] === 'object') {
                        result['initialData.' + k] = {
                            type: 'array',
                            length: v.length,
                            sampleKeys: Object.keys(v[0]).slice(0, 15)
                        };
                    } else if (typeof v === 'object' && v !== null) {
                        result['initialData.' + k] = {
                            type: 'object',
                            keys: Object.keys(v).slice(0, 10)
                        };
                    }
                }
            }
        }

        // dehydratedState 구조 확인
        if (pp.dehydratedState) {
            var ds = pp.dehydratedState;
            result.dehydratedStateKeys = Object.keys(ds);
            if (ds.queries && Array.isArray(ds.queries)) {
                result.queriesCount = ds.queries.length;
                for (var i = 0; i < Math.min(ds.queries.length, 5); i++) {
                    var q = ds.queries[i];
                    var qk = q.queryKey || [];
                    var state = q.state || {};
                    var data = state.data;
                    var info = {queryKey: JSON.stringify(qk).substring(0, 100)};
                    if (data && typeof data === 'object') {
                        info.dataKeys = Object.keys(data).slice(0, 10);
                        // 배열 확인
                        for (var dk in data) {
                            if (Array.isArray(data[dk]) && data[dk].length > 0) {
                                info['data.' + dk] = {
                                    length: data[dk].length,
                                    sampleKeys: typeof data[dk][0] === 'object' ? Object.keys(data[dk][0]).slice(0, 10) : 'non-object'
                                };
                            }
                        }
                    }
                    result['query_' + i] = info;
                }
            }
        }

        return result;
    }""")
    print("=== __NEXT_DATA__ 구조 ===")
    print(json.dumps(next_data, indent=2, ensure_ascii=False)[:3000])

    # 2) API 호출 테스트 (페이지 컨텍스트)
    api_test = page.evaluate("""() => {
        return fetch('https://api-display.wconcept.co.kr/display/api/v2/category/products/M33439436/001', {
            method: 'POST',
            credentials: 'include',
            headers: {'Content-Type': 'application/json; charset=UTF-8'},
            body: JSON.stringify({
                custNo: '',
                gender: 'All',
                sort: 'WCK',
                pageNo: 1,
                pageSize: 5,
                bcds: [],
                colors: [],
                benefits: [],
                discounts: [],
                status: ['01'],
                shopCds: [],
                domainType: 'pc'
            })
        })
        .then(function(res) {
            return {status: res.status, ok: res.ok, statusText: res.statusText, url: res.url};
        })
        .catch(function(err) {
            return {error: err.message || String(err)};
        });
    }""")
    print(f"\n=== API 호출 테스트 ===")
    print(json.dumps(api_test, indent=2))

    # API 성공 시 데이터 확인
    if api_test.get("ok"):
        api_data = page.evaluate("""() => {
            return fetch('https://api-display.wconcept.co.kr/display/api/v2/category/products/M33439436/001', {
                method: 'POST',
                credentials: 'include',
                headers: {'Content-Type': 'application/json; charset=UTF-8'},
                body: JSON.stringify({
                    custNo: '',
                    gender: 'All',
                    sort: 'WCK',
                    pageNo: 1,
                    pageSize: 3,
                    bcds: [],
                    colors: [],
                    benefits: [],
                    discounts: [],
                    status: ['01'],
                    shopCds: [],
                    domainType: 'pc'
                })
            })
            .then(function(res) { return res.json(); })
            .then(function(data) { return data; })
            .catch(function(err) { return {error: err.message}; });
        }""")
        print(f"\n=== API 응답 데이터 (상위 키) ===")
        if isinstance(api_data, dict):
            print(list(api_data.keys()))
            if "data" in api_data and isinstance(api_data["data"], dict):
                print(f"data 키: {list(api_data['data'].keys())}")
                pl = api_data["data"].get("productList", {})
                if isinstance(pl, dict):
                    content = pl.get("content", [])
                    print(f"productList.content 길이: {len(content)}")
                    if content:
                        print(f"첫 번째 아이템 키: {list(content[0].keys())}")
                        print(json.dumps(content[0], ensure_ascii=False)[:500])

    browser.close()
    print("\n진단 완료")
