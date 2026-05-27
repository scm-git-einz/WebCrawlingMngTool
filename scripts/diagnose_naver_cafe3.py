"""네이버 카페 - 개별 게시글 본문 구조 분석"""
import sys
import json
sys.path.insert(0, "D:\\crawling")
from core.browser import BrowserManager

bm = BrowserManager()
page = bm.create()

# 인기글 목록에서 게시글 URL 수집
list_url = "https://cafe.naver.com/ca-fe/cafes/14538121/popular"
print(f"1단계: 인기글 목록 접속")
resp = page.goto(list_url, wait_until="domcontentloaded", timeout=60000)
print(f"Status: {resp.status}")
page.wait_for_timeout(5000)

# 게시글 URL 수집
post_urls = page.evaluate(r"""() => {
    var links = document.querySelectorAll('a.article[href]');
    var urls = [];
    for (var i = 0; i < links.length; i++) {
        var href = links[i].getAttribute('href') || '';
        var text = links[i].textContent.trim();
        if (href.indexOf('/articles/') > -1 && text.length >= 5) {
            var fullUrl = href;
            if (href.indexOf('http') !== 0) {
                fullUrl = 'https://cafe.naver.com' + href;
            }
            urls.push({url: fullUrl, title: text.substring(0, 80)});
        }
    }
    return urls;
}""")
print(f"게시글 {len(post_urls)}개 발견")
for i, p in enumerate(post_urls[:5]):
    try:
        t = p['title'].encode('cp949', errors='replace').decode('cp949')
    except:
        t = p['title']
    print(f"  [{i}] {t}")
    print(f"      {p['url'][:120]}")

if not post_urls:
    print("게시글 없음 - 종료")
    bm.close()
    sys.exit()

# 첫 번째 게시글 상세 접속
article_url = post_urls[0]['url']
print(f"\n2단계: 게시글 상세 접속")
print(f"URL: {article_url}")
resp2 = page.goto(article_url, wait_until="domcontentloaded", timeout=60000)
print(f"Status: {resp2.status}")
print(f"Final URL: {page.url}")
page.wait_for_timeout(5000)

# 본문 텍스트
print("\n=== 본문 텍스트 ===")
body_text = page.evaluate("""() => {
    // 네이버 카페 본문 셀렉터
    var selectors = [
        '.se-main-container',   // 스마트에디터
        '.ContentRenderer',     // 새 에디터
        '#body', '.article_viewer', '.content_view',
        '.ArticleContentBox',
        '[class*="article_content"]', '[class*="article_body"]',
        '[class*="content"]',
        'article',
    ];

    for (var i = 0; i < selectors.length; i++) {
        var el = document.querySelector(selectors[i]);
        if (el) {
            var text = el.innerText.trim();
            if (text.length > 30) {
                return {
                    selector: selectors[i],
                    text: text.substring(0, 2000),
                    html: el.innerHTML.substring(0, 1000),
                    length: text.length,
                };
            }
        }
    }

    return {
        selector: 'body (fallback)',
        text: document.body.innerText.substring(0, 2000),
        html: '',
        length: document.body.innerText.length,
    };
}""")
print(f"셀렉터: {body_text['selector']}")
print(f"텍스트 길이: {body_text['length']}자")
try:
    t = body_text['text'][:600].encode('cp949', errors='replace').decode('cp949')
except:
    t = body_text['text'][:600]
print(f"본문:\n{t}")

# 본문 내 링크 (상품 링크 가능성)
print("\n=== 본문 내 링크 ===")
body_links = page.evaluate("""() => {
    var selectors = [
        '.se-main-container', '.ContentRenderer',
        '.article_viewer', '.content_view',
        '[class*="article_content"]', '[class*="content"]',
        'article',
    ];

    var container = null;
    for (var i = 0; i < selectors.length; i++) {
        var el = document.querySelector(selectors[i]);
        if (el && el.innerText.trim().length > 30) {
            container = el;
            break;
        }
    }
    if (!container) container = document.body;

    var links = container.querySelectorAll('a[href]');
    var results = [];
    for (var j = 0; j < links.length; j++) {
        var a = links[j];
        var href = a.getAttribute('href') || '';
        var text = a.textContent.trim();
        if (href && href !== '#') {
            results.push({
                text: text.substring(0, 100),
                href: href.substring(0, 200),
            });
        }
    }
    return results;
}""")
print(f"본문 내 링크: {len(body_links)}개")
for i, lnk in enumerate(body_links[:10]):
    try:
        t = lnk['text'][:50].encode('cp949', errors='replace').decode('cp949')
    except:
        t = lnk['text'][:50]
    print(f"  [{i}] {t}")
    print(f"      href: {lnk['href'][:120]}")

