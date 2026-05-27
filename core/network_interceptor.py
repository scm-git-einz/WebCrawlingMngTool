"""
네트워크 요청 인터셉터

페이지 로드 중 발생하는 XHR/Fetch 요청을 캡처하고
상품/카테고리 관련 API 엔드포인트를 자동 탐지한다.

사용법:
  interceptor = NetworkInterceptor()
  interceptor.start(page)
  page.goto(url)
  page.wait_for_timeout(5000)
  interceptor.stop(page)
  candidates = interceptor.get_api_candidates()
"""
import json
import re
from urllib.parse import urlparse, parse_qs


# ─── 분석 제외 패턴 ──────────────────────────────────────────────
_EXCLUDE_PATTERNS = [
    "analytics", "tracking", "beacon", "pixel",
    "doubleclick", "google-analytics", "facebook.com",
    "hotjar", "sentry", "datadog", "amplitude",
    "tiktok", "kakao", "criteo", "braze",
    "cloudflare", "cdn-cgi", "rum?", "gtag",
    "ads", "adservice", "adsense",
    "fonts.googleapis", "fonts.gstatic",
    ".css", ".js", ".png", ".jpg", ".gif", ".svg", ".woff",
    ".ico", ".webp", ".avif",
]

# ─── 상품 관련 키워드 (URL 경로 + 응답 필드) ──────────────────────
_PRODUCT_URL_KEYWORDS = [
    "product", "goods", "item", "catalog",
    "shop", "category", "brand", "search",
    "ranking", "best", "list", "collection",
]

_PRODUCT_FIELD_KEYWORDS = [
    "productno", "productid", "goodsno", "goodscd",
    "itemid", "itemno", "productname", "goodsnm",
    "price", "saleprice", "sellingprice",
    "imageurl", "thumbnailurl", "imgurl",
    "reviewcount", "rating", "score",
    "brandname", "categoryname",
    "discountrate", "discountprice",
]

_CATEGORY_FIELD_KEYWORDS = [
    "categoryid", "categoryno", "cateid", "catid",
    "categoryname", "catename",
    "subcategor", "children",
]

_STORE_FIELD_KEYWORDS = [
    "storename", "shopname", "brandname", "channelname",
    "storeid", "shopid", "description",
]

# ─── 페이지네이션 파라미터 패턴 ──────────────────────────────────
_PAGINATION_PARAMS = [
    "page", "pg", "p", "offset", "start",
    "cursor", "after", "next", "skip",
    "pagenum", "pagenumber", "cp",
]


