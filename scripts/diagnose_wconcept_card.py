"""W Concept: prdc-price 부모에서 상품 카드 구조 찾기"""
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

    for _ in range(3):
        page.evaluate("window.scrollBy(0, window.innerHeight)")
        time.sleep(1)

    # prdc-price 부모 계층에서 안정적 반복 패턴 찾기
    card_info = page.evaluate(r"""() => {
        var priceEls = document.querySelectorAll('.prdc-price');
        var results = {count: priceEls.length, parentPatterns: {}};

        // 각 price 요소의 부모 계층 분석
        for (var i = 0; i < priceEls.length; i++) {
            var parent = priceEls[i].parentElement;
            for (var d = 0; d < 8 && parent; d++) {
                var cls = typeof parent.className === 'string' ? parent.className : '';
                var stableClasses = cls.split(/\s+/).filter(function(c) {
                    return c && !c.startsWith('sc-') && !/[^a-zA-Z0-9_-]/.test(c);
                });

                for (var c = 0; c < stableClasses.length; c++) {
                    var key = parent.tagName.toLowerCase() + '.' + stableClasses[c];
                    if (!results.parentPatterns[key]) {
                        results.parentPatterns[key] = {count: 0, depth: d, totalEls: 0};
                    }
                    results.parentPatterns[key].count++;
                }
                parent = parent.parentElement;
            }
        }

        // 각 후보의 totalElements 계산 + 구조 분석
        var candidates = [];
        for (var k in results.parentPatterns) {
            var info = results.parentPatterns[k];
            if (info.count < 3) continue;
            var dotIdx = k.indexOf('.');
            var clsName = k.substring(dotIdx + 1);
            try {
                var els = document.querySelectorAll('.' + clsName);
                info.totalEls = els.length;
                var ratio = els.length / info.count;

                // 첫 번째 요소의 내부 구조 분석
                var sample = els[0];
                var hasImg = sample.querySelectorAll('img').length > 0;
                var hasLink = sample.querySelectorAll('a[href]').length > 0;
                var links = sample.querySelectorAll('a[href]');
                var linkHrefs = [];
                for (var li = 0; li < Math.min(links.length, 3); li++) {
                    linkHrefs.push(links[li].getAttribute('href'));
                }

                // 내부 안정적 클래스
                var innerStable = {};
                var innerEls = sample.querySelectorAll('[class]');
                for (var ie = 0; ie < innerEls.length; ie++) {
                    var icls = typeof innerEls[ie].className === 'string' ? innerEls[ie].className : '';
                    var stable = icls.split(/\s+/).filter(function(c) {
                        return c && !c.startsWith('sc-') && !/[^a-zA-Z0-9_-]/.test(c);
                    });
                    for (var sc = 0; sc < stable.length; sc++) {
                        if (!innerStable[stable[sc]]) innerStable[stable[sc]] = 0;
                        innerStable[stable[sc]]++;
                    }
                }

                // 상품 관련 안정적 클래스
                var relevantInner = {};
                for (var ik in innerStable) {
                    if (/prdc|product|title|name|brand|price|img|image|thumb|link/i.test(ik)) {
                        relevantInner[ik] = innerStable[ik];
                    }
                }

                candidates.push({
                    key: k,
                    count: info.count,
                    totalEls: info.totalEls,
                    ratio: Math.round(ratio * 100) / 100,
                    depth: info.depth,
                    hasImg: hasImg,
                    hasLink: hasLink,
                    linkHrefs: linkHrefs,
                    relevantInner: relevantInner,
                });
            } catch(e) { continue; }
        }

        candidates.sort(function(a,b) { return b.count - a.count; });
        return candidates.slice(0, 15);
    }""")

    print(f"=== .prdc-price 부모 패턴 ===")
    for c in card_info:
        flag = ""
        if not c['hasImg']: flag += " [NO-IMG]"
        if not c['hasLink']: flag += " [NO-LINK]"
        print(f"\n  {c['key']}: count={c['count']} total={c['totalEls']} "
              f"ratio={c['ratio']} depth={c['depth']}{flag}")
        if c['linkHrefs']:
            print(f"    links: {c['linkHrefs'][:2]}")
        if c['relevantInner']:
            print(f"    inner: {c['relevantInner']}")

    browser.close()
    print("\n진단 완료")
