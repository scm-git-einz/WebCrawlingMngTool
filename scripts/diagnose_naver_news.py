"""네이버 뉴스 검색 페이지 DOM 구조 분석"""
import sys
import json
sys.path.insert(0, "D:\\crawling")
from core.browser import BrowserManager

bm = BrowserManager()
page = bm.create()

# 네이버 뉴스 검색 (최신순)
url = "https://search.naver.com/search.naver?where=news&query=%ED%95%B4%EC%99%B8%EC%97%AC%ED%96%89&sort=1"
print(f"URL: {url}")
resp = page.goto(url, wait_until="domcontentloaded", timeout=60000)
print(f"Status: {resp.status}")
page.wait_for_timeout(3000)

# 1. 뉴스 기사 카드 구조 분석
print("\n=== 뉴스 기사 카드 구조 ===")
structure = page.evaluate("""() => {
    // 뉴스 결과 영역 탐색
    var containers = [
        '.news_area', '.group_news', '.list_news',
        '#news_result_list', '.news_wrap',
        '[class*="news"]', '[class*="article"]',
        '.sp_nws', '.bx'
    ];
    var found = {};
    for (var i = 0; i < containers.length; i++) {
        var els = document.querySelectorAll(containers[i]);
        if (els.length > 0) {
            found[containers[i]] = els.length;
        }
    }

    // 뉴스 제목 링크 탐색
    var titleSelectors = [
        '.news_tit', 'a.news_tit', '.news_tit a',
        '.title_link', '.news_area a',
        '.news_contents a', '.group_news a',
        '.news_wrap a[href*="news"]',
        'a[class*="news_tit"]', 'a[class*="title"]'
    ];
    var titleFound = {};
    for (var j = 0; j < titleSelectors.length; j++) {
        var tels = document.querySelectorAll(titleSelectors[j]);
        if (tels.length > 0) {
            var samples = [];
            for (var k = 0; k < Math.min(tels.length, 3); k++) {
                samples.push({
                    text: tels[k].textContent.trim().substring(0, 80),
                    href: (tels[k].getAttribute('href') || '').substring(0, 120),
                    tag: tels[k].tagName,
                    classes: tels[k].className.substring(0, 100)
                });
            }
            titleFound[titleSelectors[j]] = {count: tels.length, samples: samples};
        }
    }

    return {containers: found, titles: titleFound};
}""")

print("Containers:")
for sel, cnt in structure['containers'].items():
    print(f"  {sel}: {cnt}개")

print("\nTitle selectors:")
for sel, info in structure['titles'].items():
    print(f"\n  {sel}: {info['count']}개")
    for s in info['samples']:
        print(f"    [{s['tag']}] class='{s['classes'][:60]}'")
        print(f"    text: {s['text'][:60]}")
        print(f"    href: {s['href'][:80]}")

# 2. 개별 뉴스 카드 상세 구조
print("\n\n=== 개별 뉴스 카드 상세 ===")
cards = page.evaluate("""() => {
    // 뉴스 리스트 아이템 후보
    var itemSelectors = [
        '.bx', '.news_wrap', '.news_area',
        'li.bx', 'div.news_area', '.group_news li',
        '.list_news li', '.sp_nws .bx'
    ];

    var bestSel = null;
    var bestCount = 0;
    for (var i = 0; i < itemSelectors.length; i++) {
        var els = document.querySelectorAll(itemSelectors[i]);
        if (els.length > bestCount) {
            bestCount = els.length;
            bestSel = itemSelectors[i];
        }
    }

    if (!bestSel || bestCount === 0) return {bestSel: null, count: 0, cards: []};

    var items = document.querySelectorAll(bestSel);
    var cards = [];
    for (var j = 0; j < Math.min(items.length, 3); j++) {
        var item = items[j];

        // 내부 구조 분석
        var links = item.querySelectorAll('a[href]');
        var linkInfo = [];
        for (var k = 0; k < links.length; k++) {
            linkInfo.push({
                text: links[k].textContent.trim().substring(0, 80),
                href: (links[k].getAttribute('href') || '').substring(0, 120),
                classes: links[k].className.substring(0, 80)
            });
        }

        // 날짜/시간
        var dateEls = item.querySelectorAll('[class*="info"], [class*="date"], [class*="time"], time, span');
        var dates = [];
        for (var m = 0; m < dateEls.length; m++) {
            var dtText = dateEls[m].textContent.trim();
            if (dtText.length > 0 && dtText.length < 30) {
                dates.push({
                    text: dtText,
                    classes: dateEls[m].className.substring(0, 60),
                    tag: dateEls[m].tagName
                });
            }
        }

        // 언론사
        var pressEls = item.querySelectorAll('[class*="press"], [class*="source"], [class*="info_group"] a');
        var press = [];
        for (var n = 0; n < pressEls.length; n++) {
            press.push({
                text: pressEls[n].textContent.trim().substring(0, 30),
                classes: pressEls[n].className.substring(0, 60)
            });
        }

        cards.push({
            tag: item.tagName,
            classes: item.className.substring(0, 100),
            html_preview: item.innerHTML.substring(0, 300),
            links: linkInfo,
            dates: dates.slice(0, 5),
            press: press
        });
    }

    return {bestSel: bestSel, count: bestCount, cards: cards};
}""")

print(f"Best item selector: {cards['bestSel']} ({cards['count']}개)")
for i, card in enumerate(cards['cards']):
    print(f"\n  [{i}] {card['tag']} class='{card['classes'][:60]}'")
    print(f"  Links ({len(card['links'])}):")
    for link in card['links'][:3]:
        print(f"    class='{link['classes'][:40]}' → {link['text'][:50]}")
        print(f"    href: {link['href'][:80]}")
    print(f"  Dates: {[d['text'] for d in card['dates'][:3]]}")
    print(f"  Press: {[p['text'] for p in card['press'][:2]]}")

# 3. 페이지네이션 구조
print("\n\n=== 페이지네이션 ===")
pagination = page.evaluate("""() => {
    var pagSelectors = [
        '.sc_page_inner', '.paging', '.pagination',
        'a.btn_next', '[class*="next"]', '[class*="page"]'
    ];
    var result = {};
    for (var i = 0; i < pagSelectors.length; i++) {
        var els = document.querySelectorAll(pagSelectors[i]);
        if (els.length > 0) {
            var samples = [];
            for (var j = 0; j < Math.min(els.length, 3); j++) {
                samples.push({
                    text: els[j].textContent.trim().substring(0, 50),
                    href: els[j].getAttribute('href') || '',
                    tag: els[j].tagName,
                    classes: els[j].className.substring(0, 60)
                });
            }
            result[pagSelectors[i]] = {count: els.length, samples: samples};
        }
    }
    return result;
}""")
for sel, info in pagination.items():
    print(f"  {sel}: {info['count']}개")
    for s in info['samples'][:2]:
        print(f"    [{s['tag']}] class='{s['classes'][:40]}' text='{s['text'][:30]}'")

# 4. 전체 텍스트에서 기사 수 확인
print("\n=== 요약 ===")
summary = page.evaluate("""() => {
    var newsTit = document.querySelectorAll('a.news_tit');
    var results = [];
    for (var i = 0; i < newsTit.length; i++) {
        results.push({
            title: newsTit[i].textContent.trim().substring(0, 80),
            href: newsTit[i].getAttribute('href') || '',
        });
    }
    return results;
}""")
print(f"a.news_tit 기사 수: {len(summary)}")
for i, item in enumerate(summary[:5]):
    print(f"  [{i+1}] {item['title'][:60]}")
    print(f"      {item['href'][:80]}")

bm.close()
print("\nDone!")
