"""토리버치 코리아 상품 수집 에이전트 (toryburch.co.kr)"""
import re
from urllib.parse import urlparse, parse_qs
from agents.brand.base import BrandAgent

_SEARCH_BASE = "https://m.toryburch.co.kr/public/search/search/view?pageNo=1&keyword={sku}"

_JS_FIND_PRODUCT_LINK = """(() => {
    const selectors = [
        'a[href*="goodsDetail"]',
        'a[href*="godNo"]',
        '.goods-item a',
        '.product-item a',
        '.search-result-item a',
        '[class*="goods"] a',
        '[class*="product"] a',
    ];
    for (const sel of selectors) {
        const el = document.querySelector(sel);
        if (el && el.href) return el.href;
    }
    return null;
})()"""

# 한국 이커머스 스타일 가격 셀렉터
_DOM_PRICE_JS = """(() => {
    const results = [];
    const selectors = [
        '[itemprop="price"]',
        '.price .sales .value',
        '.goods-price',
        '.product-price',
        '.price_area .price',
        '.selling-price',
        '[class*="price"][class*="sale"]',
        '[class*="price"][class*="sell"]',
        '[class*="price"][class*="final"]',
        '[class*="Price"]',
        '.price',
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
            if (/[\\d,]{4,}\\s*원/.test(t) && t.length < 30) {
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


class ToryBurchAgent(BrandAgent):

    _TAG = "[toryburch]"
    _DOM_PRICE_JS = _DOM_PRICE_JS

    @property
    def agent_type(self) -> str:
        return "toryburch"

    def _sku_from_url(self, url: str) -> str:
        try:
            qs = parse_qs(urlparse(url).query)
            god_no = qs.get("godNo", [""])[0]
            if god_no:
                return god_no
        except Exception:
            pass
        m = re.search(r"godNo=([A-Z0-9]+)", url, re.IGNORECASE)
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
        # 모바일 URL → PC URL 변환
        product_url = product_url.replace("m.toryburch.co.kr", "www.toryburch.co.kr")
        self._log(f"상품 URL 발견: {product_url}")
        return self.fetch_product(product_url)

    def _search_product_url(self, sku: str) -> str | None:
        """토리버치 검색 페이지에서 SKU에 해당하는 상품 URL을 반환한다."""
        search_url = _SEARCH_BASE.format(sku=sku)
        try:
            self.enable_proxy()
            self.page = self._create_page(
                cookie_domain="m.toryburch.co.kr", headless=True
            )
            resp = self._safe_goto(search_url, wait_until="domcontentloaded", timeout=60000)
            if self._is_blocked(resp):
                self._log(f"검색 페이지 차단됨 (HTTP {resp.status if resp else 'N/A'})")
                return None
            try:
                self.page.wait_for_selector('a[href*="goodsDetail"]', timeout=10000)
            except Exception:
                self._log("상품 링크 요소 대기 타임아웃 — DOM 그대로 파싱 시도")
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
