"""Musinsa 랭킹 페이지 실제 DOM 구조 분석"""
import sys
import json
sys.path.insert(0, "D:\\crawling")
from core.browser import BrowserManager

bm = BrowserManager()
config = {
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "viewport": {"width": 1920, "height": 1080},
    "headers": {
        "Accept-Language": "ko-KR,ko;q=0.9",
    },
    "allowed_domains": [
        "www.musinsa.com", "musinsa.com",
        "static.msscdn.net", "image.msscdn.net", "msscdn.net",
        "api.musinsa.com", "client.musinsa.com",
    ],
    "blocked_resource_types": ["font", "media"],
}
page = bm.create(config)

url = "https://www.musinsa.com/main/musinsa/ranking"
resp = page.goto(url, wait_until="domcontentloaded", timeout=60000)
print(f"Status: {resp.status}, URL: {page.url}")
page.wait_for_timeout(5000)

# 스크롤
for i in range(5):
    page.evaluate("window.scrollBy(0, window.innerHeight)")
    page.wait_for_timeout(1500)

# 1. gtm-view-item-list 분석
print("\n=== .gtm-view-item-list 분석 ===")
gtm_info = page.evaluate("""() => {
    var cards = document.querySelectorAll('.gtm-view-item-list');
    var results = [];
    for (var i = 0; i < Math.min(cards.length, 5); i++) {
        var card = cards[i];
        var links = card.querySelectorAll('a[href]');
        var linkHrefs = [];
        for (var j = 0; j < links.length; j++) {
            linkHrefs.push({href: links[j].getAttribute('href'), text: links[j].textContent.trim().substring(0, 50)});
        }
        var text = card.textContent.trim().substring(0, 200);
        results.push({
            tag: card.tagName,
            classes: card.className.substring(0, 200),
            text: text,
            links: linkHrefs,
            childCount: card.children.length
        });
    }
    return {count: cards.length, items: results};
}""")
print(f"Count: {gtm_info['count']}")
for i, item in enumerate(gtm_info['items']):
    print(f"\n  [{i}] tag={item['tag']}, children={item['childCount']}")
    print(f"  classes: {item['classes'][:100]}")
    print(f"  text: {item['text'][:100]}")
    for link in item['links'][:3]:
        print(f"    link: {link['href']} → {link['text'][:50]}")

# 2. 실제 개별 상품 카드 찾기
print("\n=== 개별 상품 후보 탐색 ===")
product_candidates = page.evaluate("""() => {
    // 상품 관련 data attributes
    var attrSelectors = [
        '[data-goods-no]', '[data-goods-id]', '[data-product-id]',
        '[data-item-id]', '[data-product-no]',
        'a[href*="/products/"]', 'a[href*="/goods/"]',
        'a[href*="/product/"]'
    ];
    var results = {};
    for (var i = 0; i < attrSelectors.length; i++) {
        var sel = attrSelectors[i];
        var els = document.querySelectorAll(sel);
        if (els.length > 0) {
            var samples = [];
            for (var j = 0; j < Math.min(els.length, 3); j++) {
                var el = els[j];
                samples.push({
                    tag: el.tagName,
                    href: el.getAttribute('href') || '',
                    text: el.textContent.trim().substring(0, 80),
                    classes: el.className.substring(0, 100)
                });
            }
            results[sel] = {count: els.length, samples: samples};
        }
    }
    return results;
}""")
for sel, info in product_candidates.items():
    print(f"\n{sel}: {info['count']}개")
    for s in info['samples']:
        print(f"  {s['tag']} class='{s['classes'][:60]}' href='{s['href'][:60]}' text='{s['text'][:60]}'")

# 3. __NEXT_DATA__ 확인 (Next.js state)
print("\n=== __NEXT_DATA__ 확인 ===")
next_data = page.evaluate("""() => {
    var el = document.querySelector('#__NEXT_DATA__');
    if (!el) return null;
    try {
        var data = JSON.parse(el.textContent);
        var props = data.props && data.props.pageProps;
        if (!props) return {keys: Object.keys(data)};

        // data 키 구조 탐색
        var dataObj = props.data;
        if (dataObj) {
            var result = {topKeys: Object.keys(dataObj)};
            // 각 키의 타입과 크기
            for (var key in dataObj) {
                var val = dataObj[key];
                if (Array.isArray(val)) {
                    result[key + '_type'] = 'array[' + val.length + ']';
                    if (val.length > 0) {
                        result[key + '_sample_keys'] = Object.keys(val[0]).join(', ');
                    }
                } else if (typeof val === 'object' && val !== null) {
                    result[key + '_type'] = 'object';
                    result[key + '_keys'] = Object.keys(val).join(', ');
                } else {
                    result[key + '_type'] = typeof val;
                }
            }
            return result;
        }
        return {pagePropsKeys: Object.keys(props)};
    } catch(e) {
        return {error: e.message};
    }
}""")
print(json.dumps(next_data, indent=2, ensure_ascii=False))

# 4. API 요청 확인 (XHR)
print("\n=== 네트워크에서 포착된 API 요청 확인 ===")
# 페이지를 조금 더 기다려 API 호출 확인
api_check = page.evaluate("""() => {
    // performance entries에서 API 요청 확인
    var entries = performance.getEntriesByType('resource');
    var apis = [];
    for (var i = 0; i < entries.length; i++) {
        var name = entries[i].name;
        if (name.indexOf('/api/') > -1 || name.indexOf('client.musinsa') > -1) {
            apis.push(name);
        }
    }
    return apis;
}""")
for api in api_check[:20]:
    print(f"  {api}")

bm.close()
print("\nDone!")
