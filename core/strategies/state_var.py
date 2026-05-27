"""
state_var 전략 실행기

window 전역 변수(예: __PRELOADED_STATE__)에 저장된 JSON 데이터에서
DB 의 필드 매핑 설정을 읽어 JS 코드를 동적 생성하고 page.evaluate() 로 실행한다.

주의: Playwright evaluate 컨텍스트 호환을 위해
      ?. (optional chaining) 과 ?? (nullish coalescing) 를 사용하지 않는다.
      대신 && 체이닝과 || 폴백을 사용한다.
"""
from playwright.sync_api import Page

from core.strategies.base import BaseStrategy


class StateVarStrategy(BaseStrategy):
    """window 전역 변수 기반 데이터 추출"""

    def extract(self, page: Page, config: dict) -> dict | list | None:
        """
        config 구조 (target 에 따라 다름):

        [store / product_detail]
        {
            "state_var": "__PRELOADED_STATE__",
            "root_key": "channel",             # 또는 root_keys: [...]
            "fields": {"store_name": "channelName", ...},
            "dom_fallback": {"store_name": "title"}  # 선택
        }

        [category]
        {
            "state_var": "__PRELOADED_STATE__",
            "root_key": "categoryMenu",
            "list_key": "firstCategories",
            "fields": {"id": "categoryId", "name": "categoryName"}
        }

        [product_list]
        {
            "state_var": "__PRELOADED_STATE__",
            "root_key": "categoryProducts",
            "list_key": "simpleProducts",
            "total_count_key": "totalCount",
            "fields": {"product_id": "productNo", ...}
        }
        """
        state_var = config.get("state_var", "__PRELOADED_STATE__")

        # root_keys (배열) 또는 root_key (단일)
        root_keys = config.get("root_keys")
        if root_keys:
            return self._extract_multi_root(page, state_var, root_keys, config)

        root_key = config.get("root_key", "")
        list_key = config.get("list_key")

        if list_key:
            return self._extract_list(page, state_var, root_key, list_key, config)
        else:
            return self._extract_object(page, state_var, root_key, config)

    # ─── 단일 객체 추출 (store 등) ────────────────────────────────

    def _extract_object(
        self, page: Page, state_var: str, root_key: str, config: dict,
    ) -> dict | None:
        """루트 키 하위의 단일 객체에서 필드를 추출한다."""
        fields = config.get("fields", {})
        js_code = self._build_object_js(state_var, root_key, fields)

        try:
            data = page.evaluate(js_code)
        except Exception as e:
            print(f"[state_var] JS 실행 오류: {e}")
            data = None

        # DOM 폴백
        if data is None or all(v is None for v in data.values()):
            dom_fallback = config.get("dom_fallback", {})
            if dom_fallback:
                data = data or {}
                data = self._apply_dom_fallback(page, data, dom_fallback)

        return data

    # ─── 리스트 추출 (category, product_list 등) ──────────────────

    def _extract_list(
        self, page: Page, state_var: str, root_key: str,
        list_key: str, config: dict,
    ) -> dict | list | None:
        """루트 키 하위의 배열에서 필드를 매핑하여 추출한다."""
        fields = config.get("fields", {})
        total_count_key = config.get("total_count_key")

        js_code = self._build_list_js(
            state_var, root_key, list_key, fields, total_count_key,
        )

        try:
            return page.evaluate(js_code)
        except Exception as e:
            print(f"[state_var] JS 실행 오류: {e}")
            return None

    # ─── 멀티 루트 추출 (product_detail 등) ───────────────────────

    def _extract_multi_root(
        self, page: Page, state_var: str, root_keys: list, config: dict,
    ) -> dict | None:
        """여러 루트 키를 순서대로 시도하여 첫 번째 성공한 결과를 반환한다."""
        fields = config.get("fields", {})
        js_code = self._build_multi_root_js(state_var, root_keys, fields)

        try:
            data = page.evaluate(js_code)
        except Exception as e:
            print(f"[state_var] JS 실행 오류: {e}")
            data = None

        # DOM 폴백 (상세 페이지용)
        if data is None:
            dom_fallback = config.get("dom_fallback", [])
            if dom_fallback:
                data = self._apply_detail_dom_fallback(page, dom_fallback)

        return data

    # ═══════════════════════════════════════════════════════════════
    # JS 코드 생성
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    def _dot_path_js(obj_var: str, dot_path: str) -> str:
        """
        'a.b.c' → && 체이닝으로 안전 접근하는 JS 표현식을 반환한다.
        예: _dot_path_js('ch', 'a.b.c')
            → '(ch && ch.a && ch.a.b && ch.a.b.c)'
        """
        parts = dot_path.split(".")
        exprs = [obj_var]
        current = obj_var
        for part in parts:
            current = f"{current}.{part}"
            exprs.append(current)
        return "(" + " && ".join(exprs) + ")"

    @classmethod
    def _resolve_js(cls, obj_var: str, field_spec) -> str:
        """
        field_spec 이 문자열이면 단일 경로,
        리스트이면 폴백 체인(|| 연결) JS 를 반환한다.
        """
        if isinstance(field_spec, list):
            exprs = [cls._dot_path_js(obj_var, p) for p in field_spec]
            return "(" + " || ".join(exprs) + ")"
        return cls._dot_path_js(obj_var, field_spec)

    @classmethod
    def _build_object_js(
        cls, state_var: str, root_key: str, fields: dict,
    ) -> str:
        """단일 객체 추출 JS 를 생성한다."""
        lines = [
            f"var state = window.{state_var};",
            f"if (!state || !state.{root_key}) return null;",
            f"var obj = state.{root_key};",
            "return {",
        ]
        for key, spec in fields.items():
            expr = cls._resolve_js("obj", spec)
            lines.append(f"    {key}: {expr} || null,")
        lines.append("};")

        body = "\n".join(f"    {line}" for line in lines)
        return f"() => {{\n{body}\n}}"

    @classmethod
    def _build_list_js(
        cls, state_var: str, root_key: str, list_key: str,
        fields: dict, total_count_key: str | None,
    ) -> str:
        """리스트 추출 JS 를 생성한다."""
        lines = [
            f"var state = window.{state_var};",
            f"if (!state || !state.{root_key}) return null;",
            f"var container = state.{root_key};",
            f"var items = container.{list_key} || [];",
        ]

        # 개별 아이템 매핑
        map_fields = []
        for key, spec in fields.items():
            expr = cls._resolve_js("item", spec)
            map_fields.append(f"            {key}: {expr} || null,")

        map_body = "\n".join(map_fields)

        if total_count_key:
            lines.append("return {")
            lines.append(f"    totalCount: container.{total_count_key} || 0,")
            lines.append("    items: items.map(function(item) {")
            lines.append("        return {")
            lines.append(f"{map_body}")
            lines.append("        };")
            lines.append("    }),")
            lines.append("};")
        else:
            lines.append("return items.map(function(item) {")
            lines.append("    return {")
            lines.append(f"{map_body}")
            lines.append("    };")
            lines.append("});")

        body = "\n".join(f"    {line}" for line in lines)
        return f"() => {{\n{body}\n}}"

    @classmethod
    def _build_multi_root_js(
        cls, state_var: str, root_keys: list, fields: dict,
    ) -> str:
        """여러 루트 키를 순서대로 시도하는 JS 를 생성한다."""
        lines = [f"var state = window.{state_var};"]
        lines.append("if (!state) return null;")

        for root_key in root_keys:
            safe_var = root_key.replace("-", "_").replace(".", "_")
            lines.append(f"var {safe_var} = state.{root_key};")
            lines.append(
                f"if ({safe_var} && typeof {safe_var} === 'object'"
                f" && !({safe_var}.A !== undefined"
                f" && Object.keys({safe_var}).length === 1)) {{"
            )
            lines.append(f"    var obj = {safe_var};")
            lines.append("    return {")
            for key, spec in fields.items():
                expr = cls._resolve_js("obj", spec)
                lines.append(f"        {key}: {expr} || null,")
            lines.append("    };")
            lines.append("}")

        lines.append("return null;")
        body = "\n".join(f"    {line}" for line in lines)
        return f"() => {{\n{body}\n}}"

    # ═══════════════════════════════════════════════════════════════
    # DOM 폴백
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    def _apply_dom_fallback(
        page: Page, data: dict, fallback: dict,
    ) -> dict:
        """DOM 에서 폴백 값을 채운다. 예: {"store_name": "title"}"""
        for field, source in fallback.items():
            if data.get(field) is None or data.get(field) == "N/A":
                try:
                    if source == "title":
                        val = page.title() or ""
                        if val:
                            data[field] = val.split(":")[0].strip()
                    else:
                        el = page.query_selector(source)
                        if el:
                            data[field] = el.inner_text().strip()
                except Exception:
                    pass
        return data

    @staticmethod
    def _apply_detail_dom_fallback(
        page: Page, selectors: list,
    ) -> dict | None:
        """상세 페이지 DOM 폴백: 셀렉터 목록을 순서대로 시도한다."""
        for selector in selectors:
            try:
                el = page.query_selector(selector)
                if el:
                    imgs = el.query_selector_all("img")
                    img_urls = []
                    for img in imgs:
                        src = img.get_attribute("src") or ""
                        if src and "icon" not in src.lower():
                            img_urls.append(src)
                    return {
                        "description": (el.inner_text() or "")[:2000],
                        "detail_images": img_urls,
                    }
            except Exception:
                continue
        return None
