"""올리브영 상품 상세 수집 에이전트"""
from agents.local.base import LocalAgent


# 올리브영 상품 상세 페이지 DOM 셀렉터
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
        '.prd-brand a',
        '.brand a',
        '[class*="brand"] > a',
        'strong.brand',
    ]);

    // 상품명
    const name = get([
        '.prd-name',
        '[class*="prd-name"]',
        '.goods-name',
        'h1.name',
    ]);

    // 정상가 (할인 전 원가 — 취소선)
    const regular_price = get([
        '.price-1 .tx-num',
        '.price-1',
        '.origin-price .tx-num',
        '.origin-price',
        'del[class*="price"] .tx-num',
        'del[class*="price"]',
    ]);

    // 할인가 (판매가)
    const discounted_price = get([
        '.price-2 .tx-num',
        '.price-2',
        '.sale-price .tx-num',
        '.sale-price',
        '.final-price .tx-num',
        '.final-price',
    ]);

    // 할인율
    const discount_rate = get([
        '.price-3 .tx-num',
        '.price-3',
        '.discount-rate',
        '[class*="discount"][class*="rate"]',
        '[class*="badge-rate"]',
        '[class*="rate-num"]',
    ]);

    return { brand, name, regular_price, discounted_price, discount_rate };
})()"""


class OliveYoungAgent(LocalAgent):

    _TAG          = "[oliveyoung]"
    _JS_EXTRACT_DOM = _JS_EXTRACT_DOM

    @property
    def agent_type(self) -> str:
        return "local_oliveyoung"
