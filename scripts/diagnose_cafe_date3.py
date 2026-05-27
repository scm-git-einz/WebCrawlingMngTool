"""네이버 카페 인기글 - 부모 tr 레벨에서 날짜 찾기"""
import sys
sys.path.insert(0, "D:\\crawling")
from core.browser import BrowserManager

bm = BrowserManager()
page = bm.create()

url = "https://cafe.naver.com/ca-fe/cafes/14538121/popular"
resp = page.goto(url, wait_until="domcontentloaded", timeout=60000)
page.wait_for_timeout(5000)

# a.article의 부모 탐색 (tr까지)
print("=== a.article 부모 계층 ===")
parent_info = page.evaluate(r"""() => {
    var a = document.querySelector('a.article[href]');
    if (!a) return {error: 'no article link'};

    // 부모를 따라 올라가며 구조 파악
    var chain = [];
    var el = a;
    for (var i = 0; i < 10; i++) {
        el = el.parentElement;
        if (!el) break;
        chain.push({
            tag: el.tagName,
            cls: (el.className || '').substring(0, 80),
            childCount: el.children.length,
        });
        if (el.tagName === 'TABLE' || el.tagName === 'TBODY') break;
    }
    return chain;
}""")
for p in parent_info:
    print(f"  <{p['tag']}> class='{p['cls']}' children={p['childCount']}")

# tr 행의 전체 HTML 확인
print("\n=== 첫 2개 tr 행 HTML ===")
tr_html = page.evaluate(r"""() => {
    var trs = document.querySelectorAll('tr');
    var results = [];
    for (var i = 0; i < trs.length; i++) {
        var tr = trs[i];
        // article 링크가 있는 행만
        if (tr.querySelector('a.article')) {
            results.push(tr.outerHTML.substring(0, 1500));
            if (results.length >= 2) break;
        }
    }
    return results;
}""")
for i, h in enumerate(tr_html):
    safe = h.encode('ascii', errors='replace').decode('ascii')
    print(f"\n--- tr {i+1} ---")
    print(safe)

# tr 내부 td별 분석
print("\n\n=== tr 내 td 분석 ===")
td_info = page.evaluate(r"""() => {
    var trs = document.querySelectorAll('tr');
    var results = [];
    for (var i = 0; i < trs.length; i++) {
        var tr = trs[i];
        if (!tr.querySelector('a.article')) continue;
        var tds = tr.querySelectorAll('td');
        var tdList = [];
        for (var j = 0; j < tds.length; j++) {
            tdList.push({
                index: j,
                cls: (tds[j].className || '').substring(0, 60),
                text: tds[j].textContent.trim().substring(0, 50),
            });
        }
        results.push(tdList);
        if (results.length >= 3) break;
    }
    return results;
}""")
for i, tds in enumerate(td_info):
    print(f"\ntr {i+1} ({len(tds)} tds):")
    for td in tds:
        t = td['text'].encode('cp949', errors='replace').decode('cp949')
        print(f"  td[{td['index']}] cls='{td['cls']}' -> '{t}'")

bm.close()
print("\nDone!")
