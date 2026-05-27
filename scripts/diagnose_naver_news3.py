"""네이버 뉴스 검색 - ._slog_visible 카드 상세 구조"""
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
    page.wait_for_timeout(1500)

# ._slog_visible 카드의 내부 전체 구조 덤프
print("\n=== ._slog_visible 카드 구조 ===")
card_dump = page.evaluate("""() => {
    var cards = document.querySelectorAll('._slog_visible');
    if (cards.length === 0) return {error: 'no cards'};

    var results = [];
    for (var ci = 0; ci < Math.min(cards.length, 3); ci++) {
        var card = cards[ci];

        // 모든 a 태그
        var links = card.querySelectorAll('a[href]');
        var linkInfo = [];
        for (var i = 0; i < links.length; i++) {
            var a = links[i];
            var text = a.textContent.trim();
            linkInfo.push({
                text: text.substring(0, 100),
                href: (a.getAttribute('href') || '').substring(0, 150),
                classes: a.className.substring(0, 80),
                parentClasses: a.parentElement ? a.parentElement.className.substring(0, 80) : '',
            });
        }

        // 모든 텍스트 노드가 있는 leaf 요소
        var leafEls = card.querySelectorAll('span, div, p, a, strong, em, time, h2, h3');
        var leafInfo = [];
        for (var j = 0; j < leafEls.length; j++) {
            var el = leafEls[j];
            // 직접 텍스트만
            var directText = '';
            for (var k = 0; k < el.childNodes.length; k++) {
                if (el.childNodes[k].nodeType === 3) {
                    directText += el.childNodes[k].textContent;
                }
            }
            directText = directText.trim();
            if (directText.length > 0 && directText.length < 200) {
                leafInfo.push({
                    tag: el.tagName,
                    classes: el.className.substring(0, 80),
                    text: directText.substring(0, 100),
                    parentTag: el.parentElement ? el.parentElement.tagName : '',
                    parentClass: el.parentElement ? el.parentElement.className.substring(0, 50) : '',
                });
            }
        }

        // 이미지
        var imgs = card.querySelectorAll('img');
        var imgInfo = [];
        for (var m = 0; m < imgs.length; m++) {
            imgInfo.push({
                src: (imgs[m].getAttribute('src') || '').substring(0, 100),
                alt: (imgs[m].getAttribute('alt') || '').substring(0, 50),
            });
        }

        results.push({
            classes: card.className.substring(0, 80),
            links: linkInfo,
            leaves: leafInfo,
            images: imgInfo,
        });
    }

    return {count: cards.length, cards: results};
}""")

print(f"총 카드 수: {card_dump.get('count', 0)}")
for ci, card in enumerate(card_dump.get('cards', [])):
    print(f"\n{'='*60}")
    print(f"카드 [{ci}] class='{card['classes']}'")

    print(f"\n  Links ({len(card['links'])}):")
    for link in card['links']:
        print(f"    class='{link['classes'][:40]}'")
        print(f"    parent='{link['parentClasses'][:40]}'")
        print(f"    text: {link['text'][:60]}")
        print(f"    href: {link['href'][:80]}")
        print()

    print(f"  Leaf texts ({len(card['leaves'])}):")
    for leaf in card['leaves']:
        print(f"    {leaf['tag']}.{leaf['classes'][:30]} → '{leaf['text'][:60]}'")

    if card['images']:
        print(f"  Images ({len(card['images'])}):")
        for img in card['images'][:2]:
            print(f"    alt='{img['alt']}' src='{img['src'][:60]}'")

bm.close()
print("\nDone!")
