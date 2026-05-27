"""카페 인기글 날짜 추출 검증 - 1페이지 5건만 확인"""
import sys
sys.path.insert(0, "D:\\crawling")
from core.browser import BrowserManager

bm = BrowserManager()
page = bm.create()

url = "https://cafe.naver.com/ca-fe/cafes/14538121/popular"
resp = page.goto(url, wait_until="domcontentloaded", timeout=60000)
page.wait_for_timeout(5000)

# 수정된 JS로 목록 추출 (tr 우선 탐색, td.td_date 사용)
posts = page.evaluate(r"""() => {
    var links = document.querySelectorAll('a.article[href]');
    var results = [];
    var seen = {};

    for (var i = 0; i < links.length; i++) {
        var a = links[i];
        var href = a.getAttribute('href') || '';
        var text = a.textContent.trim();
        if (text.length < 3) continue;
        if (href.indexOf('/articles/') === -1) continue;

        var idMatch = href.match(/\/articles\/(\d+)/);
        if (!idMatch) continue;
        var articleId = idMatch[1];
        if (seen[articleId]) continue;
        seen[articleId] = true;

        // tr을 우선 탐색
        var row = a.closest('tr');
        if (!row) row = a.closest('.inner_list, [class*="item"]');
        var author = '';
        var date = '';
        var views = '';

        if (row) {
            var authorEl = row.querySelector('td.td_name .nickname, .nickname, .nick');
            if (authorEl) author = authorEl.textContent.trim();

            var dateEl = row.querySelector('td.td_date, .date, td:nth-child(3)');
            if (dateEl) date = dateEl.textContent.trim();

            var viewEl = row.querySelector('td.td_view, .view, td:nth-child(4)');
            if (viewEl) views = viewEl.textContent.trim();
        }

        results.push({
            article_id: articleId,
            title: text.substring(0, 60),
            author: author.substring(0, 30),
            date: date.substring(0, 30),
            views: views.substring(0, 20),
        });
    }
    return results;
}""")

print(f"=== 1페이지 게시글 ({len(posts)}개) ===\n")
for i, p in enumerate(posts):
    t = p['title'].encode('cp949', errors='replace').decode('cp949')
    a = p['author'].encode('cp949', errors='replace').decode('cp949')
    print(f"[{i+1:2d}] {t}")
    print(f"     author='{a}' | date='{p['date']}' | views='{p['views']}'")

bm.close()
print("\nDone!")
