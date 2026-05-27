"""네이버 카페 인기글 - 날짜 필드 DOM 구조 확인"""
import sys
sys.path.insert(0, "D:\\crawling")
from core.browser import BrowserManager

bm = BrowserManager()
page = bm.create()

url = "https://cafe.naver.com/ca-fe/cafes/14538121/popular"
resp = page.goto(url, wait_until="domcontentloaded", timeout=60000)
page.wait_for_timeout(5000)

# 1. 게시글 행(row)의 전체 구조 확인
print("=== 첫 3개 게시글 행 구조 ===")
rows_info = page.evaluate(r"""() => {
    var links = document.querySelectorAll('a.article[href]');
    var results = [];
    for (var i = 0; i < Math.min(links.length, 3); i++) {
        var a = links[i];
        var row = a.closest('tr, .inner_list, [class*="item"], li, div');
        if (!row) continue;

        // row 내부 모든 자식 요소 탐색
        var children = row.querySelectorAll('*');
        var childInfo = [];
        for (var j = 0; j < children.length; j++) {
            var el = children[j];
            var text = el.textContent.trim();
            if (text.length > 0 && text.length < 30) {
                childInfo.push({
                    tag: el.tagName,
                    cls: el.className.substring(0, 60),
                    text: text.substring(0, 30),
                });
            }
        }

        // td 요소들
        var tds = row.querySelectorAll('td');
        var tdInfo = [];
        for (var k = 0; k < tds.length; k++) {
            tdInfo.push({
                index: k,
                cls: tds[k].className.substring(0, 40),
                text: tds[k].textContent.trim().substring(0, 30),
                html: tds[k].innerHTML.substring(0, 150),
            });
        }

        results.push({
            rowTag: row.tagName,
            rowClass: row.className.substring(0, 80),
            rowHTML: row.outerHTML.substring(0, 500),
            tds: tdInfo,
            title: a.textContent.trim().substring(0, 40),
        });
    }
    return results;
}""")

for i, r in enumerate(rows_info):
    print(f"\n--- 게시글 {i+1}: {r['title']}")
    print(f"Row: <{r['rowTag']}> class='{r['rowClass']}'")
    print(f"TDs ({len(r['tds'])}):")
    for td in r['tds']:
        print(f"  td[{td['index']}] class='{td['cls']}' text='{td['text']}'")
        print(f"    html: {td['html'][:120]}")
    print(f"HTML: {r['rowHTML'][:300]}")

# 2. 날짜 관련 요소 직접 탐색
print("\n\n=== 날짜 관련 요소 탐색 ===")
date_info = page.evaluate(r"""() => {
    var selectors = [
        '.date', '.td_date', 'td.date',
        '[class*="date"]', '[class*="Date"]',
        '[class*="time"]', '[class*="Time"]',
        'time', '.txt_block',
    ];

    var found = {};
    for (var i = 0; i < selectors.length; i++) {
        var els = document.querySelectorAll(selectors[i]);
        if (els.length > 0) {
            var samples = [];
            for (var j = 0; j < Math.min(els.length, 5); j++) {
                samples.push({
                    text: els[j].textContent.trim().substring(0, 30),
                    cls: els[j].className.substring(0, 60),
                    tag: els[j].tagName,
                });
            }
            found[selectors[i]] = {count: els.length, samples: samples};
        }
    }
    return found;
}""")

for sel, info in date_info.items():
    print(f"\n{sel} ({info['count']}개):")
    for s in info['samples']:
        print(f"  <{s['tag']}> class='{s['cls']}' -> '{s['text']}'")

bm.close()
print("\nDone!")
