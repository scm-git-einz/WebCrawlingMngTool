"""롯데면세점 상세 페이지 — dd.detail 내부 구조 정밀 분석"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from urllib.parse import urlparse
from core.browser import BrowserManager

DETAIL_URL = "https://kor.lottedfs.com/kr/product/productDetail?prdNo=20000388497&adltPrdYn=N"

JS_DEEP = """(() => {
    var result = {};

    // dd.detail 내부 구조
    var dd = document.querySelector('dd.detail');
    if (dd) {
        result.dd_detail_text_len = dd.innerText.length;
        result.dd_detail_children = Array.from(dd.children).map(c => ({
            tag: c.tagName,
            class: c.className.toString().substring(0, 60),
            textLen: c.innerText ? c.innerText.length : 0,
            textPreview: c.innerText ? c.innerText.substring(0, 100) : ''
        }));
    }

    // .tabBody 영역 구조
    var tabBodies = document.querySelectorAll('.tabBody, [class*="tabBody"]');
    result.tabBodies = Array.from(tabBodies).map(tb => ({
        class: tb.className.toString().substring(0, 60),
        textLen: tb.innerText ? tb.innerText.length : 0,
        textPreview: tb.innerText ? tb.innerText.substring(0, 150) : ''
    }));

    // .detailSpecNew 구조
    var specNew = document.querySelector('.detailSpecNew');
    if (specNew) {
        result.detailSpecNew_text_len = specNew.innerText.length;
        result.detailSpecNew_children = Array.from(specNew.children).map(c => ({
            tag: c.tagName,
            class: c.className.toString().substring(0, 60),
            textLen: c.innerText ? c.innerText.length : 0,
            textPreview: c.innerText ? c.innerText.substring(0, 100) : ''
        }));
    }

    // productArea 안 .product_name 구조
    var prdName = document.querySelector('.product_name');
    if (prdName) {
        result.product_name_text = prdName.innerText.trim().substring(0, 200);
    }

    // .detail_price_area 구조
    var priceArea = document.querySelector('.detail_price_area');
    if (priceArea) {
        result.price_area_text = priceArea.innerText.trim().substring(0, 200);
    }

    // tabBtn 내부 (탭 제목들)
    var tabBtn = document.querySelector('.tabBtn');
    if (tabBtn) {
        result.tabBtn_text = tabBtn.innerText.trim();
        result.tabBtn_links = Array.from(tabBtn.querySelectorAll('a')).map(a => ({
            text: a.innerText.trim(),
            href: a.href,
            class: a.className.toString().substring(0, 40)
        }));
    }

    // 테이블 기반 상품 정보 (cmpsPrdInfo_pkg)
    var specTable = document.querySelector('.cmpsPrdInfo_pkg');
    if (specTable) {
        result.cmpsPrdInfo_text = specTable.innerText.trim().substring(0, 500);
    }

    // 상세 이미지 분석: dd.detail 안의 모든 이미지
    if (dd) {
        var ddImgs = dd.querySelectorAll('img');
        result.dd_detail_images = Array.from(ddImgs).slice(0, 15).map(img => ({
            src: (img.src || img.dataset.src || '').substring(0, 120),
            width: img.naturalWidth || img.width || 0,
            height: img.naturalHeight || img.height || 0,
            parentClass: img.parentElement ? img.parentElement.className.toString().substring(0, 40) : ''
        }));
    }

    // OG 태그로 상품 정보 확인
    result.og = {};
    ['og:title', 'og:description', 'og:image', 'og:url'].forEach(prop => {
        var m = document.querySelector('meta[property="' + prop + '"]');
        result.og[prop] = m ? m.content : '(없음)';
    });

    return result;
})()"""

def main():
    bm = BrowserManager()
    domain = urlparse(DETAIL_URL).hostname
    try:
        page = bm.create(cookie_domain=domain)
        page.goto(DETAIL_URL, timeout=30000, wait_until="domcontentloaded")
        page.wait_for_timeout(5000)

        result = page.evaluate(JS_DEEP)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    finally:
        bm.close()

if __name__ == "__main__":
    main()
