"""올리브영 상품 상세 수집 에이전트"""
from agents.local.base import LocalAgent


# 올리브영은 CSS 모듈 해시 클래스를 사용하므로 [class*="..."] 부분 매칭으로 추출한다.
# 디버그 확인된 실제 클래스:
#   브랜드:  TopUtils_btn-brand__tvEdp
#   정상가:  GoodsDetailInfo_price-before__5az8B
#   할인가:  GoodsDetailInfo_price__AoTh8
#   할인율:  GoodsDetailInfo_price-area__RE0Gc 텍스트 내 "37%" 패턴
#   상품명:  GoodsDetailInfo_goods-info__NvhCW 두 번째 줄
_JS_EXTRACT_DOM = """(() => {
    const get = (sels) => {
        for (const sel of sels) {
            const el = document.querySelector(sel);
            if (!el) continue;
            const t = (el.getAttribute('content') || el.innerText || el.textContent || '').trim();
            if (t) return t;
        }
        return '';
    };

    // 브랜드명
    const brand = get([
        '[class*="btn-brand"]',
        '[class*="brand-name"]',
        'a[class*="brand"]',
    ]);

    // 상품명 — goods-info 두 번째 줄(첫 줄=브랜드) or OG title
    let name = '';
    const goodsInfo = document.querySelector('[class*="goods-info"]');
    if (goodsInfo) {
        const lines = goodsInfo.innerText.split('\\n').map(s => s.trim()).filter(Boolean);
        name = lines.length >= 2 ? lines[1] : (lines[0] || '');
    }
    if (!name) {
        const og = document.querySelector('meta[property="og:title"]');
        name = (og ? og.getAttribute('content') : document.title.split('|')[0] || '').trim();
    }

    // 정상가 (할인 전 원가)
    const regular_price = get([
        '[class*="price-before"]',
        '[class*="origin-price"]',
    ]);

    // 할인가 (판매가) — "_price__" 패턴 (price-before/price-area/price-box 제외)
    let discounted_price = '';
    const priceEls = Array.from(document.querySelectorAll('[class*="GoodsDetailInfo"][class*="price"]'));
    for (const el of priceEls) {
        if (/_price__/.test(el.className)) {
            const t = (el.innerText || '').trim();
            if (t) { discounted_price = t; break; }
        }
    }
    if (!discounted_price) {
        discounted_price = get(['[class*="sale-price"]', '[class*="final-price"]']);
    }

    // 할인율 — price-area 텍스트에서 숫자% 패턴 추출
    let discount_rate = '';
    const priceArea = document.querySelector('[class*="price-area"],[class*="price-box-wrap"]');
    if (priceArea) {
        const m = (priceArea.innerText || '').match(/(\\d+)%/);
        if (m) discount_rate = m[1] + '%';
    }

    return { brand, name, regular_price, discounted_price, discount_rate };
})()"""


class OliveYoungAgent(LocalAgent):

    _TAG = "[oliveyoung]"
    _JS_EXTRACT_DOM = _JS_EXTRACT_DOM

    @property
    def agent_type(self) -> str:
        return "local_oliveyoung"
