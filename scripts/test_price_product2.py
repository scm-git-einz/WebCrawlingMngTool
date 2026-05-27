"""가격-상품명 페어링 - 다양한 패턴 검증 (3건)"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, "D:\\crawling")
from core.browser import BrowserManager

# 테스트 대상:
# 1) ■구입가격 패턴 (글렌드로낙21)
# 2) 번호+콜론 패턴 (달달위스키 행성시리즈)
# 3) 자연어 패턴 (야마자키18년 도쿄)

test_urls = [
    ("■구입가격 패턴 (글렌드로낙21)", "https://cafe.naver.com/ca-fe/cafes/14538121/articles/884773?fromPopular=true"),
    ("번호+콜론 패턴 (행성시리즈)", "https://cafe.naver.com/ca-fe/cafes/14538121/articles/884528?fromPopular=true"),
    ("자연어 패턴 (야마자키18)", "https://cafe.naver.com/ca-fe/cafes/14538121/articles/884488?fromPopular=true"),
    ("회비 제외 검증 (모임 후기)", "https://cafe.naver.com/ca-fe/cafes/14538121/articles/885103?fromPopular=true"),
]

JS_EXTRACT = r"""() => {
    var bodySelectors = ['.se-main-container','.ContentRenderer','.article_viewer','.content_view','#body'];
    var bodyEl = null;
    for (var i = 0; i < bodySelectors.length; i++) {
        var el = document.querySelector(bodySelectors[i]);
        if (el && el.innerText.trim().length > 20) { bodyEl = el; break; }
    }
    if (!bodyEl) return null;
    var bodyText = bodyEl.innerText.trim();
    var titleEl = document.querySelector('.title_text, .art_tit, h3.title_text, [class*="article_title"], [class*="subject"]');
    var title = titleEl ? titleEl.innerText.trim() : '';

    var nonProductWords = ['식대','회비','1인당','인당','÷','나누기','송금','입금','팔로워','팔로잉','게시물'];
    var priceItems = [];
    var seenPrices = {};
    var bodyLines = bodyText.split('\n');

    for (var li = 0; li < bodyLines.length; li++) {
        var line = bodyLines[li].trim();
        if (!line) continue;
        var linePriceRe = /(\d{1,3}(?:,\d{3})+)\s*원?/g;
        var pm;
        while ((pm = linePriceRe.exec(line)) !== null) {
            var priceStr = pm[0];
            var priceNum = parseInt(pm[1].replace(/,/g, ''));
            if (priceNum < 1000 || priceNum > 100000000) continue;
            var normalizedPrice = pm[1];
            if (seenPrices[normalizedPrice]) continue;
            seenPrices[normalizedPrice] = true;

            var isNonProduct = false;
            for (var npi = 0; npi < nonProductWords.length; npi++) {
                if (line.indexOf(nonProductWords[npi]) > -1) { isNonProduct = true; break; }
            }
            if (isNonProduct) continue;

            var product = '';

            // 패턴1: 슬래시 구분
            var slashParts = line.split('/');
            if (slashParts.length >= 2) {
                for (var si = 0; si < slashParts.length; si++) {
                    if (slashParts[si].indexOf(pm[1]) > -1 && si > 0) {
                        product = slashParts[si - 1].trim();
                        product = product.replace(/^\d+\.\s*/, '');
                        break;
                    }
                }
            }

            // 패턴2: 콜론 구분
            if (!product) {
                var colonIdx = line.lastIndexOf(':');
                if (colonIdx > -1 && line.indexOf(pm[1]) > colonIdx) {
                    var beforeColon = line.substring(0, colonIdx).trim();
                    beforeColon = beforeColon.replace(/^\d+\.\s*/, '');
                    if (beforeColon.indexOf('구입가격') > -1 || beforeColon.indexOf('구입 가격') > -1) {
                        product = title;
                    } else if (beforeColon.length > 1 && beforeColon.length < 100) {
                        product = beforeColon;
                    }
                }
            }

            // 패턴3: ■구입가격 (콜론 없이)
            if (!product) {
                if (line.indexOf('구입가격') > -1 || line.indexOf('구입 가격') > -1) {
                    product = title;
                }
            }

            // 패턴4: 가격 앞 텍스트
            if (!product) {
                var beforePrice = line.substring(0, pm.index).trim();
                beforePrice = beforePrice.replace(/[\s,.:;/]+$/, '');
                if (beforePrice.length > 1 && beforePrice.length < 100) {
                    beforePrice = beforePrice.replace(/^\d+\.\s*/, '');
                    beforePrice = beforePrice.replace(/^(현재\s*(금액)?|그렇게\s*적용하면\s*(가격이)?|무려)\s*/, '');
                    if (beforePrice.length > 1) { product = beforePrice; }
                }
            }

            priceItems.push({
                product: product.substring(0, 150),
                price: priceStr.trim(),
                context: line.substring(0, 200),
            });
        }
    }
    return { title: title, priceItems: priceItems };
}"""

bm = BrowserManager()
page = bm.create()

for label, url in test_urls:
    print(f"\n{'='*60}")
    print(f"테스트: {label}")
    print(f"URL: {url}")
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(5000)

    result = page.evaluate(JS_EXTRACT)
    if result:
        print(f"제목: {result['title']}")
        print(f"추출 결과 ({len(result['priceItems'])}건):")
        for idx, item in enumerate(result['priceItems'], 1):
            print(f"  [{idx}] 상품: '{item['product']}' | 가격: {item['price']}")
            print(f"       ctx: {item['context'][:100]}")
    else:
        print("추출 실패!")

bm.close()
print("\nDone!")