# 본문 내 이미지 (상품 이미지)
print("\n=== 본문 내 이미지 ===")
images = page.evaluate("""() => {
    var selectors = [
        '.se-main-container', '.ContentRenderer',
        '.article_viewer', '.content_view',
        '[class*="article_content"]', '[class*="content"]',
    ];

    var container = null;
    for (var i = 0; i < selectors.length; i++) {
        var el = document.querySelector(selectors[i]);
        if (el && el.innerText.trim().length > 30) {
            container = el;
            break;
        }
    }
    if (!container) container = document.body;

    var imgs = container.querySelectorAll('img');
    var results = [];
    for (var j = 0; j < imgs.length; j++) {
        var img = imgs[j];
        results.push({
            src: (img.getAttribute('src') || '').substring(0, 200),
            alt: (img.getAttribute('alt') || '').substring(0, 100),
            width: img.naturalWidth || img.width,
            height: img.naturalHeight || img.height,
        });
    }
    return results;
}""")
print(f"이미지: {len(images)}개")
for i, img in enumerate(images[:5]):
    print(f"  [{i}] alt='{img['alt']}' size={img['width']}x{img['height']}")
    print(f"      src: {img['src'][:100]}")

# 게시글 메타 정보 (제목, 작성자, 날짜 등)
print("\n=== 게시글 메타 정보 ===")
meta = page.evaluate("""() => {
    // 제목
    var titleEl = document.querySelector(
        '.title_text, .art_tit, h3.title_text, [class*="article_title"],'
        + ' [class*="subject"], h2, h3'
    );
    var title = titleEl ? titleEl.innerText.trim() : '';

    // 작성자
    var authorEl = document.querySelector(
        '.nickname, .nick, [class*="nickname"], [class*="author"]'
    );
    var author = authorEl ? authorEl.innerText.trim() : '';

    // 날짜
    var dateEl = document.querySelector(
        '.date, time, [class*="date"], [class*="time"]'
    );
    var date = dateEl ? dateEl.textContent.trim() : '';

    // 조회수
    var viewEl = document.querySelector(
        '.count, [class*="view"], [class*="hit"]'
    );
    var views = viewEl ? viewEl.textContent.trim() : '';

    // 카테고리
    var catEl = document.querySelector(
        '.board_name, [class*="category"], [class*="board"]'
    );
    var category = catEl ? catEl.textContent.trim() : '';

    return {
        title: title.substring(0, 200),
        author: author.substring(0, 50),
        date: date.substring(0, 50),
        views: views.substring(0, 30),
        category: category.substring(0, 50),
    };
}""")
for k, v in meta.items():
    try:
        val = v.encode('cp949', errors='replace').decode('cp949')
    except:
        val = v
    print(f"  {k}: {val}")

# GraphQL API 확인
print("\n=== GraphQL API 분석 ===")
apis = page.evaluate("""() => {
    var entries = performance.getEntriesByType('resource');
    var apis = [];
    for (var i = 0; i < entries.length; i++) {
        var name = entries[i].name;
        if (name.indexOf('.js') > -1 || name.indexOf('.css') > -1
            || name.indexOf('.png') > -1 || name.indexOf('.woff') > -1
            || name.indexOf('.gif') > -1 || name.indexOf('.svg') > -1
            || name.indexOf('.ico') > -1 || name.indexOf('pstatic') > -1) continue;
        if (name.indexOf('api') > -1 || name.indexOf('graphql') > -1
            || name.indexOf('article') > -1 || name.indexOf('cafe') > -1) {
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

# 두 번째 게시글도 확인 (다른 패턴의 상품 정보)
if len(post_urls) >= 2:
    print(f"\n\n{'='*60}")
    print(f"3단계: 두 번째 게시글 확인")
    article_url2 = post_urls[1]['url']
    print(f"URL: {article_url2}")
    resp3 = page.goto(article_url2, wait_until="domcontentloaded", timeout=60000)
    print(f"Status: {resp3.status}")
    page.wait_for_timeout(5000)

    body2 = page.evaluate("""() => {
        var selectors = [
            '.se-main-container', '.ContentRenderer',
            '.article_viewer', '.content_view',
            '[class*="article_content"]', '[class*="content"]',
        ];
        for (var i = 0; i < selectors.length; i++) {
            var el = document.querySelector(selectors[i]);
            if (el && el.innerText.trim().length > 30) {
                return {selector: selectors[i], text: el.innerText.trim().substring(0, 1500)};
            }
        }
        return {selector: 'fallback', text: document.body.innerText.substring(0, 1500)};
    }""")
    try:
        t = body2['text'][:500].encode('cp949', errors='replace').decode('cp949')
    except:
        t = body2['text'][:500]
    print(f"셀렉터: {body2['selector']}")
    print(f"본문:\n{t}")

bm.close()
print("\nDone!")
