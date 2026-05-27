"""네이버 뉴스 검색 - 최종 추출 패턴 검증"""
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

for _ in range(3):
    page.evaluate("window.scrollBy(0, window.innerHeight)")
    page.wait_for_timeout(1500)

# 안정적 패턴 기반 뉴스 기사 추출 테스트
articles = page.evaluate("""() => {
    var container = document.querySelector('.list_news');
    if (!container) container = document.querySelector('.group_news');
    if (!container) container = document.body;

    var allLinks = container.querySelectorAll('a[href]');
    var articleMap = {};  // URL별 그룹핑

    for (var i = 0; i < allLinks.length; i++) {
        var a = allLinks[i];
        var href = a.getAttribute('href') || '';
        var text = a.textContent.trim();

        // 뉴스 기사가 아닌 링크 필터
        if (!href || href === '#' || href.indexOf('javascript:') === 0) continue;
        if (href.indexOf('keep.naver.com') > -1) continue;
        if (href.indexOf('media.naver.com/press') > -1) continue;

        // 네이버뉴스 라벨 링크 (n.news, mnews, entertain.naver)
        var isNaverNewsLabel = (
            (href.indexOf('n.news.naver.com') > -1 ||
             href.indexOf('mnews') > -1 ||
             href.indexOf('entertain.naver.com') > -1)
            && text.length < 10
        );

        if (isNaverNewsLabel) continue;
        if (text.length < 5) continue;

        // 키 URL 정규화 (같은 기사의 여러 링크를 그룹핑)
        var normUrl = href.split('?')[0].split('#')[0];
        if (href.indexOf('naver.com') > -1) {
            normUrl = href;  // 네이버 뉴스 URL은 원본 유지
        }

        if (!articleMap[normUrl]) {
            articleMap[normUrl] = {url: href, texts: [], textLengths: []};
        }
        articleMap[normUrl].texts.push(text.substring(0, 200));
        articleMap[normUrl].textLengths.push(text.length);
    }

    // 각 URL 그룹에서 제목(가장 짧은 텍스트 10~150자)과 본문 미리보기 추출
    var results = [];
    for (var url in articleMap) {
        var group = articleMap[url];
        var texts = group.texts;

        // 제목: 10~150자 범위의 가장 짧은 텍스트
        var title = '';
        var description = '';
        for (var j = 0; j < texts.length; j++) {
            var t = texts[j];
            if (t.length >= 10 && t.length <= 150) {
                if (!title || t.length < title.length) {
                    title = t;
                }
            }
            if (t.length > 50) {
                if (!description || t.length > description.length) {
                    description = t;
                }
            }
        }

        if (!title) continue;

        results.push({
            title: title,
            description: description !== title ? description : '',
            url: group.url,
            linkCount: texts.length,
        });
    }

    // 언론사 + 날짜 추출 (별도 탐색)
    // 언론사: a[href*="media.naver.com/press"] 텍스트
    var pressLinks = container.querySelectorAll('a[href*="media.naver.com/press"]');
    var pressNames = [];
    for (var pi = 0; pi < pressLinks.length; pi++) {
        var ptext = pressLinks[pi].textContent.trim();
        if (ptext.length > 0 && ptext.length < 30) {
            pressNames.push(ptext);
        }
    }

    // 날짜: "X시간 전", "X분 전", "2026.05.24." 패턴
    var allSpans = container.querySelectorAll('span');
    var dates = [];
    var datePattern = /(\d+분 전|\d+시간 전|\d+일 전|\d{4}\.\d{2}\.\d{2})/;
    for (var di = 0; di < allSpans.length; di++) {
        var dtText = allSpans[di].textContent.trim();
        var match = datePattern.exec(dtText);
        if (match) {
            dates.push(match[1]);
        }
    }

    // 매칭 (순서 기반)
    var pressIdx = 0;
    var dateIdx = 0;
    for (var ri = 0; ri < results.length; ri++) {
        if (pressIdx < pressNames.length) {
            results[ri].press = pressNames[pressIdx];
            // 같은 언론사가 연속될 수 있으므로 기사별로 증가
            pressIdx++;
        }
        if (dateIdx < dates.length) {
            results[ri].date = dates[dateIdx];
            dateIdx++;
        }
    }

    return results;
}""")

print(f"\n=== 추출된 기사: {len(articles)}개 ===\n")
for i, art in enumerate(articles):
    print(f"[{i+1}] {art['title'][:70]}")
    print(f"    URL: {art['url'][:80]}")
    print(f"    언론사: {art.get('press', 'N/A')}")
    print(f"    날짜: {art.get('date', 'N/A')}")
    if art.get('description'):
        print(f"    요약: {art['description'][:60]}...")
    print()

bm.close()
print("Done!")
