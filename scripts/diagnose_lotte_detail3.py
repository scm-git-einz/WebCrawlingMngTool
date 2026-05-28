"""롯데면세점 상품 상세 페이지 DOM 구조 분석 — 확장 필드 탐지"""
import json, sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from core.browser import BrowserManager

URL = "https://kor.lottedfs.com/kr/product/productDetail?prdNo=10001395589&adltPrdYn=N"

JS_ANALYZE = r"""(() => {
    var result = {};

    /* 1. 카테고리 breadcrumb */
    var bcSels = [
        '.location_area', '.breadcrumb', '.path_area',
        '[class*="breadcrumb"]', '[class*="location"]', '[class*="path"]',
        'nav[aria-label*="breadcrumb"]', '.gnb_area .path',
        '.cmpsTit_pkg .location', '.locationWrap'
    ];
    for (var i = 0; i < bcSels.length; i++) {
        var el = document.querySelector(bcSels[i]);
        if (el && el.innerText && el.innerText.trim().length > 3) {
            result.breadcrumb_selector = bcSels[i];
            result.breadcrumb_text = el.innerText.trim().substring(0, 200);
            result.breadcrumb_html = el.innerHTML.substring(0, 500);
            break;
        }
    }

    /* 2. 상품코드 / 레퍼런스코드 */
    var allText = document.body.innerText;
    var codePatterns = [
        { label: 'product_code_match', re: /상품코드[\s:：]*([A-Z0-9\-]+)/i },
        { label: 'ref_code_match', re: /레퍼런스[\s]*코드[\s:：]*([A-Z0-9\-\s]+)/i },
        { label: 'prd_no_match', re: /PRD[\s\-]*NO[\s:：]*(\d+)/i },
        { label: 'item_code_match', re: /ITEM[\s]*CODE[\s:：]*([A-Z0-9\-]+)/i },
    ];
    codePatterns.forEach(function(p) {
        var m = allText.match(p.re);
        if (m) result[p.label] = m[0];
    });

    /* 코드 영역 DOM */
    var codeSels = [
        '.prd_code', '.product_code', '[class*="prdCode"]', '[class*="refCode"]',
        '[class*="itemCode"]', '.code_area', '.cmpsPrdInfo_pkg .code',
        '[class*="prdNo"]', '[class*="refNo"]'
    ];
    codeSels.forEach(function(sel) {
        var el = document.querySelector(sel);
        if (el && el.innerText.trim()) {
            result['code_dom_' + sel] = el.innerText.trim().substring(0, 100);
        }
    });

    /* 3. 가격 영역 분석 */
    var priceSels = [
        '.price_area', '.priceBox', '.prd_price', '.cmpsPrice_pkg',
        '.normalPrice', '.memberPrice', '.sale_price', '.member_price',
        '[class*="price"]', '[class*="Price"]'
    ];
    var priceInfo = {};
    priceSels.forEach(function(sel) {
        var els = document.querySelectorAll(sel);
        els.forEach(function(el, idx) {
            var key = sel + (idx > 0 ? '_' + idx : '');
            var text = el.innerText.trim();
            if (text && text.length < 300 && text.length > 0) priceInfo[key] = text;
        });
    });
    result.price_areas = priceInfo;

    /* 4. 구매혜택 */
    var benefitSels = [
        '[class*="benefit"]', '[class*="Benefit"]', '.coupon_area', '.point_area',
        '.cmpsOption_pkg', '.additional_info', '[class*="bnft"]',
        '[class*="addInfo"]', '.prd_benefit'
    ];
    benefitSels.forEach(function(sel) {
        var el = document.querySelector(sel);
        if (el && el.innerText.trim()) {
            result['benefit_' + sel] = el.innerText.trim().substring(0, 400);
        }
    });

    /* 5. 관련상품 */
    var relatedSels = [
        '[class*="related"]', '[class*="recommend"]', '[class*="연관"]',
        '.cmpsPrdListH_pkg', '[class*="Also"]', '[class*="together"]'
    ];
    relatedSels.forEach(function(sel) {
        var el = document.querySelector(sel);
        if (el) {
            var links = el.querySelectorAll('a[href*="product"]');
            result['related_' + sel] = {
                count: links.length,
                preview: el.innerText.trim().substring(0, 300)
            };
        }
    });

    /* 6. 상품명/브랜드 */
    var nameSels = ['.prd_name', '.product_name', 'h1', 'h2.name', '[class*="prdName"]', '.cmpsPrdInfo_pkg .name', '.cmpsDetail_pkg .name'];
    nameSels.forEach(function(sel) {
        var el = document.querySelector(sel);
        if (el && el.innerText.trim()) result['name_' + sel] = el.innerText.trim().substring(0, 100);
    });
    var brandSels = ['.brand_name', '.brand', '[class*="brandName"]', '[class*="brand_name"]', '.cmpsDetail_pkg .brand'];
    brandSels.forEach(function(sel) {
        var el = document.querySelector(sel);
        if (el && el.innerText.trim()) result['brand_' + sel] = el.innerText.trim().substring(0, 100);
    });

    /* 7. 상세 이미지 영역 */
    var detailImgSels = [
        '#productDetailContent img', '.tabBody img', '.detail_area img',
        'dd.detail img', '[class*="detail_desc"] img',
        '.cmpsPrdDetail_pkg img', '#detailContent img',
        '.detail img', '.goods_desc img'
    ];
    var detailImgInfo = {};
    detailImgSels.forEach(function(sel) {
        var imgs = document.querySelectorAll(sel);
        if (imgs.length > 0) {
            detailImgInfo[sel] = {
                count: imgs.length,
                srcs: Array.from(imgs).slice(0, 3).map(function(img) { return (img.src || img.dataset.src || '').substring(0, 120); })
            };
        }
    });
    result.detail_images_areas = detailImgInfo;

    /* 8. 페이지 최상위 구조 (class 기반) */
    var mainEls = document.querySelectorAll('body > div, #wrap > *, #content > *, .content > *, main > *');
    var structure = [];
    mainEls.forEach(function(el, i) {
        if (i < 30 && el.className) {
            structure.push({
                tag: el.tagName,
                cls: (el.className || '').substring(0, 80),
                preview: el.innerText.trim().substring(0, 60)
            });
        }
    });
    result.top_structure = structure;

    /* 9. cmpsPrdInfo_pkg 영역 전체 텍스트 (롯데 공통 상품정보 래퍼) */
    var prdInfoPkg = document.querySelector('.cmpsPrdInfo_pkg');
    if (prdInfoPkg) {
        result.cmpsPrdInfo_pkg_text = prdInfoPkg.innerText.trim().substring(0, 1000);
        result.cmpsPrdInfo_pkg_html = prdInfoPkg.innerHTML.substring(0, 2000);
    }

    /* 10. cmpsDetail_pkg 영역 */
    var detailPkg = document.querySelector('.cmpsDetail_pkg');
    if (detailPkg) {
        result.cmpsDetail_pkg_text = detailPkg.innerText.trim().substring(0, 1000);
    }

    /* 11. 페이지 전체 텍스트에서 핵심 패턴 추출 */
    var bodyText = document.body.innerText;
    /* 레퍼런스코드 패턴 */
    var refMatch = bodyText.match(/[Rr]ef(?:erence)?[\s.]*(?:[Cc]ode)?[\s:：.]*([A-Z0-9\-\.]+)/);
    if (refMatch) result.ref_code_extracted = refMatch[0];
    /* 상품코드 숫자 패턴 */
    var prdCodeMatch = bodyText.match(/(?:상품|품목|제품)[\s]*(?:코드|번호|No)[\s:：]*([A-Z0-9\-]+)/i);
    if (prdCodeMatch) result.prd_code_extracted = prdCodeMatch[0];

    return result;
})()"""


def main():
    bm = BrowserManager()
    page = bm.create(cookie_domain="lottedfs.com")
    try:
        print(f"[+] 접속: {URL}")
        resp = page.goto(URL, wait_until="domcontentloaded", timeout=30000)
        print(f"[+] 응답: {resp.status if resp else 'None'}")
        page.wait_for_timeout(3000)

        result = page.evaluate(JS_ANALYZE)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        bm.close()

if __name__ == "__main__":
    main()
