"""로저비비에 상품 수집 에이전트 (rogervivier.com/kr-ko)"""
import re
from agents.brand.base import BrandAgent

# 로저비비에 가격 셀렉터
_DOM_PRICE_JS = """(() => {
    const results = [];
    const selectors = [
        '[itemprop="price"]',
        '[class*="price"][class*="sale"]',
        '[class*="price"][class*="current"]',
        '[class*="Price"][class*="Sale"]',
        '[class*="Price"][class*="Current"]',
        '[data-price]',
        '[class*="price"]',
        '[class*="Price"]',
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


class RogerVivierAgent(BrandAgent):

    _TAG = "[rogervivier]"
    _DOM_PRICE_JS = _DOM_PRICE_JS

    @property
    def agent_type(self) -> str:
        return "rogervivier"

    def _sku_from_url(self, url: str) -> str:
        # /p/{SKU}/ 패턴
        m = re.search(r"/p/([A-Z0-9]+)/?", url, re.IGNORECASE)
        return m.group(1).upper() if m else ""
