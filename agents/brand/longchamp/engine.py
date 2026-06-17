"""롱챔프 코리아 상품 수집 에이전트 (Salesforce Commerce Cloud)"""
import re
from agents.brand.base import BrandAgent


# SFCC 표준 가격 셀렉터
_DOM_PRICE_JS = """(() => {
    const results = [];
    const selectors = [
        '.price .sales .value',
        '.price__sales .value',
        '[itemprop="price"]',
        '.prices .price',
        '.product-price .price',
        '[class*="price"][class*="sales"]',
        '[class*="price"][class*="value"]',
        '[data-price]',
    ];
    for (const sel of selectors) {
        const el = document.querySelector(sel);
        if (!el) continue;
        const text = (
            el.getAttribute('content') ||
            el.getAttribute('data-price') ||
            el.innerText || el.textContent || ''
        ).trim();
        if (text && /[\\d,]+/.test(text)) {
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


_SEARCH_BASE = "https://www.longchamp.com/kr/ko/search?q={sku}&lang=ko_KR"

_JS_EXTRACT_EXTRA = """(() => {
    const out = { brand: 'Longchamp', reference_no: '', category: '', is_new: false };

    // JSON-LD에서 sku(ref no)와 category 추출
    const scripts = document.querySelectorAll('script[type="application/ld+json"]');
    for (const s of scripts) {
        try {
            const d = JSON.parse(s.textContent);
            const items = Array.isArray(d) ? d : [d];
            for (const item of items) {
                if (!item || item['@type'] !== 'Product') continue;
                if (item.sku)      out.reference_no = item.sku;
                if (item.mpn)      out.reference_no = out.reference_no || item.mpn;
                if (item.category) out.category = Array.isArray(item.category)
                    ? item.category[item.category.length - 1]
                    : item.category;
            }
        } catch(e) {}
    }

    // category fallback: 브레드크럼 (SFCC 포함 다양한 패턴)
    if (!out.category) {
        const crumbs = document.querySelectorAll(
            '.breadcrumb a, .breadcrumbs a, ol.breadcrumb li a, ' +
            'nav[aria-label="breadcrumb"] a, ' +
            '.breadcrumb__link, .breadcrumb-item a, ' +
            '[class*="breadcrumb"] a, [class*="Breadcrumb"] a'
        );
        const cats = Array.from(crumbs).map(a => a.textContent.trim()).filter(Boolean);
        // 마지막 항목(현재 페이지)은 제외, 그 앞 항목이 카테고리
        if (cats.length > 1) out.category = cats[cats.length - 1];
    }

    // category 최후 fallback: 현재 페이지 타이틀 위 정적 텍스트
    if (!out.category) {
        const el = document.querySelector(
            '.product-breadcrumb span:last-child, ' +
            '.pdp-breadcrumb span:last-child, ' +
            '[data-cgid], [data-category-id]'
        );
        if (el) out.category = (el.getAttribute('data-cgid') || el.getAttribute('data-category-id') || el.textContent || '').trim();
    }

    // is_new: 페이지 내 신제품 관련 텍스트 탐색
    const bodyText = (document.body?.innerText || '').replace(/\s+/g, ' ');
    out.is_new = /신제품|신상품|new arrival|new in/i.test(bodyText);

    return out;
})()"""

_JS_FIND_PRODUCT_LINK = """(() => {
    const selectors = [
        '.product-item__link',
        '.product-item__inner .product-item__link',
        '.product-tile a[href*=".html"]',
        '.product-tile__link',
        'a.product-name[href*=".html"]',
        '.product-grid a[href*=".html"]',
    ];
    for (const sel of selectors) {
        const el = document.querySelector(sel);
        if (el && el.href) return el.href;
    }
    return null;
})()"""


class LongchampAgent(BrandAgent):

    _TAG = "[longchamp]"
    _DOM_PRICE_JS = _DOM_PRICE_JS

    @property
    def agent_type(self) -> str:
        return "longchamp"

    def _sku_from_url(self, url: str) -> str:
        m = re.search(r"-([A-Z0-9]+)\.html$", url, re.IGNORECASE)
        return m.group(1).upper() if m else ""

    def _extract_extra(self, result: dict) -> dict:
        """brand, reference_no, category, is_new, original_price 추출."""
        extra = {}
        try:
            data = self.page.evaluate(_JS_EXTRACT_EXTRA)
            if data:
                extra.update(data)
                self._log(f"추가 필드: ref={data.get('reference_no')} cat={data.get('category')} new={data.get('is_new')}")
        except Exception as e:
            self._log(f"추가 필드 추출 오류: {e}")
        extra['original_price'] = result.get('price', '')
        return extra

    def fetch_by_sku(self, sku: str) -> dict:
        """URL이면 바로 수집, 템플릿 있으면 조합 후 바로 수집, 없으면 검색 후 수집."""
        if sku.startswith("http"):
            self._log(f"URL 직접 수집: {sku}")
            return self.fetch_product(sku)

        template = getattr(self, '_search_url_template', '')
        if template:
            product_url = template.replace('{keyword}', sku).replace('{sku}', sku)
            self._log(f"URL 템플릿 조합 후 직접 수집: {product_url}")
            return self.fetch_product(product_url)

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
        """롱챔프 검색 페이지에서 SKU에 해당하는 상품 URL을 반환한다."""
        template = getattr(self, '_search_url_template', '') or _SEARCH_BASE
        search_url = template.replace('{keyword}', sku).replace('{sku}', sku)
        try:
            self.enable_proxy()
            self.page = self._create_page(
                cookie_domain="www.longchamp.com", headless=True
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
