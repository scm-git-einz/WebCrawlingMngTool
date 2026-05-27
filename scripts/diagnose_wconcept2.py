"""W Concept DOM 필드 구조 분석"""
import sys
import json
sys.path.insert(0, "D:\\crawling")
from core.browser import BrowserManager

bm = BrowserManager()
page = bm.create()

url = "https://www.wconcept.co.kr/Women"
print(f"[diag] Loading: {url}")
page.goto(url, wait_until="domcontentloaded", timeout=60000)
page.wait_for_timeout(8000)

# 스크롤
for i in range(3):
    page.evaluate("window.scrollBy(0, window.innerHeight)")
    page.wait_for_timeout(1500)

# 1) .product-item 내부 구조 분석
field_analysis = page.evaluate("""() => {
    var cards = document.querySelectorAll('.product-item');
    if (cards.length === 0) return {count: 0};

    var samples = [];
    for (var i = 0; i < Math.min(5, cards.length); i++) {
        var card = cards[i];
        var children = card.querySelectorAll('*');
        var structure = [];
        for (var j = 0; j < children.length; j++) {
            var el = children[j];
            var text = (el.textContent || '').trim();
            var ownText = '';
            // own text (not children's text)
            for (var k = 0; k < el.childNodes.length; k++) {
                if (el.childNodes[k].nodeType === 3) {
                    ownText += (el.childNodes[k].textContent || '').trim();
                }
            }
            if (text.length > 0 && text.length < 200) {
                structure.push({
                    tag: el.tagName,
                    cls: (el.className || '').toString().substring(0, 80),
                    text: text.substring(0, 100),
                    ownText: ownText.substring(0, 100),
                    href: el.getAttribute('href') || '',
                    src: el.getAttribute('src') || el.getAttribute('data-src') || '',
                });
            }
        }

        // 링크 확인
        var links = card.querySelectorAll('a[href]');
        var linkInfo = [];
        for (var j = 0; j < links.length; j++) {
            linkInfo.push({
                href: links[j].getAttribute('href') || '',
                text: (links[j].textContent || '').trim().substring(0, 50),
            });
        }

        // 이미지 확인
        var imgs = card.querySelectorAll('img');
        var imgInfo = [];
        for (var j = 0; j < imgs.length; j++) {
            imgInfo.push({
                src: (imgs[j].src || imgs[j].getAttribute('data-src') || '').substring(0, 100),
                alt: imgs[j].alt || '',
            });
        }

        samples.push({
            tag: card.tagName,
            cls: (card.className || '').toString().substring(0, 100),
            innerHTML_len: (card.innerHTML || '').length,
            links: linkInfo,
            imgs: imgInfo,
            elements: structure.slice(0, 15),
        });
    }

    return {count: cards.length, samples: samples};
}""")

print(f"\n[diag] .product-item count: {field_analysis['count']}")
for i, sample in enumerate(field_analysis.get('samples', [])):
    print(f"\n--- Card {i+1} ---")
    print(f"  class: {sample['cls'][:80]}")
    print(f"  innerHTML len: {sample['innerHTML_len']}")
    print(f"  Links:")
    for link in sample['links'][:3]:
        try:
            print(f"    href={link['href'][:80]}, text={link['text'][:50]}")
        except:
            print(f"    href={link['href'][:80]}")
    print(f"  Images:")
    for img in sample['imgs'][:2]:
        print(f"    src={img['src'][:80]}")
    print(f"  Elements:")
    for el in sample['elements'][:10]:
        cls_short = el['cls'][:50] if el['cls'] else ''
        try:
            print(f"    <{el['tag']} class='{cls_short}'> own='{el['ownText'][:60]}'")
        except:
            print(f"    <{el['tag']} class='{cls_short}'> (encoding)")

# 2) 기존 필드 셀렉터 테스트
selectors_test = page.evaluate("""() => {
    var card = document.querySelector('.product-item');
    if (!card) return null;
    var tests = {
        'span.title': card.querySelector('span.title'),
        'span.price': card.querySelector('span.price'),
        'a': card.querySelector('a'),
        'img': card.querySelector('img'),
        '[class*="name"]': card.querySelector('[class*="name"]'),
        '[class*="price"]': card.querySelector('[class*="price"]'),
        '[class*="brand"]': card.querySelector('[class*="brand"]'),
        '[class*="title"]': card.querySelector('[class*="title"]'),
        '[class*="discount"]': card.querySelector('[class*="discount"]'),
        'p': card.querySelector('p'),
        'span': card.querySelector('span'),
    };
    var result = {};
    for (var key in tests) {
        if (tests[key]) {
            result[key] = {
                tag: tests[key].tagName,
                text: (tests[key].textContent || '').trim().substring(0, 80),
                cls: (tests[key].className || '').toString().substring(0, 60),
            };
        } else {
            result[key] = null;
        }
    }
    return result;
}""")
print(f"\n[diag] === Selector tests on first .product-item ===")
for sel, info in (selectors_test or {}).items():
    if info:
        try:
            print(f"  {sel}: <{info['tag']} class='{info['cls'][:40]}'> text='{info['text'][:60]}'")
        except:
            print(f"  {sel}: <{info['tag']}> (encoding)")
    else:
        print(f"  {sel}: NOT FOUND")

bm.close()
print("\n[diag] Done")
