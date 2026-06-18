"""까르띠에 상품 수집 에이전트 (cartier.com/ko-kr) — Richemont Group"""
import re
from agents.brand.base import BrandAgent

_SEARCH_BASE = "https://www.cartier.com/ko-kr/search?q={sku}&lang=ko_KR"

_JS_FIND_PRODUCT_LINK = """(() => {
    const selectors = [
        '.product-item__link',
        '.product-tile a[href*=".html"]',
        '.product-tile__link',
        '.search-results .product-item a[href*=".html"]',
        '.product-grid a[href*=".html"]',
        'a.product-name[href*=".html"]',
        '[class*="product"] a[href*=".html"]',
    ];
    for (const sel of selectors) {
        const el = document.querySelector(sel);
        if (el && el.href) return el.href;
    }
    // fallback: .html 링크 중 첫 번째 상품 링크
    const links = Array.from(document.querySelectorAll('a[href*=".html"]'));
    for (const a of links) {
        const href = a.href || '';
        if (href.includes('/ko-kr/') && !href.includes('/search')) return href;
    }
    return null;
})()"""

_DOM_PRICE_JS = """(() => {
    const results = [];
    const selectors = [
        '[itemprop="price"]',
        '[class*="price"][class*="sale"]',
        '[class*="price"][class*="current"]',
        '[class*="Price"][class*="Sale"]',
        '[class*="ProductPrice"]',
        '[class*="product-price"]',
        '[data-price]',
        '[class*="price"]',
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


class CartierAgent(BrandAgent):

    _TAG = "[cartier]"
    _DOM_PRICE_JS = _DOM_PRICE_JS

    @property
    def agent_type(self) -> str:
        return "cartier"

    def _sku_from_url(self, url: str) -> str:
        # URL 끝: -c-CRL3002220.html 또는 CRL3002220.html
        m = re.search(r"([A-Z]{2,}\d+)\.html", url)
        return m.group(1) if m else ""

    def fetch_by_sku(self, sku: str) -> dict:
        """SKU로 상품을 검색하여 가격을 수집한다."""
        self._log(f"SKU 검색 시작: {sku}")
        product_url = self._search_product_url(sku)
        if not product_url:
            return {
                "sku": sku, "url": "", "name": "", "price": "",
                "currency": "KRW", "source": "failed", "raw_api_url": "",
                "error": f"SKU '{sku}'에 해당하는 상품 URL을 찾을 수 없음",
            }
        self._log(f"상품 URL 발견: {product_url}")
        return self.fetch_product(product_url)

    def _search_product_url(self, sku: str) -> str | None:
        """까르띠에 검색 페이지에서 SKU에 해당하는 상품 URL을 반환한다."""
        search_url = _SEARCH_BASE.format(sku=sku)
        try:
            self.enable_proxy()
            self.page = self._create_page(
                cookie_domain="www.cartier.com", headless=True
            )
            resp = self._safe_goto(search_url, wait_until="domcontentloaded", timeout=60000)
            if self._is_blocked(resp):
                self._log(f"검색 페이지 차단됨 (HTTP {resp.status if resp else 'N/A'})")
                return None
            self.page.wait_for_timeout(3000)
            self._human_dwell()
            product_url = self.page.evaluate(_JS_FIND_PRODUCT_LINK)
            if not product_url:
                self._log("검색 결과에서 상품 링크를 찾지 못함")
            return product_url
        except Exception as e:
            self._log(f"검색 중 오류: {e}")
            return None
        finally:
            try:
                self.browser_mgr.close()
            except Exception:
                pass
            self.page = None
