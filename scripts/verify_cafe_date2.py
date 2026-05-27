"""카페 인기글 - 2페이지 날짜 형식 확인 (버튼 클릭)"""
import sys
sys.path.insert(0, "D:\\crawling")
from core.browser import BrowserManager

bm = BrowserManager()
page = bm.create()

url = "https://cafe.naver.com/ca-fe/cafes/14538121/popular"
resp = page.goto(url, wait_until="domcontentloaded", timeout=60000)
page.wait_for_timeout(5000)

# 5페이지 버튼 클릭 (오래된 글이 있을 확률이 높음)
for target in [2, 3, 4, 5]:
    clicked = page.evaluate(r"""(targetPage) => {
        var container = document.querySelector('.ArticlePaginate, [class*="Paginate"]');
        if (!container) return {error: 'no container'};
        var buttons = container.querySelectorAll('button');
        for (var i = 0; i < buttons.length; i++) {
            if (buttons[i].textContent.trim() === String(targetPage)) {
                buttons[i].click();
                return {clicked: true, page: targetPage};
            }
        }
        return {error: 'not found'};
    }""", target)
    page.wait_for_timeout(3000)

print(f"현재 URL: {page.url}")

# 5페이지 게시글 날짜 확인
posts = page.evaluate(r"""() => {
    var links = document.querySelectorAll('a.article[href]');
    var results = [];
    var seen = {};
    for (var i = 0; i < links.length; i++) {
        var a = links[i];
        var href = a.getAttribute('href') || '';
        var text = a.textContent.trim();
        if (text.length < 3 || href.indexOf('/articles/') === -1) continue;
        var idMatch = href.match(/\/articles\/(\d+)/);
        if (!idMatch) continue;
        var articleId = idMatch[1];
        if (seen[articleId]) continue;
        seen[articleId] = true;

        var row = a.closest('tr');
        var date = '';
        if (row) {
            var dateEl = row.querySelector('td.td_date');
            if (dateEl) date = dateEl.textContent.trim();
        }
        results.push({
            title: text.substring(0, 50),
            date: date,
        });
    }
    return results;
}""")

print(f"\n=== 5페이지 게시글 ({len(posts)}개) ===\n")
for i, p in enumerate(posts):
    t = p['title'].encode('cp949', errors='replace').decode('cp949')
    print(f"[{i+1:2d}] date='{p['date']}' | {t}")

bm.close()
print("\nDone!")