class NetworkInterceptor:
    """
    Playwright 페이지 응답 리스너.
    페이지 로드 중 발생하는 JSON API 요청을 캡처·분석한다.
    """

    def __init__(self):
        self.captured: list[dict] = []
        self._handler = None

    # ─── 수집 제어 ────────────────────────────────────────────────

    def start(self, page):
        """페이지에 응답 리스너를 등록한다."""
        self.captured.clear()

        def on_response(response):
            self._handle_response(response)

        self._handler = on_response
        page.on("response", self._handler)

    def stop(self, page):
        """리스너를 해제한다."""
        if self._handler:
            try:
                page.remove_listener("response", self._handler)
            except Exception:
                pass
            self._handler = None

    # ─── 응답 처리 ────────────────────────────────────────────────

    def _handle_response(self, response):
        """개별 응답을 검사하여 JSON API 요청만 캡처한다."""
        try:
            url = response.url
            status = response.status

            # 실패 응답 무시
            if status < 200 or status >= 400:
                return

            # 제외 패턴 매칭
            url_lower = url.lower()
            for pattern in _EXCLUDE_PATTERNS:
                if pattern in url_lower:
                    return

            # Content-Type 검사
            content_type = ""
            try:
                content_type = response.headers.get("content-type", "")
            except Exception:
                pass

            if "json" not in content_type and "javascript" not in content_type:
                return

            # JSON 응답 바디 샘플 캡처
            body_sample = None
            body_parsed = None
            try:
                body_text = response.text()
                if body_text and len(body_text) > 10:
                    body_sample = body_text[:5000]
                    try:
                        body_parsed = json.loads(body_text)
                    except (json.JSONDecodeError, ValueError):
                        pass
            except Exception:
                pass

            if body_parsed is None:
                return

            parsed_url = urlparse(url)
            request = response.request
            method = request.method if request else "GET"

            # POST 요청의 body 캡처
            request_body = None
            request_headers = {}
            if request:
                try:
                    post_data = request.post_data
                    if post_data:
                        try:
                            request_body = json.loads(post_data)
                        except (json.JSONDecodeError, ValueError):
                            request_body = post_data
                except Exception:
                    pass
                try:
                    request_headers = dict(request.headers) if request.headers else {}
                except Exception:
                    pass

            self.captured.append({
                "url": url,
                "path": parsed_url.path,
                "query": parse_qs(parsed_url.query),
                "method": method,
                "status": status,
                "content_type": content_type,
                "body_sample": body_sample,
                "body_parsed": body_parsed,
                "domain": parsed_url.hostname or "",
                "request_body": request_body,
                "request_headers": request_headers,
            })

        except Exception:
            pass

    # ─── API 후보 분석 ────────────────────────────────────────────

    def get_api_candidates(self) -> list[dict]:
        """
        캡처된 요청 중 상품/카테고리 데이터를 포함하는
        API 엔드포인트 후보를 점수순으로 반환한다.
        """
        candidates = []

        for req in self.captured:
            score = 0
            target_type = None  # "product_list", "category", "store"
            analysis = {}

            body = req.get("body_parsed")
            if not body or not isinstance(body, dict):
                continue

            path_lower = req["path"].lower()
            url_lower = req["url"].lower()

            # 1. URL 경로에 상품 키워드 포함 여부
            for kw in _PRODUCT_URL_KEYWORDS:
                if kw in path_lower:
                    score += 3
                    break

            # 2. 응답 본문에서 배열 탐색 → 상품 리스트 감지
            list_info = self._find_product_list(body)
            if list_info:
                score += list_info["score"]
                target_type = "product_list"
                analysis["list_path"] = list_info["path"]
                analysis["list_length"] = list_info["length"]
                analysis["item_fields"] = list_info["item_fields"]
                analysis["field_mapping"] = list_info["field_mapping"]

                # total count 감지
                tc = self._find_total_count(body)
                if tc:
                    analysis["total_count_path"] = tc

            # 3. 카테고리 데이터 감지
            cat_info = self._find_category_data(body)
            if cat_info and cat_info["score"] > (list_info or {}).get("score", 0):
                score += cat_info["score"]
                target_type = "category"
                analysis["list_path"] = cat_info["path"]
                analysis["list_length"] = cat_info["length"]
                analysis["item_fields"] = cat_info["item_fields"]
                analysis["field_mapping"] = cat_info["field_mapping"]

            # 4. 매장 데이터 감지
            store_info = self._find_store_data(body)
            if store_info and not target_type:
                score += store_info["score"]
                target_type = "store"
                analysis["data_path"] = store_info["path"]
                analysis["field_mapping"] = store_info["field_mapping"]

            # 5. 페이지네이션 파라미터 감지
            pagination = self._detect_pagination(req)
            if pagination:
                analysis["pagination"] = pagination
                score += 2

            if score >= 5 and target_type:
                candidates.append({
                    "url": req["url"],
                    "path": req["path"],
                    "query": req["query"],
                    "method": req["method"],
                    "domain": req["domain"],
                    "score": score,
                    "target_type": target_type,
                    "analysis": analysis,
                    "request_body": req.get("request_body"),
                    "request_headers": req.get("request_headers", {}),
                })

        # 점수순 정렬
        candidates.sort(key=lambda x: x["score"], reverse=True)
        return candidates

    def get_observed_domains(self) -> list[str]:
        """캡처된 요청에서 고유 도메인 목록을 반환한다."""
        domains = set()
        for req in self.captured:
            d = req.get("domain", "")
            if d:
                domains.add(d)
        # 제외 도메인 필터
        exclude = {
            "analytics", "tracking", "beacon", "sentry",
            "datadog", "amplitude", "tiktok", "facebook",
            "google", "doubleclick", "criteo", "braze",
        }
        return [
            d for d in sorted(domains)
            if not any(ex in d.lower() for ex in exclude)
        ]

    # ─── 내부 분석 함수들 ─────────────────────────────────────────

    def _find_product_list(
        self, body: dict, path: str = "",
    ) -> dict | None:
        """
        JSON 응답에서 상품 리스트 배열을 찾는다.
        재귀적으로 탐색하며, 아이템 키 이름으로 점수를 매긴다.
        중첩된 하위 오브젝트의 필드도 포함하여 스코어링/매핑한다.
        """
        best = None

        for key, value in body.items():
            current_path = f"{path}.{key}" if path else key

            if isinstance(value, list) and len(value) >= 3:
                # 배열의 첫 번째 아이템이 딕셔너리인지 확인
                if isinstance(value[0], dict):
                    sample_item = value[0]
                    # 최상위 키 + 중첩 키(1레벨) 모두 수집하여 스코어링
                    all_keys = self._collect_item_keys(sample_item)
                    score = self._score_product_fields(all_keys)

                    if score >= 5 and (best is None or score > best["score"]):
                        best = {
                            "path": current_path,
                            "length": len(value),
                            "score": score,
                            "item_fields": list(sample_item.keys())[:30],
                            "field_mapping": self._map_product_fields_deep(
                                sample_item,
                            ),
                        }

            elif isinstance(value, dict):
                # 깊이 3까지 재귀
                if path.count(".") < 3:
                    nested = self._find_product_list(value, current_path)
                    if nested and (best is None or nested["score"] > best["score"]):
                        best = nested

        return best

    @staticmethod
    def _collect_item_keys(item: dict, prefix: str = "") -> list[str]:
        """아이템의 최상위 + 중첩 1레벨 키를 모두 수집한다."""
        keys = []
        for k, v in item.items():
            full = f"{prefix}.{k}" if prefix else k
            keys.append(full)
            if isinstance(v, dict):
                for sub_k in v:
                    keys.append(f"{full}.{sub_k}")
        return keys

    def _find_category_data(
        self, body: dict, path: str = "",
    ) -> dict | None:
        """JSON 응답에서 카테고리 배열을 찾는다."""
        best = None

        for key, value in body.items():
            current_path = f"{path}.{key}" if path else key
            key_lower = key.lower()

            # 키 이름이 카테고리 관련인 경우
            is_cat_key = any(
                kw in key_lower
                for kw in ["categor", "menu", "nav", "cate"]
            )

            if isinstance(value, list) and len(value) >= 2:
                if isinstance(value[0], dict):
                    item_keys = list(value[0].keys())
                    score = self._score_category_fields(item_keys)
                    if is_cat_key:
                        score += 5

                    if score >= 5 and (best is None or score > best["score"]):
                        best = {
                            "path": current_path,
                            "length": len(value),
                            "score": score,
                            "item_fields": item_keys[:20],
                            "field_mapping": self._map_category_fields(item_keys),
                        }

            elif isinstance(value, dict):
                if path.count(".") < 3:
                    nested = self._find_category_data(value, current_path)
                    if nested and (best is None or nested["score"] > best["score"]):
                        best = nested

        return best

    def _find_store_data(self, body: dict) -> dict | None:
        """JSON 응답에서 매장 정보를 찾는다."""
        # 플랫 키에서 매장 필드 찾기
        all_keys = self._collect_flat_keys(body, max_depth=2)
        score = 0
        mapping = {}

        for sk in _STORE_FIELD_KEYWORDS:
            for key in all_keys:
                if sk == key.lower():
                    score += 3
                    std_field = self._store_keyword_to_field(sk)
                    if std_field:
                        mapping[std_field] = key
                    break

        if score >= 6:
            return {
                "path": "",
                "score": score,
                "field_mapping": mapping,
            }
        return None

    def _find_total_count(self, body: dict, path: str = "") -> str | None:
        """totalCount, total, count 등의 키를 찾는다."""
        for key, value in body.items():
            current_path = f"{path}.{key}" if path else key
            key_lower = key.lower()

            if isinstance(value, (int, float)):
                if "total" in key_lower and ("count" in key_lower or "cnt" in key_lower):
                    return current_path
                if key_lower in ("total", "totalcount", "totalcnt", "count"):
                    return current_path

            if isinstance(value, dict) and path.count(".") < 2:
                nested = self._find_total_count(value, current_path)
                if nested:
                    return nested

        return None

    def _detect_pagination(self, req: dict) -> dict | None:
        """요청의 쿼리 파라미터에서 페이지네이션 패턴을 탐지한다."""
        query = req.get("query", {})
        for param in _PAGINATION_PARAMS:
            if param in query:
                return {
                    "type": "query_param",
                    "param": param,
                    "current_value": query[param][0] if query[param] else "1",
                }

        # URL 경로에 페이지 번호 패턴
        path = req.get("path", "")
        page_match = re.search(r"/page/(\d+)", path)
        if page_match:
            return {
                "type": "path_segment",
                "pattern": "/page/{page}",
                "current_value": page_match.group(1),
            }

        return None

    # ─── 필드 스코어링 ────────────────────────────────────────────

    @staticmethod
    def _score_product_fields(item_keys: list[str]) -> int:
        """
        아이템 키 목록이 상품 데이터일 확률을 점수로 반환한다.
        dot notation 키 (예: 'itemInfo.productName') 의 마지막 부분도 매칭.
        """
        score = 0
        # dot notation 키의 마지막 세그먼트도 포함
        keys_lower = []
        for k in item_keys:
            kl = k.lower()
            keys_lower.append(kl)
            if "." in kl:
                keys_lower.append(kl.rsplit(".", 1)[1])

        for kw in _PRODUCT_FIELD_KEYWORDS:
            for kl in keys_lower:
                if kw in kl:
                    score += 2
                    break

        # 가격 + 이름이 동시에 있으면 보너스
        has_price = any("price" in k for k in keys_lower)
        has_name = any(
            k in keys_lower
            for k in ["name", "productname", "goodsnm", "title"]
        ) or any("name" in k for k in keys_lower)
        if has_price and has_name:
            score += 5

        # ID 필드가 있으면 보너스
        has_id = any(
            k in keys_lower
            for k in ["id", "productno", "productid", "goodsno", "goodscd", "itemid"]
        )
        if has_id:
            score += 3

        return score

    @staticmethod
    def _score_category_fields(item_keys: list[str]) -> int:
        """아이템 키 목록이 카테고리 데이터일 확률을 점수로 반환한다."""
        score = 0
        keys_lower = [k.lower() for k in item_keys]

        for kw in _CATEGORY_FIELD_KEYWORDS:
            for kl in keys_lower:
                if kw in kl:
                    score += 3
                    break

        # name + id 쌍이면 보너스
        has_name = any("name" in k for k in keys_lower)
        has_id = any(k in ("id", "categoryid", "cateid") for k in keys_lower)
        if has_name and has_id:
            score += 3

        return score

    # ─── 필드 매핑 ────────────────────────────────────────────────

    _PRODUCT_FIELD_MAP = {
        "product_id": [
            "productno", "productid", "goodsno", "goodscd",
            "itemid", "itemno", "id", "no",
        ],
        "product_name": [
            "productname", "goodsnm", "goodsname", "name",
            "itemname", "title", "dispname",
        ],
        "selling_price": [
            "saleprice", "sellingprice", "sellprice", "price",
            "finalprice", "customerprice", "displayprice",
        ],
        "original_price": [
            "originprice", "normalprice", "retailprice",
            "listprice", "regularprice", "consumerprice",
            "originalprice",
        ],
        "discount_rate": [
            "discountrate", "discountratio", "discountpercent",
            "salerate",
        ],
        "image_url": [
            "representativeimageurl", "imageurl", "thumbnailurl",
            "imgurl", "mainimage", "productimage", "image",
            "thumbnailsrc", "thumbnail",
        ],
        "review_count": [
            "totalreviewcount", "reviewcount", "reviewcnt",
            "reviewamount", "commentcount",
        ],
        "brand_name": [
            "brandname", "brand", "makername", "manufacturer",
        ],
        "product_url": [
            "producturl", "goodsurl", "itemurl", "url",
            "detailurl", "link", "weblink",
        ],
    }

    @classmethod
    def _map_product_fields(cls, item_keys: list[str]) -> dict:
        """아이템 키를 표준 스키마에 매핑한다 (플랫 키만)."""
        mapping = {}
        keys_lower = {k.lower(): k for k in item_keys}

        for std_field, candidates in cls._PRODUCT_FIELD_MAP.items():
            for cand in candidates:
                if cand in keys_lower:
                    mapping[std_field] = keys_lower[cand]
                    break

        return mapping

    @classmethod
    def _map_product_fields_deep(cls, sample_item: dict) -> dict:
        """
        아이템의 중첩 구조를 포함하여 표준 스키마에 매핑한다.
        결과는 dot notation 경로 (예: "itemInfo.productName").
        값이 dict/list인 최상위 키는 스킵하고 중첩 탐색으로 처리.
        """
        # 1) 최상위 키 중 스칼라 값만 매핑 (dict/list 값은 스킵)
        scalar_keys = [
            k for k, v in sample_item.items()
            if not isinstance(v, (dict, list))
        ]
        mapping = cls._map_product_fields(scalar_keys)

        # 2) 중첩 1레벨 탐색 (dict 값의 하위 키)
        for key, value in sample_item.items():
            if not isinstance(value, dict):
                continue

            sub_keys_lower = {sk.lower(): sk for sk in value.keys()}

            for std_field, candidates in cls._PRODUCT_FIELD_MAP.items():
                if std_field in mapping:
                    continue  # 이미 매핑됨
                for cand in candidates:
                    if cand in sub_keys_lower:
                        # 하위 값도 스칼라인지 확인
                        sub_val = value.get(sub_keys_lower[cand])
                        if isinstance(sub_val, (dict, list)):
                            continue  # 여전히 복합 값이면 스킵
                        # dot notation: "itemInfo.productName"
                        mapping[std_field] = f"{key}.{sub_keys_lower[cand]}"
                        break

        return mapping

    @staticmethod
    def _map_category_fields(item_keys: list[str]) -> dict:
        """카테고리 아이템 키를 표준 스키마에 매핑한다."""
        mapping = {}
        keys_lower = {k.lower(): k for k in item_keys}

        id_candidates = ["id", "categoryid", "cateid", "catid", "categoryno"]
        for cand in id_candidates:
            if cand in keys_lower:
                mapping["id"] = keys_lower[cand]
                break

        name_candidates = ["name", "categoryname", "catename", "label", "title"]
        for cand in name_candidates:
            if cand in keys_lower:
                mapping["name"] = keys_lower[cand]
                break

        return mapping

    @staticmethod
    def _store_keyword_to_field(keyword: str) -> str | None:
        """매장 키워드를 표준 필드명으로 변환한다."""
        kw_map = {
            "storename": "store_name",
            "shopname": "store_name",
            "brandname": "store_name",
            "channelname": "store_name",
            "storeid": "store_id",
            "shopid": "store_id",
            "description": "description",
        }
        return kw_map.get(keyword)

    @staticmethod
    def _collect_flat_keys(
        obj: dict, max_depth: int = 2, prefix: str = "",
    ) -> list[str]:
        """중첩 딕셔너리의 키를 플랫하게 수집한다."""
        keys = []
        for k, v in obj.items():
            full_key = f"{prefix}.{k}" if prefix else k
            keys.append(full_key)
            if isinstance(v, dict) and max_depth > 0:
                keys.extend(
                    NetworkInterceptor._collect_flat_keys(v, max_depth - 1, full_key)
                )
        return keys
