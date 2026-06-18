"""IWC 상품 수집 에이전트 (iwc.com/kr-ko) — Richemont Group"""
import re
from agents.brand.base import BrandAgent

_DOM_PRICE_JS = """(() => {
    const results = [];
    const selectors = [
        '[itemprop="price"]',
        '[class*="Price"]',
        '[class*="price"]',
        '[data-price]',
        '[data-testid*="price"]',
    ];
    for (const sel of selectors) {
        const el = document.querySelector(sel);
        if (!el) continue;
        const text = (
            el.getAttribute('content') ||
            el.getAttribute('data-price') ||
            el.innerText || el.textContent || ''
        ).trim().replace(/\\s+/g, ' ');
        if (text && /[\\d,]+/.test(text) && text.length < 50) {
            results.push({ selector: sel, text: text });
            break;
        }
    }
    if (results.length === 0) {
        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        let node;
        while ((node = walker.nextNode())) {
            const t = node.textContent.trim();
            if (/[\\d,]{4,}/.test(t) && t.length < 30) {
                const parent = node.parentElement;
                results.push({
                    selector: parent ? (parent.className.slice(0, 60) || parent.tagName) : 'text',
                    text: t,
                });
                if (results.length >= 3) break;
            }
        }
    }
    return results;
})()"""


class IWCAgent(BrandAgent):

    _TAG = "[iwc]"
    _DOM_PRICE_JS = _DOM_PRICE_JS

    @property
    def agent_type(self) -> str:
        return "iwc"

    def _sku_from_url(self, url: str) -> str:
        # 마지막 경로 세그먼트에서 iw+숫자 추출
        # 예: iw328301-pilots-watch-mark-xx → iw328301
        m = re.search(r"/(iw\d+)", url, re.IGNORECASE)
        return m.group(1).lower() if m else ""
