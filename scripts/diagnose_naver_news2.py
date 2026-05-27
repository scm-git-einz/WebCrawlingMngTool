"""네이버 뉴스 검색 - 기사 카드 상세 구조 분석"""
import sys
import json
sys.path.insert(0, "D:\\crawling")
from core.browser import BrowserManager

bm = BrowserManager()
page = bm.create()

url = "https://search.naver.com/search.naver?where=news&query=%ED%95%B4%EC%99%B8%EC%97%AC%ED%96%89&sort=1"
resp = page.goto(url, wait_until="domcontentloaded", timeout=60000)
print(f"Status: {resp.status}")
page.wait_for_timeout(5000)

# 스크롤
for _ in range(3):
    page.evaluate("window.scrollBy(0, window.innerHeight)")
    page.wait_for_timeout(1000)

# 1. .list_news 또는 .group_news 내부 구조
print("\n=== .list_news / .group_news 내부 ===")
inner = page.evaluate("""() => {
    var container = document.querySelector('.list_news') || document.querySelector('.group_news');
    if (!container) return {error: 'container not found'};

    // 직계 자식 분석
    var children = container.children;
    var childInfo = [];
    for (var i = 0; i < Math.min(children.length, 10); i++) {
        childInfo.push({
            tag: children[i].tagName,
            classes: children[i].className.substring(0, 120),
            childCount: children[i].children.length,
            text: children[i].textContent.trim().substring(0, 100)
        });
    }

    return {
        containerTag: container.tagName,
        containerClass: container.className.substring(0, 100),
        childCount: children.length,
        children: childInfo
    };
}""")
print(f"Container: {inner.get('containerTag')} class='{inner.get('containerClass')}'")
print(f"Children: {inner.get('childCount')}개")
for i, ch in enumerate(inner.get('children', [])):
    print(f"  [{i}] {ch['tag']} class='{ch['classes'][:60]}' children={ch['childCount']}")
    print(f"      text: {ch['text'][:70]}")

# 2. 뉴스 기사를 포함하는 <a> 태그 전체 검색 (naver.com/mnews 또는 news.naver)
print("\n\n=== 뉴스 링크 a 태그 ===")
news_links = page.evaluate("""() => {
    var allLinks = document.querySelectorAll('a[href*="news.naver"], a[href*="n.news"], a[href*="mnews"]');
    var results = [];
    var seen = {};
    for (var i = 0; i < allLinks.length; i++) {
        var a = allLinks[i];
        var href = a.getAttribute('href') || '';
        var text = a.textContent.trim();
        if (text.length < 5 || text.length > 200) continue;
        if (seen[href]) continue;
        seen[href] = true;

        // 부모 요소 탐색
        var parent = a.parentElement;
        var grandparent = parent ? parent.parentElement : null;

        results.push({
            text: text.substring(0, 100),
            href: href.substring(0, 150),
            classes: a.className.substring(0, 80),
            tag: a.tagName,
            parentTag: parent ? parent.tagName : '',
            parentClass: parent ? parent.className.substring(0, 80) : '',
            grandparentTag: grandparent ? grandparent.tagName : '',
            grandparentClass: grandparent ? grandparent.className.substring(0, 80) : '',
        });
    }
    return results;
}""")
print(f"뉴스 링크: {len(news_links)}개")
for i, link in enumerate(news_links[:10]):
    print(f"\n  [{i}] {link['text'][:60]}")
    print(f"    href: {link['href'][:100]}")
    print(f"    a.class: {link['classes'][:60]}")
    print(f"    parent: {link['parentTag']}.{link['parentClass'][:40]}")
    print(f"    gparent: {link['grandparentTag']}.{link['grandparentClass'][:40]}")

# 3. 기사 제목 링크의 부모 카드 구조 분석
print("\n\n=== 기사 카드 전체 구조 (첫 번째 기사) ===")
card_detail = page.evaluate("""() => {
    // 기사 링크 중 가장 긴 텍스트를 가진 것이 제목 링크
    var allLinks = document.querySelectorAll('a[href*="news.naver"], a[href*="n.news"], a[href*="mnews"]');
    var titleLink = null;
    for (var i = 0; i < allLinks.length; i++) {
        var text = allLinks[i].textContent.trim();
        if (text.length >= 10 && text.length <= 200) {
            titleLink = allLinks[i];
            break;
        }
    }
    if (!titleLink) return {error: 'title link not found'};

    // 상위 카드 컨테이너 탐색 (li, div, article 중 가장 가까운 것)
    var card = titleLink.closest('li, div[class], article');
    if (!card) card = titleLink.parentElement.parentElement;

    // 카드 내부 전체 요소 덤프
    var allEls = card.querySelectorAll('*');
    var dump = [];
    for (var j = 0; j < allEls.length; j++) {
        var el = allEls[j];
        var elText = el.textContent.trim().substring(0, 80);
        // 직접 텍스트만 (자식 제외)
        var directText = '';
        for (var k = 0; k < el.childNodes.length; k++) {
            if (el.childNodes[k].nodeType === 3) {
                directText += el.childNodes[k].textContent.trim();
            }
        }
        if (directText.length === 0 && el.children.length > 0) continue; // 래퍼만 있는 요소 스킵

        dump.push({
            tag: el.tagName,
            classes: el.className.substring(0, 60),
            href: el.getAttribute('href') || '',
            directText: directText.substring(0, 80),
            attrs: el.getAttribute('data-cr') || el.getAttribute('data-gdid') || ''
        });
    }

    return {
        cardTag: card.tagName,
        cardClass: card.className.substring(0, 100),
        cardOuterHTML: card.outerHTML.substring(0, 500),
        elements: dump.slice(0, 30)
    };
}""")

if 'error' not in card_detail:
    print(f"Card: {card_detail['cardTag']} class='{card_detail['cardClass'][:60]}'")
    print(f"\nElements:")
    for el in card_detail['elements']:
        prefix = f"  {el['tag']}"
        if el['classes']:
            prefix += f".{el['classes'][:30]}"
        if el['href']:
            prefix += f" href='{el['href'][:50]}'"
        text = el['directText'][:50] if el['directText'] else ''
        print(f"{prefix} → '{text}'")

    print(f"\nHTML preview:\n{card_detail['cardOuterHTML'][:400]}")
else:
    print(card_detail)

# 4. 네이버 뉴스 API 확인
print("\n\n=== Performance API entries (news 관련) ===")
apis = page.evaluate("""() => {
    var entries = performance.getEntriesByType('resource');
    var apis = [];
    for (var i = 0; i < entries.length; i++) {
        var name = entries[i].name;
        if (name.indexOf('/api/') > -1 || name.indexOf('openapi') > -1 || name.indexOf('/search') > -1) {
            if (name.indexOf('.js') === -1 && name.indexOf('.css') === -1) {
                apis.push(name.substring(0, 200));
            }
        }
    }
    return apis;
}""")
for api in apis[:15]:
    print(f"  {api}")

bm.close()
print("\nDone!")
