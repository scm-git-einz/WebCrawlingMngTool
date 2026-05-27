"""네이버 카페 인기글 - 페이징 클릭 + API 분석"""
import sys
import json
sys.path.insert(0, "D:\\crawling")
from core.browser import BrowserManager

bm = BrowserManager()
page = bm.create()

url = "https://cafe.naver.com/ca-fe/cafes/14538121/popular"
resp = page.goto(url, wait_until="domcontentloaded", timeout=60000)
print(f"1페이지 접속: Status={resp.status}")
page.wait_for_timeout(5000)

# 1. ArticlePaginate 내부 전체 구조
print("\n=== ArticlePaginate 구조 ===")
paging_struct = page.evaluate(r"""() => {
    var container = document.querySelector('.ArticlePaginate, [class*="Paginate"]');
    if (!container) return {error: 'not found'};

    var buttons = container.querySelectorAll('button');
    var btnList = [];
    for (var i = 0; i < buttons.length; i++) {
        var btn = buttons[i];
        btnList.push({
            text: btn.textContent.trim().substring(0, 20),
            classes: btn.className.substring(0, 80),
            disabled: btn.disabled,
            ariaLabel: (btn.getAttribute('aria-label') || '').substring(0, 50),
            dataPage: btn.getAttribute('data-page') || '',
            onclick: btn.getAttribute('onclick') || '',
        });
    }

    return {
        containerClass: container.className.substring(0, 100),
        containerHTML: container.outerHTML.substring(0, 800),
        buttons: btnList,
    };
}""")

if 'error' not in paging_struct:
    print(f"Container: {paging_struct['containerClass']}")
    print(f"Buttons ({len(paging_struct['buttons'])}개):")
    for btn in paging_struct['buttons']:
        print(f"  [{btn['text']}] class='{btn['classes'][:40]}' "
              f"disabled={btn['disabled']} aria='{btn['ariaLabel']}'")
    print(f"\nHTML:\n{paging_struct['containerHTML'][:500]}")
else:
    print(paging_struct)

# 2. 2페이지 버튼 클릭 + URL/API 변화 관찰
print("\n=== 2페이지 버튼 클릭 ===")

# 클릭 전 URL 기록
url_before = page.url

# performance entries 초기화
page.evaluate("performance.clearResourceTimings()")

# 2번 버튼 클릭
clicked = page.evaluate(r"""() => {
    var container = document.querySelector('.ArticlePaginate, [class*="Paginate"]');
    if (!container) return {error: 'no container'};

    var buttons = container.querySelectorAll('button');
    for (var i = 0; i < buttons.length; i++) {
        var text = buttons[i].textContent.trim();
        if (text === '2') {
            buttons[i].click();
            return {clicked: true, text: text, classes: buttons[i].className};
        }
    }
    return {error: 'button 2 not found'};
}""")
print(f"클릭 결과: {clicked}")

# 페이지 변화 대기
page.wait_for_timeout(3000)

# URL 변화 확인
url_after = page.url
print(f"URL 변화: {url_before != url_after}")
print(f"  before: {url_before}")
print(f"  after:  {url_after}")

# 새로운 API 호출 확인
print("\n=== 2페이지 API 호출 ===")
apis = page.evaluate("""() => {
    var entries = performance.getEntriesByType('resource');
    var apis = [];
    for (var i = 0; i < entries.length; i++) {
        var name = entries[i].name;
        if (name.indexOf('.js') > -1 || name.indexOf('.css') > -1
            || name.indexOf('.png') > -1 || name.indexOf('.woff') > -1
            || name.indexOf('.gif') > -1 || name.indexOf('.svg') > -1
            || name.indexOf('pstatic') > -1) continue;
        if (name.indexOf('popular') > -1 || name.indexOf('article') > -1
            || name.indexOf('page') > -1 || name.indexOf('api') > -1
            || name.indexOf('graphql') > -1 || name.indexOf('cafe') > -1) {
            apis.push(name.substring(0, 300));
        }
    }
    return apis;
}""")
seen = set()
for api in apis:
    short = api.split('?')[0]
    if short not in seen:
        seen.add(short)
        print(f"  {api[:200]}")

# 2페이지 게시글 확인
print("\n=== 2페이지 게시글 ===")
posts2 = page.evaluate(r"""() => {
    var links = document.querySelectorAll('a.article[href]');
    var results = [];
    for (var i = 0; i < links.length; i++) {
        var a = links[i];
        var text = a.textContent.trim();
        if (text.length < 3) continue;

        var row = a.closest('tr, .inner_list, [class*="item"]');
        var date = '';
        if (row) {
            var dateEl = row.querySelector('.date, td:nth-child(3)');
            if (dateEl) date = dateEl.textContent.trim();
        }

        results.push({
            text: text.substring(0, 60),
            date: date,
        });
    }
    return results;
}""")
print(f"2페이지 게시글: {len(posts2)}개")
for i, p in enumerate(posts2[:5]):
    try:
        t = p['text'].encode('cp949', errors='replace').decode('cp949')
    except:
        t = p['text']
    print(f"  [{i}] {t} | {p['date']}")

# 3. 마지막 페이지 확인 (다음 그룹 버튼으로 이동)
print("\n=== 페이지 네비게이션 구조 ===")
nav_info = page.evaluate(r"""() => {
    var container = document.querySelector('.ArticlePaginate, [class*="Paginate"]');
    if (!container) return {};

    var buttons = container.querySelectorAll('button');
    var info = {totalButtons: buttons.length, pages: [], navigation: []};

    for (var i = 0; i < buttons.length; i++) {
        var btn = buttons[i];
        var text = btn.textContent.trim();
        var num = parseInt(text);
        if (!isNaN(num)) {
            info.pages.push(num);
        } else {
            info.navigation.push({
                text: text.substring(0, 20),
                classes: btn.className.substring(0, 60),
                disabled: btn.disabled,
            });
        }
    }
    return info;
}""")
print(f"총 버튼: {nav_info.get('totalButtons', 0)}")
print(f"페이지 번호: {nav_info.get('pages', [])}")
print(f"네비게이션 버튼:")
for nav in nav_info.get('navigation', []):
    print(f"  [{nav['text']}] class='{nav['classes'][:40]}' disabled={nav['disabled']}")

bm.close()
print("\nDone!")
