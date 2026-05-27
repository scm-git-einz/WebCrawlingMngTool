"""KREAM /shop 페이지 진단 - 상품 목록 추출 가능성 확인"""
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
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        locale="ko-KR",
        timezone_id="Asia/Seoul",
        extra_http_headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Sec-Ch-Ua": '"Chromium";v="125", "Google Chrome";v="125", "Not=A?Brand";v="8"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        },
    )
    page = ctx.new_page()
    Stealth().apply_stealth_sync(page)

    interceptor = NetworkInterceptor()
    interceptor.start(page)

    # 메인 페이지 로드 후 SHOP 탭 찾기
    page.goto(url, wait_until="networkidle", timeout=60000)
    time.sleep(3)

    # SHOP 링크 찾기
    shop_links = page.evaluate(r"""() => {
        var links = document.querySelectorAll('a[href]');
        var results = [];
        for (var i = 0; i < links.length; i++) {
            var href = links[i].getAttribute('href') || '';
            var text = (links[i].textContent || '').trim();
            if (href.indexOf('/shop') > -1 || text === 'SHOP' || text === 'Shop') {
                results.push({href: href, text: text.substring(0, 30)});
            }
        }
        return results;
    }""")
    print(f"SHOP 링크: {json.dumps(shop_links, indent=2, ensure_ascii=False)}")

    # /shop 직접 접속
    print("\n=== /shop 페이지 접속 ===")
    interceptor.captured = []  # reset
    page.goto("https://kream.co.kr/shop", wait_until="networkidle", timeout=60000)
    time.sleep(5)

    print(f"URL: {page.url}")
    title = page.title()
    print(f"Title: {title}")

    # 스크롤
    for _ in range(5):
        page.evaluate("window.scrollBy(0, window.innerHeight)")
        time.sleep(2)

    # 요소 수
    elem_count = page.evaluate(r"""() => {
        return {
            total: document.querySelectorAll('*').length,
            divs: document.querySelectorAll('div').length,
            imgs: document.querySelectorAll('img').length,
            anchors: document.querySelectorAll('a').length,
        };
    }""")
    print(f"Elements: {json.dumps(elem_count)}")

    # 상품 관련 클래스
    product_classes = page.evaluate(r"""() => {
        var all = document.querySelectorAll('*');
        var classCounts = {};
        for (var i = 0; i < all.length; i++) {
            var el = all[i];
            var cls = typeof el.className === 'string' ? el.className : '';
            if (!cls) continue;
            var classes = cls.trim().split(/\s+/);
            for (var c = 0; c < classes.length; c++) {
                var name = classes[c].toLowerCase();
                if (name.length > 2 && (
                    name.indexOf('product') > -1 ||
                    name.indexOf('item') > -1 ||
                    name.indexOf('card') > -1 ||
                    name.indexOf('goods') > -1 ||
                    name.indexOf('price') > -1 ||
                    name.indexOf('brand') > -1 ||
                    name.indexOf('shop') > -1 ||
                    name.indexOf('search') > -1
                )) {
                    classCounts[classes[c]] = (classCounts[classes[c]] || 0) + 1;
                }
            }
        }
        var sorted = Object.keys(classCounts).sort(function(a, b) {
            return classCounts[b] - classCounts[a];
        });
        var top = {};
        for (var i = 0; i < Math.min(sorted.length, 30); i++) {
            top[sorted[i]] = classCounts[sorted[i]];
        }
        return top;
    }""")
    print(f"\nProduct-related classes:")
    print(json.dumps(product_classes, indent=2, ensure_ascii=False))

    # 상품 링크
    prod_links = page.evaluate(r"""() => {
        var links = document.querySelectorAll('a[href*="products"]');
        return {
            count: links.length,
            samples: Array.from(links).slice(0, 5).map(function(l) {
                return {
                    href: l.getAttribute('href'),
                    text: (l.textContent || '').trim().substring(0, 80),
                    classes: typeof l.className === 'string' ? l.className.substring(0, 60) : '',
                };
            }),
        };
    }""")
    print(f"\nProduct links: {prod_links['count']}개")
    for s in prod_links['samples']:
        print(f"  href={s['href']}")
        print(f"  cls={s['classes']}")
        print(f"  text={s['text'][:60]}")
        print()

    # 가격 요소
    prices = page.evaluate(r"""() => {
        var priceEls = [];
        var allEls = document.querySelectorAll('*');
        for (var i = 0; i < allEls.length; i++) {
            var el = allEls[i];
            var text = (el.textContent || '').trim();
            if (/^\d{1,3}(,\d{3})+\s*원?$/.test(text) && el.children.length === 0) {
                priceEls.push({
                    tag: el.tagName.toLowerCase(),
                    cls: (typeof el.className === 'string' ? el.className : '').substring(0, 80),
                    text: text.substring(0, 50),
                    parentCls: el.parentElement ? (typeof el.parentElement.className === 'string' ? el.parentElement.className : '').substring(0, 80) : '',
                });
            }
        }
        return {count: priceEls.length, samples: priceEls.slice(0, 10)};
    }""")
    print(f"\nPrice elements (leaf): {prices['count']}개")
    for s in prices['samples']:
        print(f"  <{s['tag']} class='{s['cls']}'> '{s['text']}' (parent: '{s['parentCls']}')")

    # 네트워크 요청
    interceptor.stop(page)
    print(f"\n=== 캡처된 요청: {len(interceptor.captured)}개 ===")
    candidates = interceptor.get_api_candidates()
    print(f"API 후보: {len(candidates)}개")
    for c in candidates[:10]:
        print(f"  target={c['target_type']} score={c['score']} path={c['path']}")

    # XHR/Fetch 요청 확인
    print(f"\n=== XHR/Fetch 요청 ===")
    for req in interceptor.captured:
        rtype = req.get("resource_type", "")
        if rtype in ("xhr", "fetch"):
            print(f"  {req.get('method','GET')} {req.get('url','')[:120]}")

    # DOM에서 카드 구조 확인 (product link의 부모 구조)
    if prod_links['count'] > 0:
        card_structure = page.evaluate(r"""() => {
            var link = document.querySelector('a[href*="products"]');
            if (!link) return null;
            // 상위 5단계까지 확인
            var ancestors = [];
            var el = link;
            for (var i = 0; i < 5; i++) {
                if (!el.parentElement) break;
                el = el.parentElement;
                ancestors.push({
                    tag: el.tagName.toLowerCase(),
                    cls: (typeof el.className === 'string' ? el.className : '').substring(0, 100),
                    childCount: el.children.length,
                });
            }
            return {
                linkHTML: link.outerHTML.substring(0, 300),
                ancestors: ancestors,
            };
        }""")
        if card_structure:
            print(f"\n=== 상품 카드 구조 ===")
            print(f"Link HTML: {card_structure['linkHTML']}")
            for i, anc in enumerate(card_structure['ancestors']):
                print(f"  parent[{i}]: <{anc['tag']} class='{anc['cls']}'> children={anc['childCount']}")

    browser.close()
    print("\n진단 완료")
