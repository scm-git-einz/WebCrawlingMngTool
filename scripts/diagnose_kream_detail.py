"""KREAM 상세 진단 - 페이지 로딩 확인"""
import sys
import json
import time
sys.path.insert(0, "D:\\crawling")

from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

url = "https://kream.co.kr"

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context(
        viewport={"width": 1920, "height": 1080},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    )
    page = ctx.new_page()
    Stealth().apply_stealth_sync(page)

    resp = page.goto(url, wait_until="domcontentloaded", timeout=60000)
    print(f"Status: {resp.status}")
    print(f"URL: {page.url}")
    time.sleep(8)

    title = page.title()
    print(f"Title: {title}")

    html_len = page.evaluate("document.documentElement.outerHTML.length")
    print(f"HTML length: {html_len}")

    body_text = page.evaluate("document.body ? document.body.innerText.substring(0, 800) : 'NO BODY'")
    print(f"Body text preview:\n{body_text}")

    # Bot detection check
    cf_check = page.evaluate(r"""() => {
        var html = document.documentElement.outerHTML;
        return {
            hasCloudflare: html.indexOf('cloudflare') > -1 || html.indexOf('cf-') > -1,
            hasCaptcha: html.indexOf('captcha') > -1 || html.indexOf('challenge') > -1,
            hasBlocked: html.indexOf('blocked') > -1 || html.indexOf('denied') > -1,
            hasVerify: html.indexOf('verify') > -1,
            scripts: Array.from(document.querySelectorAll('script[src]')).slice(0, 10).map(function(s) {
                return s.getAttribute('src');
            }),
        };
    }""")
    print(f"\nBot detection check:")
    print(json.dumps(cf_check, indent=2, ensure_ascii=False))

    # Element counts
    elem_count = page.evaluate(r"""() => {
        return {
            total: document.querySelectorAll('*').length,
            divs: document.querySelectorAll('div').length,
            imgs: document.querySelectorAll('img').length,
            anchors: document.querySelectorAll('a').length,
            iframes: document.querySelectorAll('iframe').length,
        };
    }""")
    print(f"\nElement counts: {json.dumps(elem_count)}")

    # Check __NEXT_DATA__ or any global state
    global_state = page.evaluate(r"""() => {
        var result = {};
        if (window.__NEXT_DATA__) result.nextData = Object.keys(window.__NEXT_DATA__);
        if (window.__NUXT__) result.nuxt = Object.keys(window.__NUXT__);
        if (window.__pinia) result.pinia = true;
        if (window.__INITIAL_STATE__) result.initialState = true;
        // Check for React root
        var root = document.getElementById('root') || document.getElementById('__next') || document.getElementById('app');
        if (root) {
            result.rootId = root.id;
            result.rootChildCount = root.children.length;
            result.rootHTML = root.innerHTML.substring(0, 300);
        }
        return result;
    }""")
    print(f"\nGlobal state:")
    print(json.dumps(global_state, indent=2, ensure_ascii=False))

    # Try waiting longer with networkidle
    print("\n--- Trying networkidle wait ---")
    try:
        page.goto(url, wait_until="networkidle", timeout=60000)
        time.sleep(5)
        for _ in range(3):
            page.evaluate("window.scrollBy(0, window.innerHeight)")
            time.sleep(2)

        html_len2 = page.evaluate("document.documentElement.outerHTML.length")
        print(f"HTML length after networkidle+scroll: {html_len2}")

        elem_count2 = page.evaluate(r"""() => {
            return {
                total: document.querySelectorAll('*').length,
                divs: document.querySelectorAll('div').length,
                imgs: document.querySelectorAll('img').length,
                anchors: document.querySelectorAll('a').length,
            };
        }""")
        print(f"Element counts: {json.dumps(elem_count2)}")

        # Search for product-like patterns
        product_search = page.evaluate(r"""() => {
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
                        name.indexOf('list') > -1 ||
                        name.indexOf('price') > -1 ||
                        name.indexOf('brand') > -1 ||
                        name.indexOf('shop') > -1
                    )) {
                        classCounts[classes[c]] = (classCounts[classes[c]] || 0) + 1;
                    }
                }
            }
            // Sort by count
            var sorted = Object.keys(classCounts).sort(function(a, b) {
                return classCounts[b] - classCounts[a];
            });
            var top = {};
            for (var i = 0; i < Math.min(sorted.length, 20); i++) {
                top[sorted[i]] = classCounts[sorted[i]];
            }
            return top;
        }""")
        print(f"\nProduct-related classes:")
        print(json.dumps(product_search, indent=2, ensure_ascii=False))

        # Check links
        link_patterns = page.evaluate(r"""() => {
            var links = document.querySelectorAll('a[href]');
            var patterns = {};
            for (var i = 0; i < links.length; i++) {
                var href = links[i].getAttribute('href') || '';
                if (href.indexOf('/products/') > -1 || href.indexOf('/product/') > -1) {
                    patterns['product_links'] = (patterns['product_links'] || 0) + 1;
                }
                if (href.indexOf('/shop/') > -1) {
                    patterns['shop_links'] = (patterns['shop_links'] || 0) + 1;
                }
            }
            // Sample product links
            var prodLinks = document.querySelectorAll('a[href*="product"]');
            patterns['samples'] = Array.from(prodLinks).slice(0, 5).map(function(l) {
                return l.getAttribute('href');
            });
            return patterns;
        }""")
        print(f"\nLink patterns:")
        print(json.dumps(link_patterns, indent=2, ensure_ascii=False))

    except Exception as e:
        print(f"networkidle error: {e}")

    browser.close()
    print("\n진단 완료")
