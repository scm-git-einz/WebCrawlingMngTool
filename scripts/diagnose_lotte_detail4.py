"""롯데면세점 상세 페이지 — 가격/코드/혜택 정밀 분석"""
import json, sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from core.browser import BrowserManager

URL = "https://kor.lottedfs.com/kr/product/productDetail?prdNo=10001395589&adltPrdYn=N"

JS_DETAIL = r"""(() => {
    var r = {};

    /* ── 1. cmpsDetail_pkg (상품 상세 메인 영역) 내부 구조 ── */
    var detailPkg = document.querySelector('.cmpsDetail_pkg');
    if (detailPkg) {
        /* 하위 주요 영역 */
        var areas = detailPkg.querySelectorAll('[class]');
        var areaMap = {};
        areas.forEach(function(el) {
            var cls = el.className.trim();
            if (cls && cls.length < 60 && el.innerText.trim().length > 0 && el.innerText.trim().length < 300) {
                if (!areaMap[cls]) areaMap[cls] = el.innerText.trim();
            }
        });
        r.cmpsDetail_areas = areaMap;
    }

    /* ── 2. 가격 정밀 분석: 정상가/회원가 구분 ── */
    /* 가격 영역 상위 래퍼 */
    var priceWrap = document.querySelector('.cmpsPrice_pkg, .price_wrap, .priceInfo');
    if (priceWrap) {
        r.priceWrap_text = priceWrap.innerText.trim().substring(0, 500);
        r.priceWrap_html = priceWrap.innerHTML.substring(0, 1500);
    }

    /* 정상가 / 할인가 / 회원가 각각 */
    var priceLabels = document.querySelectorAll('dt, th, .label, .tit, [class*="tit"]');
    var pricePairs = [];
    priceLabels.forEach(function(lbl) {
        var text = lbl.innerText.trim();
        if (/정상가|판매가|할인가|회원가|멤버|합계|VIP/i.test(text)) {
            var next = lbl.nextElementSibling;
            var val = next ? next.innerText.trim() : '';
            pricePairs.push({ label: text, value: val.substring(0, 100), class: lbl.className });
        }
    });
    r.price_pairs = pricePairs;

    /* ── 3. 상품코드/레퍼런스코드 정밀 추출 ── */
    /* dl > dt + dd 패턴 */
    var dts = document.querySelectorAll('dt');
    var codePairs = [];
    dts.forEach(function(dt) {
        var text = dt.innerText.trim();
        if (/상품코드|레퍼런스|품목코드|Ref/i.test(text)) {
            var dd = dt.nextElementSibling;
            codePairs.push({
                label: text,
                value: dd ? dd.innerText.trim().substring(0, 80) : '',
                parent_class: dt.parentElement ? dt.parentElement.className : ''
            });
        }
    });
    r.code_pairs = codePairs;

    /* td 기반 코드 탐색 */
    var tds = document.querySelectorAll('td, th');
    tds.forEach(function(td) {
        var text = td.innerText.trim();
        if (/상품코드|레퍼런스코드/i.test(text) && text.length < 50) {
            var next = td.nextElementSibling;
            codePairs.push({
                label: text,
                value: next ? next.innerText.trim() : '',
                tag: td.tagName
            });
        }
    });

    /* ── 4. 구매혜택 상세 ── */
    var benefitEl = document.querySelector('[class*="benefit"]');
    if (benefitEl) {
        r.benefit_text = benefitEl.innerText.trim().substring(0, 500);
        r.benefit_children = [];
        var children = benefitEl.children;
        for (var i = 0; i < Math.min(children.length, 10); i++) {
            r.benefit_children.push({
                tag: children[i].tagName,
                cls: children[i].className.substring(0, 50),
                text: children[i].innerText.trim().substring(0, 100)
            });
        }
    }

    /* ── 5. 관련상품 (함께 살수록 할인, 연관상품) ── */
    var togetherEl = document.querySelector('[class*="together"], [class*="Together"]');
    if (togetherEl) {
        r.together_text = togetherEl.innerText.trim().substring(0, 300);
        var togItems = togetherEl.querySelectorAll('[class*="item"], li, .prd');
        r.together_items = [];
        togItems.forEach(function(item, idx) {
            if (idx < 10) {
                r.together_items.push({
                    text: item.innerText.trim().substring(0, 100),
                    img: item.querySelector('img') ? item.querySelector('img').src : ''
                });
            }
        });
    }

    /* ── 6. 탭 영역 (상품기술서 이미지가 들어있는 탭) ── */
    var tabs = document.querySelectorAll('[class*="tab"] a, [class*="tab"] li, [role="tab"]');
    r.tab_labels = [];
    tabs.forEach(function(tab, i) {
        if (i < 10 && tab.innerText.trim()) {
            r.tab_labels.push(tab.innerText.trim().substring(0, 30));
        }
    });

    /* dd.detail 내 이미지 (상품기술서) */
    var ddDetail = document.querySelector('dd.detail');
    if (ddDetail) {
        var ddImgs = ddDetail.querySelectorAll('img');
        r.dd_detail_images = [];
        ddImgs.forEach(function(img, i) {
            if (i < 10) r.dd_detail_images.push((img.src || img.dataset.src || '').substring(0, 150));
        });
        r.dd_detail_text_preview = ddDetail.innerText.trim().substring(0, 200);
    }

    return r;
})()"""


def main():
    bm = BrowserManager()
    page = bm.create(cookie_domain="lottedfs.com")
    try:
        print(f"[+] 접속: {URL}")
        resp = page.goto(URL, wait_until="domcontentloaded", timeout=30000)
        print(f"[+] 응답: {resp.status if resp else 'None'}")
        page.wait_for_timeout(3000)

        result = page.evaluate(JS_DETAIL)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        bm.close()

if __name__ == "__main__":
    main()
