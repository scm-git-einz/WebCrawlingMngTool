"""KREAM 진단 - 다양한 접근 방식 시도"""
import sys
import json
import time
sys.path.insert(0, "D:\\crawling")

from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

url = "https://kream.co.kr"

with sync_playwright() as pw:
    # 시도 1: 더 완전한 브라우저 컨텍스트
    print("=== 시도 1: 풍부한 헤더 + headless ===")
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

    resp = page.goto(url, wait_until="domcontentloaded", timeout=60000)
    print(f"  Status: {resp.status}")
    time.sleep(3)
    html = page.evaluate("document.documentElement.outerHTML")
    print(f"  HTML length: {len(html)}")
    print(f"  HTML: {html[:300]}")
    browser.close()

    # 시도 2: headed 모드 (실제 브라우저 창)
    print("\n=== 시도 2: headed 모드 ===")
    browser2 = pw.chromium.launch(headless=False)
    ctx2 = browser2.new_context(
        viewport={"width": 1920, "height": 1080},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        locale="ko-KR",
        timezone_id="Asia/Seoul",
    )
    page2 = ctx2.new_page()
    Stealth().apply_stealth_sync(page2)

    resp2 = page2.goto(url, wait_until="domcontentloaded", timeout=60000)
    print(f"  Status: {resp2.status}")
    time.sleep(5)

    html2 = page2.evaluate("document.documentElement.outerHTML")
    print(f"  HTML length: {len(html2)}")
    title2 = page2.title()
    print(f"  Title: {title2}")

    if len(html2) > 100:
        # 상세 분석
        elem_count = page2.evaluate(r"""() => {
            return {
                total: document.querySelectorAll('*').length,
                divs: document.querySelectorAll('div').length,
                imgs: document.querySelectorAll('img').length,
                anchors: document.querySelectorAll('a').length,
            };
        }""")
        print(f"  Elements: {json.dumps(elem_count)}")

        body_preview = page2.evaluate("(document.body.innerText || '').substring(0, 500)")
        print(f"  Body text: {body_preview[:200]}")

        # 스크롤 후 확인
        for _ in range(3):
            page2.evaluate("window.scrollBy(0, window.innerHeight)")
            time.sleep(2)

        product_classes = page2.evaluate(r"""() => {
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
                        name.indexOf('home') > -1
                    )) {
                        classCounts[classes[c]] = (classCounts[classes[c]] || 0) + 1;
                    }
                }
            }
            var sorted = Object.keys(classCounts).sort(function(a, b) {
                return classCounts[b] - classCounts[a];
            });
            var top = {};
            for (var i = 0; i < Math.min(sorted.length, 20); i++) {
                top[sorted[i]] = classCounts[sorted[i]];
            }
            return top;
        }""")
        print(f"\n  Product-related classes:")
        print(json.dumps(product_classes, indent=2, ensure_ascii=False))

        # product links
        link_info = page2.evaluate(r"""() => {
            var links = document.querySelectorAll('a[href]');
            var prodLinks = [];
            for (var i = 0; i < links.length; i++) {
                var href = links[i].getAttribute('href') || '';
                if (href.indexOf('/products/') > -1) {
                    prodLinks.push(href);
                }
            }
            return {count: prodLinks.length, samples: prodLinks.slice(0, 5)};
        }""")
        print(f"\n  Product links: {json.dumps(link_info, indent=2, ensure_ascii=False)}")

        # framework state
        fw = page2.evaluate(r"""() => {
            var result = {};
            if (window.__NEXT_DATA__) result.nextData = Object.keys(window.__NEXT_DATA__);
            if (window.__NUXT__) result.nuxt = Object.keys(window.__NUXT__);
            if (window.__pinia) result.pinia = true;
            var root = document.getElementById('root') || document.getElementById('__next') || document.getElementById('app') || document.getElementById('__nuxt');
            if (root) result.rootId = root.id;
            return result;
        }""")
        print(f"\n  Framework state: {json.dumps(fw, indent=2, ensure_ascii=False)}")

        # 가격 패턴
        prices = page2.evaluate(r"""() => {
            var priceEls = [];
            var allEls = document.querySelectorAll('*');
            for (var i = 0; i < allEls.length; i++) {
                var el = allEls[i];
                var text = (el.textContent || '').trim();
                if (/\d{1,3}(,\d{3})+\s*원?/.test(text) && el.children.length < 3) {
                    priceEls.push({
                        tag: el.tagName.toLowerCase(),
                        cls: (typeof el.className === 'string' ? el.className : '').substring(0, 60),
                        text: text.substring(0, 50),
                    });
                }
            }
            return {count: priceEls.length, samples: priceEls.slice(0, 10)};
        }""")
        print(f"\n  Price elements: {prices['count']}개")
        for s in prices['samples']:
            print(f"    <{s['tag']} class='{s['cls']}'> '{s['text']}'")

    browser2.close()
    print("\n진단 완료")
