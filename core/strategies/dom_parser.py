"""
dom 전략 실행기

CSS 셀렉터 기반으로 DOM 에서 직접 데이터를 추출한다.
DB 의 config JSON 에 정의된 셀렉터와 속성 매핑을 읽어 실행한다.
"""
import re

from playwright.sync_api import Page

from core.strategies.base import BaseStrategy


class DomParserStrategy(BaseStrategy):
    """CSS 셀렉터 기반 DOM 데이터 추출"""

    def extract(self, page: Page, config: dict) -> dict | list | None:
        """
        config 구조:

        [store - 단일 객체]
        {
            "selectors": {
                "store_name": {"selector": "h1.brand-title", "attr": "textContent"},
                "description": {"selector": "p.desc", "attr": "textContent"},
            }
        }

        [category - 링크 기반]
        {
            "container": ".cate-nav",
            "item_selector": "a[href]",
            "fields": {...},
            "categories_from_links": true,
        }

        [product_list - 반복 아이템]
        {
            "container": ".product-list",
            "item_selector": ".product-item",
            "fields": {
                "product_name": {"selector": ".name", "attr": "textContent"},
                "selling_price": {"selector": ".price", "attr": "textContent",
                                  "regex": "[\\d,]+"},
                "image_url": {"selector": "img", "attr": "src"},
                "product_url": {"selector": "a", "attr": "href"},
            },
            "pagination": {
                "type": "url_param",
                "param": "page",
                "max_pages": 50,
            }
        }

        [product_detail - 상세]
        {
            "selectors": {
                "description": {"selector": ".detail-content", "attr": "textContent"},
                "detail_images": {"selector": ".detail-content img",
                                  "attr": "src", "multiple": true},
            }
        }
        """
        # 단일 객체 추출 (selectors 키)
        if "selectors" in config:
            return self._extract_single(page, config["selectors"])

        # 리스트 추출 (item_selector 키)
        if "item_selector" in config:
            return self._extract_list(page, config)

        print("[dom] config 에 selectors 또는 item_selector 가 없습니다")
        return None

    # ─── 단일 객체 추출 ───────────────────────────────────────────

    def _extract_single(self, page: Page, selectors: dict) -> dict:
        """각 필드의 CSS 셀렉터로 단일 값을 추출한다."""
        result = {}
        for field, spec in selectors.items():
            try:
                result[field] = self._extract_field(page, page, spec)
            except Exception as e:
                print(f"[dom] {field} 추출 실패: {e}")
                result[field] = None
        return result

    # ─── 리스트 추출 ──────────────────────────────────────────────

    def _extract_list(self, page: Page, config: dict) -> dict | None:
        """반복 아이템에서 필드를 매핑하여 리스트로 추출한다."""
        container_sel = config.get("container", "body")
        item_sel = config.get("item_selector", "")
        fields = config.get("fields", {})

        try:
            container = page.query_selector(container_sel)
            if not container:
                container = page

            items = container.query_selector_all(item_sel) if item_sel else []
        except Exception as e:
            print(f"[dom] 아이템 셀렉터 실행 실패: {e}")
            return None

        products = []
        for item_el in items:
            product = {}
            for field, spec in fields.items():
                try:
                    product[field] = self._extract_field(page, item_el, spec)
                except Exception:
                    product[field] = None

            # 빈 상품 필터링 (이름이나 가격이 모두 없으면 스킵)
            has_content = any(
                v and str(v).strip()
                for k, v in product.items()
                if k in ("product_name", "selling_price", "name")
            )
            if has_content:
                products.append(product)

        return {
            "totalCount": len(products),
            "items": products,
        }

    # ─── 필드 단위 추출 ───────────────────────────────────────────

    def _extract_field(self, page: Page, context_el, spec: dict):
        """
        하나의 필드 스펙으로 값을 추출한다.

        spec 예시:
        {"selector": ".price", "attr": "textContent", "regex": "[\\d,]+"}
        {"selector": "img", "attr": "src", "multiple": true}
        """
        selector = spec.get("selector", "")
        attr = spec.get("attr", "textContent")
        regex = spec.get("regex")
        multiple = spec.get("multiple", False)

        if multiple:
            elements = context_el.query_selector_all(selector) if selector else []
            values = []
            for el in elements:
                val = self._get_attr(el, attr)
                if val:
                    values.append(val)
            return values

        # :self → 카드 자체의 속성을 사용 (카드가 <a> 태그인 경우 등)
        if selector == ":self":
            el = context_el
        else:
            el = context_el.query_selector(selector) if selector else context_el
        if not el:
            return None

        val = self._get_attr(el, attr)

        if val and regex:
            match = re.search(regex, val)
            val = match.group(0) if match else val

        return val

    @staticmethod
    def _get_attr(el, attr: str) -> str | None:
        """요소에서 속성 값을 가져온다."""
        try:
            if attr == "textContent":
                return (el.inner_text() or "").strip()
            elif attr == "innerHTML":
                return (el.inner_html() or "").strip()
            else:
                return el.get_attribute(attr)
        except Exception:
            return None
