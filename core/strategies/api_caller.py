"""
api 전략 실행기

페이지 컨텍스트에서 REST API 를 호출하고
응답 JSON 에서 필드 매핑으로 데이터를 추출한다.

브라우저의 쿠키/세션을 공유하기 위해
page.evaluate(fetch(...)) 방식으로 호출한다.
"""
import json
import re

from playwright.sync_api import Page

from core.strategies.base import BaseStrategy


class ApiCallerStrategy(BaseStrategy):
    """REST API 호출 기반 데이터 추출"""

    def extract(
        self, page: Page, config: dict, **kwargs,
    ) -> dict | list | None:
        """
        config 구조:

        [store]
        {
            "endpoint": "/api/store/info",
            "method": "GET",
            "params": {"storeId": "123"},
            "response": {
                "data_path": "data",
                "fields": {
                    "store_name": "storeName",
                    "description": "storeDesc",
                }
            }
        }

        [product_list]
        {
            "endpoint": "/api/products",
            "method": "GET",
            "params": {"page": "{page}", "size": 40},
            "response": {
                "list_path": "data.productList",
                "total_count_path": "data.totalCount",
                "fields": {
                    "product_id": "goodsCd",
                    "product_name": "goodsNm",
                }
            }
        }

        kwargs 로 동적 파라미터 치환 가능:
          page=2, cat_id="abc", product_id="123"
        """
        endpoint = config.get("endpoint", "")
        method = config.get("method", "GET").upper()
        params = dict(config.get("params", {}))
        body = dict(config.get("body", {}))
        headers = config.get("headers", {})
        response_config = config.get("response", {})

        if not endpoint:
            print("[api] endpoint 가 설정되지 않았습니다")
            return None

        # 동적 파라미터 치환 ({page}, {cat_id}, {product_id} 등)
        endpoint = self._substitute(endpoint, kwargs)
        params = {
            k: self._substitute(str(v), kwargs)
            for k, v in params.items()
        }
        body = {
            k: self._substitute(str(v), kwargs) if isinstance(v, str) else v
            for k, v in body.items()
        }

        # fetch JS 생성 및 실행
        js_code = self._build_fetch_js(endpoint, method, params, body, headers)

        try:
            raw = page.evaluate(js_code)
        except Exception as e:
            print(f"[api] fetch 실행 오류: {e}")
            return None

        if raw is None:
            print("[api] API 응답 없음")
            return None

        return self._map_response(raw, response_config)

    # ─── 파라미터 치환 ────────────────────────────────────────────

    @staticmethod
    def _substitute(text: str, kwargs: dict) -> str:
        """문자열의 {key} 플레이스홀더를 kwargs 값으로 치환한다."""
        for key, val in kwargs.items():
            text = text.replace(f"{{{key}}}", str(val))
        return text

    # ─── fetch JS 생성 ────────────────────────────────────────────

    @staticmethod
    def _build_fetch_js(
        endpoint: str, method: str, params: dict, body: dict,
        headers: dict | None = None,
    ) -> str:
        """브라우저 컨텍스트에서 실행할 fetch JS 를 생성한다."""
        # 치환되지 않은 플레이스홀더 제거
        clean_params = {
            k: v for k, v in params.items()
            if "{" not in str(v)
        }

        if method == "GET" and clean_params:
            qs_parts = []
            for k, v in clean_params.items():
                qs_parts.append(f"{k}={v}")
            qs = "&".join(qs_parts)
            url_expr = f"'{endpoint}?{qs}'"
        else:
            url_expr = f"'{endpoint}'"

        # fetch 옵션 구성
        opts_parts = [f"method: '{method}'", "credentials: 'include'"]

        if headers:
            h_json = json.dumps(headers, ensure_ascii=False)
            opts_parts.append(f"headers: {h_json}")

        if method == "POST" and body:
            body_json = json.dumps(body, ensure_ascii=False)
            if "headers" not in (headers or {}):
                opts_parts.append(
                    "headers: {'Content-Type': 'application/json'}"
                )
            opts_parts.append(f"body: JSON.stringify({body_json})")

        opts = "{ " + ", ".join(opts_parts) + " }"

        return f"""() => {{
    return fetch({url_expr}, {opts})
        .then(function(res) {{ return res.json(); }})
        .then(function(data) {{ return data; }})
        .catch(function(err) {{ return null; }});
}}"""

    # ─── 응답 매핑 ────────────────────────────────────────────────

    def _map_response(self, raw: dict, response_config: dict) -> dict | list | None:
        """API 응답에서 필드 매핑을 적용한다."""
        fields = response_config.get("fields", {})

        # 리스트 응답
        list_path = response_config.get("list_path")
        if list_path:
            items_raw = self._get_nested(raw, list_path) or []
            total_count_path = response_config.get("total_count_path")
            total_count = self._get_nested(raw, total_count_path) if total_count_path else 0

            items = []
            for item in items_raw:
                if not isinstance(item, dict):
                    continue
                mapped = {}
                for field_name, source_path in fields.items():
                    mapped[field_name] = self._get_nested(item, source_path)
                items.append(mapped)

            return {
                "totalCount": total_count or len(items),
                "items": items,
            }

        # 단일 객체 응답
        data_path = response_config.get("data_path")
        data = self._get_nested(raw, data_path) if data_path else raw

        if data is None:
            return None

        if not fields:
            return data

        result = {}
        for field_name, source_path in fields.items():
            result[field_name] = self._get_nested(data, source_path)
        return result

    @staticmethod
    def _get_nested(obj, dot_path: str):
        """dot notation 경로로 중첩 객체의 값을 가져온다."""
        if not obj or not dot_path:
            return None

        parts = dot_path.split(".")
        current = obj
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, list):
                # 배열 인덱스 접근
                try:
                    idx = int(part)
                    current = current[idx]
                except (ValueError, IndexError):
                    return None
            else:
                return None
            if current is None:
                return None
        return current
