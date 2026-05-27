"""네이버 카페 인기글 - 페이징 구조 분석"""
import sys
sys.path.insert(0, "D:\\crawling")
from core.browser import BrowserManager

bm = BrowserManager()
page = bm.create()

url = "https://cafe.naver.com/ca-fe/cafes/14538121/popular"
print(f"접속: {url}")
resp = page.goto(url, wait_until="domcontentloaded", timeout=60000)
print(f"Status: {resp.status}")
page.wait_for_timeout(5000)

# 1. 페이징 영역 전체 구조
print("\n=== 페이징 영역 ===")
paging = page.evaluate(r"""() => {
    // 페이징 컨테이너 탐색
    var selectors = [
        '.prev-next', '.pagination', '.Paging',
        '[class*="paging"]', '[class*="Paging"]', '[class*="page"]',
        '.board_paging', '.article_paging',
    ];

    var found = {};
    for (var i = 0; i < selectors.length; i++) {
        var els = document.querySelectorAll(selectors[i]);
        if (els.length > 0) {
            found[selectors[i]] = {
                count: els.length,
                html: els[0].outerHTML.substring(0, 500),
                text: els[0].textContent.trim().substring(0, 200),
            };
        }
    }

    // 숫자 페이지 링크 탐색
    var pageLinks = document.querySelectorAll('a[href*="page="], a[href*="search.page="]');
    var pageLinkInfo = [];
    for (var j = 0; j < pageLinks.length; j++) {
        var a = pageLinks[j];
        pageLinkInfo.push({
            text: a.textContent.trim(),
            href: (a.getAttribute('href') || '').substring(0, 200),
            classes: a.className.substring(0, 60),
        });
    }

    // 버튼 형태 페이징 탐색
    var pageButtons = document.querySelectorAll('button[class*="page"], button[class*="Page"]');
    var btnInfo = [];
    for (var k = 0; k < pageButtons.length; k++) {
        var btn = pageButtons[k];
        btnInfo.push({
            text: btn.textContent.trim(),
            classes: btn.className.substring(0, 80),
            disabled: btn.disabled,
        });
    }

    return {
        selectors: found,
        pageLinks: pageLinkInfo,
        pageButtons: btnInfo,
    };
}""")

print("셀렉터 매칭:")
for sel, info in paging.get("selectors", {}).items():
    print(f"  {sel}: count={info['count']}")
    print(f"    text: {info['text'][:100]}")
    print(f"    html: {info['html'][:200]}")

print(f"\n페이지 링크: {len(paging.get('pageLinks', []))}개")
for lnk in paging.get("pageLinks", [])[:10]:
    print(f"  [{lnk['text']}] href={lnk['href'][:100]} class={lnk['classes'][:40]}")

print(f"\n페이지 버튼: {len(paging.get('pageButtons', []))}개")
for btn in paging.get("pageButtons", [])[:10]:
    print(f"  [{btn['text']}] class={btn['classes'][:40]} disabled={btn['disabled']}")

# 2. 현재 URL의 쿼리 파라미터 분석
print("\n=== URL 파라미터 분석 ===")
print(f"현재 URL: {page.url}")

# 3. 2페이지 클릭 테스트
print("\n=== 2페이지 이동 테스트 ===")
page2_result = page.evaluate(r"""() => {
    // 페이지 2 링크 찾기
    var allLinks = document.querySelectorAll('a');
    for (var i = 0; i < allLinks.length; i++) {
        var a = allLinks[i];
        var text = a.textContent.trim();
        var href = a.getAttribute('href') || '';
        if (text === '2' && (href.indexOf('page') > -1 || href.indexOf('popular') > -1)) {
            return {
                found: true,
                text: text,
                href: href.substring(0, 300),
                classes: a.className.substring(0, 80),
                parentClasses: a.parentElement ? a.parentElement.className.substring(0, 80) : '',
            };
        }
    }

    // 숫자 2 텍스트를 가진 모든 클릭 가능 요소
    var clickables = document.querySelectorAll('a, button');
    var candidates = [];
    for (var j = 0; j < clickables.length; j++) {
        var el = clickables[j];
        var t = el.textContent.trim();
        if (t === '2') {
            candidates.push({
                tag: el.tagName,
                href: (el.getAttribute('href') || '').substring(0, 200),
                classes: el.className.substring(0, 80),
                parentTag: el.parentElement ? el.parentElement.tagName : '',
                parentClass: el.parentElement ? el.parentElement.className.substring(0, 60) : '',
            });
        }
    }
    return {found: false, candidates: candidates};
}""")
print(f"2페이지 링크 발견: {page2_result.get('found', False)}")
if page2_result.get('found'):
    print(f"  href: {page2_result['href'][:150]}")
    print(f"  class: {page2_result['classes']}")
    print(f"  parent: {page2_result['parentClasses']}")
else:
    print("  후보:")
    for c in page2_result.get('candidates', []):
        print(f"    {c['tag']}.{c['classes'][:30]} href={c.get('href','')[:80]}")
        print(f"    parent: {c['parentTag']}.{c['parentClass'][:30]}")

# 4. 실제로 2페이지 이동
print("\n=== 2페이지 실제 이동 ===")
if page2_result.get('found') and page2_result.get('href'):
    href2 = page2_result['href']
    if href2.startswith('/'):
        href2 = 'https://cafe.naver.com' + href2
    print(f"이동 URL: {href2}")
    resp2 = page.goto(href2, wait_until="domcontentloaded", timeout=60000)
    print(f"Status: {resp2.status}")
    page.wait_for_timeout(5000)

    # 2페이지 게시글 확인
    posts2 = page.evaluate(r"""() => {
        var links = document.querySelectorAll('a.article[href]');
        var results = [];
        for (var i = 0; i < links.length; i++) {
            var text = links[i].textContent.trim();
            if (text.length >= 3) {
                results.push(text.substring(0, 60));
            }
        }
        return results;
    }""")
    print(f"2페이지 게시글: {len(posts2)}개")
    for i, t in enumerate(posts2[:3]):
        try:
            t = t.encode('cp949', errors='replace').decode('cp949')
        except:
            pass
        print(f"  [{i}] {t}")

    # 마지막 페이지 번호 확인
    last_page = page.evaluate(r"""() => {
        var allLinks = document.querySelectorAll('a');
        var maxPage = 1;
        for (var i = 0; i < allLinks.length; i++) {
            var text = allLinks[i].textContent.trim();
            var num = parseInt(text);
            var href = allLinks[i].getAttribute('href') || '';
            if (!isNaN(num) && num > maxPage && href.indexOf('page') > -1) {
                maxPage = num;
            }
        }
        return maxPage;
    }""")
    print(f"\n현재 보이는 최대 페이지: {last_page}")

    # 날짜 패턴 확인
    print("\n=== 게시글 날짜 패턴 ===")
    dates = page.evaluate(r"""() => {
        var rows = document.querySelectorAll('tr, .inner_list, [class*="item"]');
        var dates = [];
        for (var i = 0; i < Math.min(rows.length, 5); i++) {
            var dateEl = rows[i].querySelector('.date, td:nth-child(3), [class*="date"]');
            if (dateEl) {
                dates.push(dateEl.textContent.trim());
            }
        }
        return dates;
    }""")
    for d in dates:
        try:
            d = d.encode('cp949', errors='replace').decode('cp949')
        except:
            pass
        print(f"  {d}")

bm.close()
print("\nDone!")
