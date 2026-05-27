"""롯데면세점 상세 페이지 DOM 구조 분석 스크립트"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.browser import BrowserManager

DETAIL_URL = "https://kor.lottedfs.com/kr/product/productDetail?prdNo=20000388497&adltPrdYn=N"

JS_ANALYZE = """(() => {
    const result = {};

    // 1. meta description 확인
    const metaDesc = document.querySelector('meta[name="description"]');
    result.meta_description = metaDesc ? metaDesc.content : '(없음)';

    // 2. OG tags
    const ogDesc = document.querySelector('meta[property="og:description"]');
    result.og_description = ogDesc ? ogDesc.content : '(없음)';
    const ogTitle = document.querySelector('meta[property="og:title"]');
    result.og_title = ogTitle ? ogTitle.content : '(없음)';
    const ogImage = document.querySelector('meta[property="og:image"]');
    result.og_image = ogImage ? ogImage.content : '(없음)';

    // 3. 상품명 후보
    result.title_tag = document.title;
    const h1 = document.querySelector('h1');
    result.h1_text = h1 ? h1.innerText.trim() : '(없음)';
    const h2s = document.querySelectorAll('h2');
    result.h2_texts = Array.from(h2s).slice(0, 5).map(h => h.innerText.trim());

    // 4. 상세 설명 영역 탐지
    const selectors = [
        '[class*="detail"]', '[class*="description"]', '[class*="info"]',
        '[class*="product"]', '[class*="prd"]', '[class*="goods"]',
        '[class*="content"]', '[class*="spec"]', '[class*="tabContent"]',
        '[id*="detail"]', '[id*="info"]', '[id*="product"]',
        '[id*="content"]', '[id*="spec"]', '[id*="tab"]',
        'article', 'main', '.detail_view', '#detailArea',
        '.prd_detail', '.goods_detail', '.product_detail'
    ];

    result.found_selectors = {};
    for (const sel of selectors) {
        const els = document.querySelectorAll(sel);
        if (els.length > 0) {
            const samples = Array.from(els).slice(0, 3).map(el => ({
                tag: el.tagName,
                class: el.className ? el.className.toString().substring(0, 80) : '',
                id: el.id || '',
                childCount: el.children.length,
                textLen: el.innerText ? el.innerText.length : 0,
                textPreview: el.innerText ? el.innerText.substring(0, 100) : ''
            }));
            result.found_selectors[sel] = samples;
        }
    }

    // 5. 이미지 영역 탐지
    const allImgs = document.querySelectorAll('img[src]');
    result.total_images = allImgs.length;
    const largeImgs = Array.from(allImgs).filter(img =>
        img.naturalWidth > 200 && !img.src.includes('icon') && !img.src.includes('logo')
    );
    result.large_images_count = largeImgs.length;
    result.large_images_samples = largeImgs.slice(0, 10).map(img => ({
        src: img.src.substring(0, 120),
        width: img.naturalWidth,
        height: img.naturalHeight,
        parentClass: img.parentElement ? img.parentElement.className.toString().substring(0, 60) : '',
        grandParentClass: img.parentElement && img.parentElement.parentElement ?
            img.parentElement.parentElement.className.toString().substring(0, 60) : ''
    }));

    // 6. 가격 관련 요소
    const priceEls = document.querySelectorAll('[class*="price"], [class*="Price"]');
    result.price_elements = Array.from(priceEls).slice(0, 10).map(el => ({
        class: el.className.toString().substring(0, 60),
        text: el.innerText.trim().substring(0, 50)
    }));

    // 7. 탭 구조 확인 (상세정보 탭 등)
    const tabEls = document.querySelectorAll('[class*="tab"], [role="tab"], [data-tab]');
    result.tab_elements = Array.from(tabEls).slice(0, 10).map(el => ({
        tag: el.tagName,
        class: el.className.toString().substring(0, 60),
        text: el.innerText.trim().substring(0, 50),
        href: el.href || '',
        dataTab: el.dataset ? el.dataset.tab || '' : ''
    }));

    // 8. iframe 확인 (상세 설명이 iframe으로 되어있을 수 있음)
    const iframes = document.querySelectorAll('iframe');
    result.iframes = Array.from(iframes).slice(0, 5).map(f => ({
        src: f.src ? f.src.substring(0, 120) : '',
        id: f.id || '',
        class: f.className || '',
        width: f.width,
        height: f.height
    }));

    // 9. 본문 주요 영역 구조 (body > div 1~2레벨)
    const body = document.body;
    const topDivs = body.querySelectorAll(':scope > div, :scope > main, :scope > section');
    result.top_structure = Array.from(topDivs).slice(0, 10).map(d => ({
        tag: d.tagName,
        id: d.id || '',
        class: d.className ? d.className.toString().substring(0, 80) : '',
        childCount: d.children.length
    }));

    return result;
})()"""

def main():
    from urllib.parse import urlparse
    bm = BrowserManager()
    domain = urlparse(DETAIL_URL).hostname
    try:
        page = bm.create(cookie_domain=domain)

        print(f"접속 중: {DETAIL_URL}")
        page.goto(DETAIL_URL, timeout=30000, wait_until="domcontentloaded")
        page.wait_for_timeout(5000)

        print(f"현재 URL: {page.url}")
        print(f"페이지 제목: {page.title()}")

        result = page.evaluate(JS_ANALYZE)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    finally:
        bm.close()

if __name__ == "__main__":
    main()
