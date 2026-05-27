"""네이버 카페 인기글 - inner_list 내 날짜 필드 확인"""
import sys
sys.path.insert(0, "D:\\crawling")
from core.browser import BrowserManager

bm = BrowserManager()
page = bm.create()

url = "https://cafe.naver.com/ca-fe/cafes/14538121/popular"
resp = page.goto(url, wait_until="domcontentloaded", timeout=60000)
page.wait_for_timeout(5000)

# inner_list div 내부 구조 (HTML 전체)
print("=== inner_list 구조 ===")
html_info = page.evaluate(r"""() => {
    var items = document.querySelectorAll('.inner_list');
    var results = [];
    for (var i = 0; i < Math.min(items.length, 3); i++) {
        results.push(items[i].outerHTML.substring(0, 1000));
    }
    return results;
}""")

for i, h in enumerate(html_info):
    safe = h.encode('ascii', errors='replace').decode('ascii')
    print(f"\n--- item {i+1} ---")
    print(safe)

# span/div 요소 중 날짜 패턴 포함하는 것 찾기
print("\n\n=== 날짜 패턴 탐색 ===")
date_els = page.evaluate(r"""() => {
    var items = document.querySelectorAll('.inner_list');
    var results = [];
    for (var i = 0; i < Math.min(items.length, 5); i++) {
        var all = items[i].querySelectorAll('*');
        var children = [];
        for (var j = 0; j < all.length; j++) {
            var el = all[j];
            var text = el.textContent.trim();
            // 짧은 텍스트만 (날짜는 보통 10~15자)
            if (text.length >= 3 && text.length <= 20) {
                children.push({
                    tag: el.tagName,
                    cls: (el.className || '').substring(0, 60),
                    text: text,
                });
            }
        }
        results.push(children);
    }
    return results;
}""")

for i, children in enumerate(date_els):
    safe_items = []
    for c in children:
        t = c['text'].encode('cp949', errors='replace').decode('cp949')
        safe_items.append(f"  <{c['tag']}> cls='{c['cls']}' -> '{t}'")
    print(f"\nitem {i+1} ({len(children)} elements):")
    for s in safe_items:
        print(s)

bm.close()
print("\nDone!")
