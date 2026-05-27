"""네이버 카페 (꼬냑클럽) 인기글 페이지 구조 분석"""
import sys
import json
sys.path.insert(0, "D:\\crawling")
from core.browser import BrowserManager

bm = BrowserManager()
page = bm.create()

url = "https://cafe.naver.com/f-e/cafes/14538121/popular"
print(f"접속 URL: {url}")
resp = page.goto(url, wait_until="domcontentloaded", timeout=60000)
print(f"Status: {resp.status}")
print(f"Final URL: {page.url}")
page.wait_for_timeout(5000)

# 스크롤
for _ in range(3):
    page.evaluate("window.scrollBy(0, window.innerHeight)")
    page.wait_for_timeout(1500)

# 1. 페이지 기본 정보
print("\n=== 페이지 기본 정보 ===")
page_info = page.evaluate("""() => {
    return {
        title: document.title,
        url: location.href,
        bodyClasses: document.body.className.substring(0, 200),
        hasIframe: !!document.querySelector('iframe'),
        iframeCount: document.querySelectorAll('iframe').length,
        iframeSrcs: Array.from(document.querySelectorAll('iframe')).map(f => (f.src || '').substring(0, 150)),
    };
}""")
for k, v in page_info.items():
    print(f"  {k}: {v}")

# 2. 로그인 필요 여부 확인
print("\n=== 로그인 상태 확인 ===")
login_check = page.evaluate("""() => {
    var loginBtn = document.querySelector('.gnb_btn_login, .btn_login, [class*="login"]');
    var loginText = document.body.innerText.indexOf('로그인') > -1;
    var restrictText = document.body.innerText.indexOf('카페 멤버') > -1
        || document.body.innerText.indexOf('가입') > -1;
    return {
        hasLoginButton: !!loginBtn,
        hasLoginText: loginText,
        hasRestriction: restrictText,
        bodyTextPreview: document.body.innerText.substring(0, 500),
    };
}""")
for k, v in login_check.items():
    if k == 'bodyTextPreview':
        print(f"  {k}: {str(v)[:200]}...")
    else:
        print(f"  {k}: {v}")

# 3. 게시글 목록 구조 탐색
print("\n=== 게시글 목록 구조 ===")
list_structure = page.evaluate("""() => {
    // 다양한 컨테이너 패턴
    var selectors = [
        '.article-board', '.board-list', '.article_lst',
        '[class*="article"]', '[class*="post"]', '[class*="board"]',
        '[class*="list"]', '.cafe-menu-list',
        'ul li a', 'table tbody tr',
    ];

    var found = {};
    for (var i = 0; i < selectors.length; i++) {
        var els = document.querySelectorAll(selectors[i]);
        if (els.length > 0) {
            found[selectors[i]] = els.length;
        }
    }

    // 모든 링크 중 게시글 패턴
    var allLinks = document.querySelectorAll('a[href]');
    var postLinks = [];
    var linkPatterns = {};
    for (var j = 0; j < allLinks.length; j++) {
        var href = allLinks[j].getAttribute('href') || '';
        var text = allLinks[j].textContent.trim();

        // URL 패턴 분류
        if (href.indexOf('/articles/') > -1 || href.indexOf('articleid=') > -1
            || href.indexOf('/ArticleRead') > -1) {
            postLinks.push({
                text: text.substring(0, 80),
                href: href.substring(0, 150),
                classes: allLinks[j].className.substring(0, 60),
            });
        }

        // 패턴 수집
        var match = href.match(/cafe\.naver\.com\/([^\/\?]+)/);
        if (match) {
            var pattern = match[0];
            linkPatterns[pattern] = (linkPatterns[pattern] || 0) + 1;
        }
    }

    return {
        selectorMatches: found,
        postLinkCount: postLinks.length,
        postLinks: postLinks.slice(0, 10),
        linkPatterns: linkPatterns,
    };
}""")
print(f"  셀렉터 매칭: {json.dumps(list_structure['selectorMatches'], indent=2)}")
print(f"  게시글 링크: {list_structure['postLinkCount']}개")
for i, link in enumerate(list_structure['postLinks'][:5]):
    print(f"    [{i}] {link['text'][:50]}")
    print(f"        href: {link['href'][:100]}")
    print(f"        class: {link['classes'][:40]}")

# 4. 주요 DOM 구조 (직계 자식 탐색)
print("\n=== 주요 DOM 구조 ===")
dom_tree = page.evaluate("""() => {
    function getTree(el, depth) {
        if (depth > 3) return null;
        var children = el.children;
        var result = [];
        for (var i = 0; i < Math.min(children.length, 10); i++) {
            var ch = children[i];
            var text = '';
            for (var k = 0; k < ch.childNodes.length; k++) {
                if (ch.childNodes[k].nodeType === 3) {
                    text += ch.childNodes[k].textContent.trim();
                }
            }
            var info = {
                tag: ch.tagName,
                id: (ch.id || '').substring(0, 30),
                classes: ch.className.substring(0, 60),
                text: text.substring(0, 50),
            };
            if (ch.children.length > 0 && depth < 3) {
                info.children = getTree(ch, depth + 1);
            }
            result.push(info);
        }
        return result;
    }

    var main = document.querySelector('main, #app, #__next, .content, #content, #container');
    if (!main) main = document.body;
    return {
        root: main.tagName + '.' + main.className.substring(0, 40),
        tree: getTree(main, 0)
    };
}""")
print(f"  Root: {dom_tree['root']}")

def print_tree(nodes, indent=2):
    if not nodes:
        return
    for n in nodes[:8]:
        prefix = " " * indent
        tag = n['tag']
        cls = n.get('classes', '')[:30]
        nid = n.get('id', '')
        text = n.get('text', '')[:40]
        id_str = f"#{nid}" if nid else ""
        cls_str = f".{cls}" if cls else ""
        text_str = f" -> '{text}'" if text else ""
        print(f"{prefix}{tag}{id_str}{cls_str}{text_str}")
        if 'children' in n and n['children']:
            print_tree(n['children'], indent + 2)

print_tree(dom_tree.get('tree', []))

# 5. 네트워크 API 패턴
print("\n=== API 엔드포인트 ===")
apis = page.evaluate("""() => {
    var entries = performance.getEntriesByType('resource');
    var apis = [];
    for (var i = 0; i < entries.length; i++) {
        var name = entries[i].name;
        if ((name.indexOf('/api/') > -1 || name.indexOf('cafe') > -1)
            && name.indexOf('.js') === -1
            && name.indexOf('.css') === -1
            && name.indexOf('.png') === -1
            && name.indexOf('.woff') === -1) {
            apis.push(name.substring(0, 250));
        }
    }
    return apis;
}""")
seen = set()
for api in apis[:20]:
    short = api.split('?')[0] if '?' in api else api
    if short not in seen:
        seen.add(short)
        print(f"  {api[:150]}")

# 6. 현재 보이는 텍스트 콘텐츠 분석
print("\n=== 페이지 텍스트 (상위 500자) ===")
text_preview = page.evaluate("""() => {
    var main = document.querySelector('main, #app, #content, .content');
    if (!main) main = document.body;
    return main.innerText.substring(0, 800);
}""")
print(text_preview[:500])

bm.close()
print("\nDone!")
