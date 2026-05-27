"""네이버 카페 - iframe 내부 + API 분석"""
import sys
import json
sys.path.insert(0, "D:\\crawling")
from core.browser import BrowserManager

bm = BrowserManager()
page = bm.create()

# 방법 1: iframe URL 직접 접속
iframe_url = "https://cafe.naver.com/ca-fe/cafes/14538121/popular"
print(f"=== iframe URL 직접 접속 ===")
print(f"URL: {iframe_url}")
resp = page.goto(iframe_url, wait_until="domcontentloaded", timeout=60000)
print(f"Status: {resp.status}")
print(f"Final URL: {page.url}")
page.wait_for_timeout(5000)

# 스크롤
for _ in range(3):
    page.evaluate("window.scrollBy(0, window.innerHeight)")
    page.wait_for_timeout(1500)

# 페이지 텍스트 확인
print("\n=== 페이지 텍스트 ===")
text = page.evaluate("""() => {
    return document.body.innerText.substring(0, 1500);
}""")
# cp949 안전 출력
try:
    print(text[:800].encode('cp949', errors='replace').decode('cp949'))
except:
    print(text[:800])

# 게시글 링크 탐색
print("\n=== 게시글 링크 ===")
links = page.evaluate(r"""() => {
    var allLinks = document.querySelectorAll('a[href]');
    var postLinks = [];
    for (var i = 0; i < allLinks.length; i++) {
        var a = allLinks[i];
        var href = a.getAttribute('href') || '';
        var text = a.textContent.trim();
        if (text.length < 5) continue;
        // 게시글 패턴
        if (href.indexOf('/articles/') > -1
            || href.indexOf('articleid') > -1
            || /\/\d{5,}/.test(href)) {
            postLinks.push({
                text: text.substring(0, 80),
                href: href.substring(0, 200),
                classes: a.className.substring(0, 60),
                parentTag: a.parentElement ? a.parentElement.tagName : '',
                parentClass: a.parentElement ? a.parentElement.className.substring(0, 60) : '',
            });
        }
    }
    return {total: allLinks.length, posts: postLinks};
}""")
print(f"총 링크: {links['total']}개, 게시글 링크: {len(links['posts'])}개")
for i, lnk in enumerate(links['posts'][:10]):
    try:
        t = lnk['text'][:50].encode('cp949', errors='replace').decode('cp949')
    except:
        t = lnk['text'][:50]
    print(f"  [{i}] {t}")
    print(f"      href: {lnk['href'][:120]}")
    print(f"      a.class: {lnk['classes'][:40]}")
    print(f"      parent: {lnk['parentTag']}.{lnk['parentClass'][:30]}")

# API 엔드포인트
print("\n=== API 엔드포인트 ===")
apis = page.evaluate("""() => {
    var entries = performance.getEntriesByType('resource');
    var apis = [];
    for (var i = 0; i < entries.length; i++) {
        var name = entries[i].name;
        if (name.indexOf('.js') > -1 || name.indexOf('.css') > -1
            || name.indexOf('.png') > -1 || name.indexOf('.woff') > -1
            || name.indexOf('.gif') > -1 || name.indexOf('.svg') > -1
            || name.indexOf('.ico') > -1) continue;
        if (name.indexOf('api') > -1 || name.indexOf('/v1') > -1
            || name.indexOf('/v2') > -1 || name.indexOf('/v3') > -1
            || name.indexOf('popular') > -1 || name.indexOf('article') > -1
            || name.indexOf('cafe') > -1) {
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

# DOM 구조 (주요 컨테이너)
print("\n=== 주요 컨테이너 ===")
containers = page.evaluate("""() => {
    var selectors = [
        '#app', '#__next', '#content', 'main',
        '[class*="popular"]', '[class*="article"]', '[class*="post"]',
        '[class*="board"]', '[class*="list"]', '[class*="card"]',
        '[class*="item"]', '[class*="feed"]',
        'ul', 'ol', 'table',
    ];
    var found = {};
    for (var i = 0; i < selectors.length; i++) {
        var els = document.querySelectorAll(selectors[i]);
        if (els.length > 0) {
            var sample = els[0];
            found[selectors[i]] = {
                count: els.length,
                tag: sample.tagName,
                id: (sample.id || '').substring(0, 30),
                classes: sample.className.substring(0, 80),
                childCount: sample.children.length,
                text: sample.textContent.trim().substring(0, 80),
            };
        }
    }
    return found;
}""")
for sel, info in containers.items():
    print(f"  {sel}: count={info['count']}, tag={info['tag']}, "
          f"class='{info['classes'][:40]}', children={info['childCount']}")

bm.close()
print("\nDone!")
