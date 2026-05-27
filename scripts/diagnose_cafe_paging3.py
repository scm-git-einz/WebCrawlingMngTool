"""네이버 카페 인기글 - 정확한 페이징 URL 확인"""
import sys
import json
sys.path.insert(0, "D:\\crawling")
from core.browser import BrowserManager

bm = BrowserManager()
page = bm.create()

url = "https://cafe.naver.com/ca-fe/cafes/14538121/popular"
print(f"1) 1페이지 접속: {url}")
resp = page.goto(url, wait_until="domcontentloaded", timeout=60000)
print(f"   Status={resp.status}")
page.wait_for_timeout(5000)

# 1페이지 첫번째 게시글 제목
first_p1 = page.evaluate(r"""() => {
    var a = document.querySelector('a.article[href]');
    return a ? a.textContent.trim().substring(0, 60) : 'NOT FOUND';
}""")
print(f"   1페이지 첫 글: {first_p1}")

# 2) 버튼 클릭으로 2페이지 이동 후 URL 캡처
print("\n2) 2페이지 버튼 클릭...")
page.evaluate("performance.clearResourceTimings()")

click_result = page.evaluate(r"""() => {
    var container = document.querySelector('.ArticlePaginate, [class*="Paginate"]');
    if (!container) return {error: 'container not found'};
    var buttons = container.querySelectorAll('button');
    for (var i = 0; i < buttons.length; i++) {
        if (buttons[i].textContent.trim() === '2') {
            buttons[i].click();
            return {clicked: true};
        }
    }
    return {error: 'button 2 not found'};
}""")
print(f"   클릭: {click_result}")
page.wait_for_timeout(4000)

url_after_click = page.url
print(f"   클릭 후 URL: {url_after_click}")

# 2페이지 첫번째 게시글 제목
first_p2 = page.evaluate(r"""() => {
    var a = document.querySelector('a.article[href]');
    return a ? a.textContent.trim().substring(0, 60) : 'NOT FOUND';
}""")
print(f"   2페이지 첫 글: {first_p2}")
print(f"   1페이지와 다른가? {first_p1 != first_p2}")

# API 호출 확인
apis = page.evaluate(r"""() => {
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
            apis.push(name);
        }
    }
    return apis;
}""")
print(f"\n   클릭 후 API 호출 ({len(apis)}개):")
seen = set()
for api in apis:
    short = api.split('?')[0]
    if short not in seen:
        seen.add(short)
        print(f"     {api[:250]}")

# 3) 클릭 후 URL로 직접 접속 테스트
print(f"\n3) 클릭으로 얻은 URL로 직접 접속...")
resp2 = page.goto(url_after_click, wait_until="domcontentloaded", timeout=60000)
print(f"   Status={resp2.status}")
page.wait_for_timeout(5000)

first_direct = page.evaluate(r"""() => {
    var a = document.querySelector('a.article[href]');
    return a ? a.textContent.trim().substring(0, 60) : 'NOT FOUND';
}""")
print(f"   직접 접속 첫 글: {first_direct}")
print(f"   2페이지와 같은가? {first_p2 == first_direct}")
print(f"   1페이지와 같은가? {first_p1 == first_direct}")

# 4) 다양한 URL 패턴 테스트
print("\n4) URL 패턴 테스트:")
test_urls = [
    f"{url}?p=2",
    f"{url}?page=2",
    f"{url}?search.page=2",
]

for test_url in test_urls:
    try:
        resp3 = page.goto(test_url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)
        first_test = page.evaluate(r"""() => {
            var a = document.querySelector('a.article[href]');
            return a ? a.textContent.trim().substring(0, 60) : 'NOT FOUND';
        }""")
        final_url = page.url
        same_as_p1 = first_test == first_p1
        same_as_p2 = first_test == first_p2
        print(f"   {test_url}")
        print(f"     -> final URL: {final_url}")
        print(f"     -> 첫 글: {first_test}")
        print(f"     -> p1동일={same_as_p1}, p2동일={same_as_p2}")
    except Exception as e:
        print(f"   {test_url} -> ERROR: {e}")

bm.close()
print("\nDone!")
