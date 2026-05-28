"""
상품/랭킹 수집 에이전트 (v2) — Config 구동 방식

UI에서 설정한 수집 필드·페이지네이션·범위에 따라 동작한다.
기존 v1의 '플랫폼 감지 → 전략 선택' 2단계 대신,
페이지 구조 직접 분석(API → JS전역변수 → DOM) 1단계로 단순화.

수집 파이프라인:
  1. config 로드 + 정규화
  2. 브라우저 시작 + 네트워크 캡처 + 페이지 접속
  3. 페이지 구조 분석 (API JSON / JS 전역변수 / DOM 패턴)
  4. 상품 목록 수집 (scroll / click / api / none)
  5. (선택) 상품 상세 수집
  6. 필드 필터링 + 정규화 + 저장
"""
import json
import os
import re
import time
from datetime import datetime
from urllib.parse import urlparse, urlencode, parse_qs, urlunparse

from core.base_agent import BaseAgent, DEFAULT_SETTINGS
from core.network_interceptor import NetworkInterceptor


_TAG = "[product]"

_DEFAULT_FIELDS = ["name", "price", "brand", "image"]

# 상세 페이지 수집 가능 필드 정의
DETAIL_FIELD_DEFS = [
    {"key": "category_breadcrumb", "label": "카테고리 경로"},
    {"key": "reference_code",      "label": "레퍼런스코드"},
    {"key": "product_code",        "label": "상품코드"},
    {"key": "regular_price_usd",   "label": "정상가(달러)"},
    {"key": "regular_price_krw",   "label": "정상가(원화)"},
    {"key": "discount_rate",       "label": "할인율"},
    {"key": "sale_price_usd",      "label": "판매가(달러)"},
    {"key": "sale_price_krw",      "label": "판매가(원화)"},
    {"key": "max_benefit_info",    "label": "최대혜택가(프로모션)"},
    {"key": "benefits",            "label": "구매혜택"},
    {"key": "related_products",    "label": "관련상품"},
    {"key": "description",         "label": "상품설명"},
    {"key": "detail_images",       "label": "상세이미지"},
    {"key": "spec",                "label": "제품스펙"},
]

# products.json에서 제외할 상세 전용 필드 (대용량)
_DETAIL_ONLY_KEYS = ("description", "detail_images", "spec", "benefits",
                     "related_products", "max_benefit_info")

# 상품 데이터 키 이름 → 표준 필드 매핑
_FIELD_ALIASES = {
    "name": ["name", "product_name", "productName", "goodsNm", "title",
             "item_name", "itemName", "prdNm"],
    "price": ["price", "selling_price", "sellingPrice", "salePrice",
              "sale_price", "finalPrice", "displayPrice"],
    "original_price": ["original_price", "originalPrice", "normalPrice",
                       "listPrice", "regularPrice", "consumer_price"],
    "brand": ["brand", "brand_name", "brandName", "brandNm", "manufacturer"],
    "image": ["image", "image_url", "imageUrl", "representativeImageUrl",
              "thumbUrl", "thumbnail", "img", "imgUrl", "productImage"],
    "rank": ["rank", "ranking", "display_order", "displayOrder", "seq"],
    "discount_rate": ["discount_rate", "discountRate", "discountPercent",
                      "benefitRate"],
    "gift": ["gift", "giftDesc", "freeGift", "benefit"],
    "reference_no": ["reference_no", "referenceNo", "modelNo", "productCode",
                     "goodsCd", "itemNo", "sku"],
    "category": ["category", "categoryName", "category_name", "cateName"],
    "product_url": ["product_url", "productUrl", "url", "link", "detailUrl"],
    "product_id": ["product_id", "productId", "productNo", "goodsNo",
                   "itemId", "id"],
}


class ProductAgent(BaseAgent):
    """상품/랭킹 수집 에이전트 (v2) — Config 구동"""

    @property
    def agent_type(self) -> str:
        return "product"

    # ══════════════════════════════════════════════════════════════
    # UI → Agent config 변환
    # ══════════════════════════════════════════════════════════════

    def _normalize_config(self, crawl_cfg: dict) -> dict:
        """UI crawl_config → Agent 내부 config 변환.

        UI 필드:
          collect_fields, optional_fields  → 리스트 (공백 구분 문자열도 허용)
          extra_fields                     → URL 분석으로 발견된 추가 필드
                                             [{raw_key, standard_key, label}, ...]
          list_type, pagination, max_pages, max_items, detail_page
        """
        cfg = dict(crawl_cfg)

        # collect_fields / optional_fields: 공백 구분 문자열이면 리스트로 변환
        for key in ("collect_fields", "optional_fields"):
            val = cfg.get(key)
            if isinstance(val, str):
                cfg[key] = val.split() if val.strip() else []

        cfg.setdefault("collect_fields", list(_DEFAULT_FIELDS))
        cfg.setdefault("optional_fields", [])
        cfg.setdefault("list_type", "catalog")
        cfg.setdefault("pagination", "scroll")
        cfg.setdefault("max_pages", 5)
        cfg.setdefault("detail_page", False)
        cfg.setdefault("extra_fields", [])
        cfg.setdefault("detail_fields", [])
        # detail_page=true인데 detail_fields가 비어 있으면 전체 필드 수집
        if cfg.get("detail_page") and not cfg["detail_fields"]:
            cfg["detail_fields"] = [{"key": f["key"]} for f in DETAIL_FIELD_DEFS]

        if cfg.pop("item_limit_type", None) == "all":
            cfg["max_items"] = 0
        cfg.setdefault("max_items", 100)

        for k in ("max_pages", "max_items"):
            if isinstance(cfg[k], str):
                cfg[k] = int(cfg[k]) if cfg[k].isdigit() else 5

        return cfg

    # ══════════════════════════════════════════════════════════════
    # 메인 파이프라인
    # ══════════════════════════════════════════════════════════════

    def run_site(self, site_id: int):
        site = self.db.get_site(site_id)
        if not site:
            _log(f"사이트 ID={site_id} 를 찾을 수 없습니다")
            return

        result_id = self.db.create_result(site_id)
        t0 = time.time()
        cfg = self._normalize_config(self.get_crawl_config(site))
        self._cfg = cfg  # _apply_detail()에서 detail_fields 참조용
        url = site["site_url"]

        _log(f"수집 시작: {site['site_name']}  type={cfg['list_type']}  "
             f"pagination={cfg['pagination']}")

        try:
            # 1) 브라우저 + 네트워크 캡처 + 페이지 접속
            cookie_domain = self._get_cookie_domain(url)
            interceptor = NetworkInterceptor()
            self.page = self.browser_mgr.create(cookie_domain=cookie_domain)
            interceptor.start(self.page)

            resp = self._safe_goto(url)
            if self._is_blocked(resp):
                raise RuntimeError(f"차단됨 (HTTP {resp.status})")

            self.page.wait_for_timeout(DEFAULT_SETTINGS["initial_wait_ms"])
            self._human_dwell()
            self._human_scroll()

            interceptor.stop(self.page)
            captured = list(interceptor.captured)
            _log(f"네트워크 요청 {len(captured)}건 캡처")

            # 2) 페이지 구조 분석
            detection = self._detect_page_structure(captured)
            _log(f"탐지 결과: method={detection['method']}, "
                 f"초기 상품={len(detection.get('products', []))}건")

            # 3) 상품 목록 수집
            products = self._collect_products(cfg, detection)

            # 4) 상품 상세 수집 (선택)
            if cfg.get("detail_page") and products:
                products = self._collect_details(products, site)

            # 5) 필드 정규화 + 필터링
            products = self._normalize_products(products, cfg)

            # 6) 저장
            elapsed = time.time() - t0
            self.db.update_result(
                result_id, status="success",
                store_info={"site_name": site["site_name"]},
                products=products,
                product_count=len(products),
                elapsed_sec=elapsed,
            )
            self._save_json(site, products)
            _log(f"수집 완료: {len(products)}개 상품, {elapsed:.1f}초")

        except Exception as e:
            elapsed = time.time() - t0
            self.db.update_result(
                result_id, status="failed",
                error_msg=str(e), elapsed_sec=elapsed,
            )
            _log(f"수집 실패: {e}")

        finally:
            self.browser_mgr.close()
            self.page = None

    # ══════════════════════════════════════════════════════════════
    # 페이지 구조 분석 (API → JS전역변수 → DOM)
    # ══════════════════════════════════════════════════════════════

    def _detect_page_structure(self, captured: list) -> dict:
        detection = self._try_api_detection(captured)
        if detection:
            return detection

        detection = self._try_state_var_detection()
        if detection:
            return detection

        detection = self._try_dom_detection()
        if detection:
            return detection

        _log("자동 탐지 실패 — 빈 결과로 진행")
        return {"method": "none", "products": []}

    def _try_api_detection(self, captured: list) -> dict | None:
        """네트워크 캡처에서 상품 JSON API를 찾는다."""
        best = None
        best_count = 0

        for entry in captured:
            body = entry.get("body")
            if not body or not isinstance(body, (dict, list)):
                continue

            items = _find_product_array(body)
            if items and len(items) > best_count:
                best_count = len(items)
                best = {
                    "method": "api",
                    "products": items[:200],
                    "api_url": entry.get("url", ""),
                    "api_method": entry.get("method", "GET"),
                }

        if best and best_count >= 3:
            _log(f"API 탐지: {best_count}개 상품, URL={best['api_url'][:80]}")
            return best
        return None

    def _try_state_var_detection(self) -> dict | None:
        """JS 전역변수에서 상품 배열을 찾는다."""
        try:
            result = self.page.evaluate(_JS_FIND_STATE_PRODUCTS)
        except Exception:
            return None

        if not result or not result.get("items"):
            return None

        items = result["items"]
        _log(f"JS 전역변수 탐지: {result['source']}, {len(items)}개 상품")
        return {
            "method": "state_var",
            "products": items[:200],
            "source": result["source"],
            "path_keys": result.get("pathKeys", []),
        }

    def _try_dom_detection(self) -> dict | None:
        """DOM 반복 패턴에서 상품 카드를 찾는다."""
        try:
            result = self.page.evaluate(_JS_FIND_DOM_PRODUCTS)
        except Exception:
            return None

        if not result or not result.get("items"):
            return None

        items = result["items"]
        _log(f"DOM 탐지: {len(items)}개 상품 카드")
        return {
            "method": "dom",
            "products": items,
            "card_selector": result.get("selector", ""),
        }

    # ══════════════════════════════════════════════════════════════
    # 상품 목록 수집 (페이지네이션별 분기)
    # ══════════════════════════════════════════════════════════════

    def _collect_products(self, cfg: dict, detection: dict) -> list:
        pagination = cfg.get("pagination", "none")
        max_pages = cfg.get("max_pages", 5)
        max_items = cfg.get("max_items", 0)
        initial = detection.get("products", [])

        if pagination == "scroll":
            products = self._paginate_scroll(detection, initial, max_pages, max_items)
        elif pagination == "click":
            products = self._paginate_click(detection, initial, max_pages, max_items)
        elif pagination == "api" and detection.get("method") == "api":
            products = self._paginate_api(detection, initial, max_pages, max_items)
        else:
            products = list(initial)

        if max_items > 0 and len(products) > max_items:
            products = products[:max_items]

        return products

    def _paginate_scroll(self, detection, initial, max_pages, max_items):
        """무한 스크롤로 상품을 추가 수집한다."""
        products = list(initial)
        seen = _build_seen_set(products)

        for page_idx in range(max_pages):
            self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            self.page.wait_for_timeout(2000)

            new_items = self._re_extract(detection)
            added = 0
            for item in new_items:
                key = _product_key(item)
                if key and key not in seen:
                    seen.add(key)
                    products.append(item)
                    added += 1

            _log(f"스크롤 {page_idx+1}: +{added}, 총 {len(products)}")

            if added == 0:
                break
            if max_items > 0 and len(products) >= max_items:
                break

        return products

    def _paginate_click(self, detection, initial, max_pages, max_items):
        """다음 페이지 버튼 클릭으로 상품을 수집한다."""
        products = list(initial)
        seen = _build_seen_set(products)

        next_selectors = [
            "a[class*='next']", "button[class*='next']",
            "[class*='btn_next']", "[aria-label='Next']",
            "[aria-label='next']", ".pagination .next",
            "a:has(> [class*='ico_next'])",
        ]

        for page_idx in range(1, max_pages):
            clicked = False
            for sel in next_selectors:
                try:
                    btn = self.page.query_selector(sel)
                    if btn and btn.is_visible():
                        btn.click()
                        self.page.wait_for_timeout(DEFAULT_SETTINGS["page_wait_ms"])
                        clicked = True
                        break
                except Exception:
                    continue

            if not clicked:
                _log(f"다음 버튼 없음 → 페이지 {page_idx}에서 종료")
                break

            new_items = self._re_extract(detection)
            added = 0
            for item in new_items:
                key = _product_key(item)
                if key and key not in seen:
                    seen.add(key)
                    products.append(item)
                    added += 1

            _log(f"페이지 {page_idx+1}: +{added}, 총 {len(products)}")

            if added == 0:
                break
            if max_items > 0 and len(products) >= max_items:
                break

            self._delay()

        return products

    def _paginate_api(self, detection, initial, max_pages, max_items):
        """API 페이지 파라미터를 증가시키며 수집한다."""
        products = list(initial)
        seen = _build_seen_set(products)
        api_url = detection.get("api_url", "")

        if not api_url:
            return products

        for page_idx in range(1, max_pages):
            paged_url = _increment_page_param(api_url, page_idx + 1)
            _log(f"API 페이지 {page_idx+1}: {paged_url[:80]}")

            try:
                raw = self.page.evaluate(f"""
                    async () => {{
                        const r = await fetch("{_js_escape(paged_url)}", {{
                            credentials: 'include',
                            headers: {{'Accept': 'application/json'}}
                        }});
                        return await r.json();
                    }}
                """)
            except Exception as e:
                _log(f"API 호출 실패: {e}")
                break

            items = _find_product_array(raw) if raw else []
            if not items:
                _log("API 결과 없음 → 종료")
                break

            added = 0
            for item in items:
                key = _product_key(item)
                if key and key not in seen:
                    seen.add(key)
                    products.append(item)
                    added += 1

            _log(f"API 페이지 {page_idx+1}: +{added}, 총 {len(products)}")

            if added == 0:
                break
            if max_items > 0 and len(products) >= max_items:
                break

            self._delay()

        return products

    def _re_extract(self, detection: dict) -> list:
        """현재 페이지 상태에서 상품을 다시 추출한다."""
        method = detection.get("method", "none")

        if method == "state_var":
            try:
                result = self.page.evaluate(_JS_FIND_STATE_PRODUCTS)
                return (result or {}).get("items", [])
            except Exception:
                pass

        if method == "dom" or method == "state_var":
            try:
                result = self.page.evaluate(_JS_FIND_DOM_PRODUCTS)
                return (result or {}).get("items", [])
            except Exception:
                pass

        return []

    # ══════════════════════════════════════════════════════════════
    # 상품 상세 수집
    # ══════════════════════════════════════════════════════════════

    def _collect_details(self, products: list, site: dict) -> list:
        """상품 상세 페이지를 방문하여 추가 정보를 수집한다.

        URL이 있으면 직접 이동, 없으면 카드 클릭(product_id/image)으로 이동.
        """
        _log(f"상세 수집 대상: {len(products)}개")
        base_url = site["site_url"].rstrip("/")
        list_url = self.page.url

        for i, prod in enumerate(products, 1):
            url = _resolve_product_url(prod, base_url)
            name_preview = _safe(str(prod.get("name", ""))[:30])

            if url:
                # ── URL 기반 상세 이동 ──
                _log(f"[{i}/{len(products)}] {name_preview}")
                try:
                    resp = self._safe_goto(url)
                    if self._is_blocked(resp):
                        continue
                    self._human_dwell()
                    self._apply_detail(prod)
                except Exception as e:
                    _log(f"  상세 오류: {e}")
            else:
                # ── 카드 클릭 기반 상세 이동 (javascript: 링크 대응) ──
                product_id = prod.get("product_id", "")
                image_url = prod.get("image", "")
                if not product_id and not image_url:
                    continue

                _log(f"[{i}/{len(products)}] {name_preview} (클릭)")
                try:
                    before_url = self.page.url
                    clicked = self.page.evaluate(
                        _JS_CLICK_CARD,
                        {"productId": product_id, "imageUrl": image_url})
                    if not clicked:
                        _log("  카드 클릭 실패")
                        continue

                    # 페이지 전환 대기
                    self.page.wait_for_timeout(2000)
                    try:
                        self.page.wait_for_load_state(
                            "domcontentloaded", timeout=10000)
                    except Exception:
                        pass

                    current_url = self.page.url
                    if current_url != before_url:
                        prod["product_url"] = current_url
                        self._human_dwell()
                        self._apply_detail(prod)

                        # 목록 페이지로 복귀
                        self.page.go_back()
                        self.page.wait_for_timeout(1500)
                        try:
                            self.page.wait_for_load_state(
                                "domcontentloaded", timeout=10000)
                        except Exception:
                            pass
                    else:
                        _log("  페이지 전환 없음")

                except Exception as e:
                    _log(f"  상세 오류: {e}")
                    try:
                        self._safe_goto(list_url)
                        self.page.wait_for_timeout(2000)
                    except Exception:
                        pass

            if i < len(products):
                self._delay()

        _log("상세 수집 완료")
        return products

    def _apply_detail(self, prod: dict):
        """현재 페이지에서 상세 정보를 추출하여 prod에 반영한다.

        detail_fields 설정에 따라 수집할 필드를 제한한다.
        미설정 시 기본 3종(description, detail_images, spec)만 수집.
        """
        detail = self.page.evaluate(_JS_EXTRACT_DETAIL)
        if not detail:
            return

        # 수집할 상세 필드 목록 결정
        detail_fields = getattr(self, "_cfg", {}).get("detail_fields", [])
        if not detail_fields:
            detail_fields = [{"key": f["key"]} for f in DETAIL_FIELD_DEFS]

        active_keys = {f["key"] if isinstance(f, dict) else f
                       for f in detail_fields}

        for key in active_keys:
            val = detail.get(key)
            if not val:
                continue
            if key == "description":
                prod["description"] = val[:2000]
            elif key == "detail_images":
                prod["detail_images"] = val[:20]
            elif key == "spec":
                prod["spec"] = val
            elif key == "related_products":
                prod["related_products"] = val[:20] if isinstance(val, list) else val
            elif key == "max_benefit_info":
                prod["max_benefit_info"] = val[:1000] if isinstance(val, str) else val
            elif isinstance(val, str):
                prod[key] = val[:500]
            elif isinstance(val, list):
                prod[key] = val[:20]
            else:
                prod[key] = val

        # description 자동 생성 (spec 기반 fallback)
        if "description" in active_keys and not prod.get("description"):
            spec = detail.get("spec")
            if spec:
                prod["description"] = " | ".join(
                    f"{k}: {v}" for k, v in list(spec.items())[:5]
                )[:500]

    # ══════════════════════════════════════════════════════════════
    # 필드 정규화 + 필터링
    # ══════════════════════════════════════════════════════════════

    def _normalize_products(self, products: list, cfg: dict) -> list:
        """수집된 상품 데이터를 표준 필드로 정규화하고 필터링한다.

        keep_fields = collect_fields + optional_fields + extra_fields(standard_key)
        extra_fields는 raw_key → standard_key 매핑으로 값을 추출한다.
        """
        keep_fields = set(cfg.get("collect_fields", _DEFAULT_FIELDS))
        keep_fields.update(cfg.get("optional_fields", []))
        keep_fields.update(["product_url", "product_id"])

        # extra_fields: URL 분석으로 발견된 추가 필드
        extra_fields = cfg.get("extra_fields", [])
        extra_raw_map = {}  # standard_key → raw_key
        for ef in extra_fields:
            std_key = ef.get("standard_key", "")
            raw_key = ef.get("raw_key", "")
            if std_key:
                keep_fields.add(std_key)
                if raw_key:
                    extra_raw_map[std_key] = raw_key

        result = []
        for i, raw in enumerate(products, 1):
            normalized = {"rank": i}

            # 표준 필드 매핑 (_FIELD_ALIASES 기반)
            for std_field, aliases in _FIELD_ALIASES.items():
                if std_field not in keep_fields:
                    continue
                for alias in aliases:
                    val = raw.get(alias)
                    if val is not None and val != "":
                        normalized[std_field] = val
                        break

            # extra_fields: raw_key로 직접 매핑
            for std_key, raw_key in extra_raw_map.items():
                if std_key in normalized:
                    continue
                # "parent.child" 형태의 중첩 키 지원
                if "." in raw_key:
                    parts = raw_key.split(".", 1)
                    parent = raw.get(parts[0])
                    if isinstance(parent, dict):
                        val = parent.get(parts[1])
                        if val is not None and val != "":
                            normalized[std_key] = val
                else:
                    val = raw.get(raw_key)
                    if val is not None and val != "":
                        normalized[std_key] = val

            if not normalized.get("name") and not normalized.get("price"):
                continue

            normalized["collected_at"] = datetime.now().strftime(
                "%Y-%m-%dT%H:%M:%S"
            )

            # 상세 수집 필드 전달
            for dk in ("description", "detail_images", "spec",
                       "category_breadcrumb", "reference_code", "product_code",
                       "regular_price_usd", "regular_price_krw",
                       "discount_rate", "sale_price_usd", "sale_price_krw",
                       "max_benefit_info",
                       "benefits", "related_products"):
                if raw.get(dk):
                    normalized[dk] = raw[dk]

            result.append(normalized)

        return result

    # ══════════════════════════════════════════════════════════════
    # 결과 저장
    # ══════════════════════════════════════════════════════════════

    @staticmethod
    def _save_json(site: dict, products: list):
        """수집 결과를 3개 파일로 저장한다.

        - products.json        : 기본 상품 목록 (상세 정보 제외)
        - product_details.json : 전체 상품 + 상세 정보 (description, detail_images)
        - crawl_result.json    : 메타데이터 + 요약 통계
        """
        site_name = site["site_name"].replace(" ", "_")
        output_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "output", f"{site['id']}_{site_name}",
        )
        os.makedirs(output_dir, exist_ok=True)

        # 기본 상품 목록 (대용량 상세 정보 제외)
        basic_products = []
        for p in products:
            basic = {k: v for k, v in p.items() if k not in _DETAIL_ONLY_KEYS}
            basic_products.append(basic)

        detail_count = sum(
            1 for p in products
            if p.get("description") or p.get("detail_images") or p.get("spec")
               or p.get("reference_code") or p.get("regular_price_usd")
        )

        result = {
            "crawl_meta": {
                "site_name": site["site_name"],
                "site_url": site["site_url"],
                "crawl_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "agent_version": "v2",
            },
            "total_products": len(products),
            "detail_collected": detail_count,
        }

        for path, data in [
            (os.path.join(output_dir, "products.json"), basic_products),
            (os.path.join(output_dir, "product_details.json"), products),
            (os.path.join(output_dir, "crawl_result.json"), result),
        ]:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

        _log(f"파일 저장: {output_dir}")


# ══════════════════════════════════════════════════════════════════
# JS 스니펫: 전역변수에서 상품 배열 탐색
# ══════════════════════════════════════════════════════════════════

_JS_FIND_STATE_PRODUCTS = """(() => {
    const GLOBALS = [
        '__NEXT_DATA__','__PRELOADED_STATE__','__INITIAL_STATE__',
        '__NUXT__','__pinia','__remixContext'
    ];
    const NAME_RE  = /name|title|product|goods|item/i;
    const PRICE_RE = /price|cost|amount|sell/i;

    function isProductLike(obj) {
        if (!obj || typeof obj !== 'object') return false;
        var ks = Object.keys(obj).join(' ');
        return NAME_RE.test(ks) && PRICE_RE.test(ks);
    }

    function findArrays(obj, depth, pathKeys) {
        if (depth > 6 || !obj || typeof obj !== 'object') return [];
        var results = [];
        if (Array.isArray(obj)) {
            if (obj.length >= 3 && isProductLike(obj[0])) {
                results.push({pathKeys: pathKeys, count: obj.length});
            }
            return results;
        }
        var keys = Object.keys(obj);
        for (var i = 0; i < keys.length; i++) {
            try {
                var child = obj[keys[i]];
                if (child && typeof child === 'object') {
                    var found = findArrays(child, depth + 1,
                                           pathKeys.concat(keys[i]));
                    results = results.concat(found);
                }
            } catch(e) {}
        }
        return results;
    }

    function getByPath(root, keys) {
        var cur = root;
        for (var i = 0; i < keys.length; i++) {
            if (cur == null) return null;
            cur = cur[keys[i]];
        }
        return cur;
    }

    for (var gi = 0; gi < GLOBALS.length; gi++) {
        try {
            var val = window[GLOBALS[gi]];
            if (!val) continue;
            var found = findArrays(val, 0, [GLOBALS[gi]]);
            if (found.length === 0) continue;
            found.sort(function(a,b){ return b.count - a.count; });
            var best = found[0];
            var items = getByPath(window, best.pathKeys);
            if (!Array.isArray(items)) continue;
            return {
                source: GLOBALS[gi],
                pathKeys: best.pathKeys,
                items: items.slice(0, 200)
            };
        } catch(e) {}
    }
    return null;
})()"""

# ══════════════════════════════════════════════════════════════════
# JS 스니펫: DOM에서 상품 카드 패턴 탐색
# ══════════════════════════════════════════════════════════════════

_JS_FIND_DOM_PRODUCTS = r"""(() => {
    var PRICE_RE = /[\d,]+\s*원|₩\s*[\d,]+|\$\s*[\d,.]+|¥\s*[\d,.]+/;
    var BADGE_CLS = /badge|tag|label|sticker|flag|icon|stamp|ribbon|chip|mark|event|promotion|emblem/i;
    var NAME_CLS  = /name|title|prdNm|goods.?nm|product.?name|item.?name/i;
    var BRAND_CLS = /brand|maker|manufacturer|vendor/i;
    var ORIG_CLS  = /origin|regular|normal|list|retail|before|consumer|org/i;

    function clsOf(el) {
        if (!el) return '';
        var c = el.className;
        return (typeof c === 'string' ? c : (c && c.baseVal) || '');
    }
    function ancestorCls(el, n) {
        var s = '';
        for (var i = 0; i < n && el; i++) { s += ' ' + clsOf(el); el = el.parentElement; }
        return s;
    }

    /* ── 가격 리프 요소 수집 ── */
    var priceEls = [];
    var allEls = document.body.querySelectorAll('*');
    for (var i = 0; i < allEls.length; i++) {
        var el = allEls[i];
        if (el.children.length > 0) continue;
        var txt = (el.textContent || '').trim();
        if (txt.length >= 3 && txt.length < 50 && PRICE_RE.test(txt)) {
            priceEls.push(el);
        }
    }
    if (priceEls.length < 3) return null;

    /* ── 가격 요소 → 카드 조상 → 그리드 부모 탐색 ── */
    var bestParent = null, bestTag = '', bestCount = 0;
    for (var pi = 0; pi < priceEls.length; pi++) {
        var node = priceEls[pi];
        for (var depth = 1; depth <= 6; depth++) {
            for (var d = 0; d < depth; d++) {
                if (!node.parentElement) break;
                node = node.parentElement;
            }
            if (!node.parentElement) break;
            var parent = node.parentElement;
            var tag = node.tagName;
            var siblings = parent.children;
            var sameCount = 0;
            for (var si = 0; si < siblings.length; si++) {
                if (siblings[si].tagName === tag) sameCount++;
            }
            if (sameCount >= 3 && sameCount > bestCount) {
                bestParent = parent;
                bestTag = tag;
                bestCount = sameCount;
            }
            node = priceEls[pi];
        }
    }
    if (!bestParent || bestCount < 3) return null;

    var cards = bestParent.querySelectorAll(':scope > ' + bestTag);

    /* ── Pass 1: 빈도 분석 (짧고 반복되는 텍스트 = 배지/라벨) ── */
    var freq = {};
    for (var ci = 0; ci < cards.length; ci++) {
        var seen = {};
        var w = document.createTreeWalker(cards[ci], NodeFilter.SHOW_TEXT, null);
        while (w.nextNode()) {
            var t = w.currentNode.textContent.trim();
            if (t.length >= 2 && t.length <= 10 && !PRICE_RE.test(t) && !seen[t]) {
                seen[t] = 1;
                freq[t] = (freq[t] || 0) + 1;
            }
        }
    }
    var thr = Math.max(cards.length * 0.3, 3);
    var badgeTexts = {};
    for (var k in freq) { if (freq[k] >= thr) badgeTexts[k] = 1; }

    /* ── Pass 2: 카드별 데이터 추출 ── */
    var items = [];
    for (var ci = 0; ci < cards.length; ci++) {
        var card = cards[ci];
        var img = card.querySelector('img[src]');
        /* 링크: javascript: 제외, 실제 URL 우선 */
        var link = null;
        var cardLinks = card.querySelectorAll('a[href]');
        for (var li = 0; li < cardLinks.length; li++) {
            var h = cardLinks[li].getAttribute('href') || '';
            if (h && h.indexOf('javascript:') !== 0 && h !== '#') {
                link = cardLinks[li]; break;
            }
        }
        var jsLink = null;
        if (!link && cardLinks.length > 0) jsLink = cardLinks[0];

        /* 1) 클래스 기반 시멘틱 추출 (이름·브랜드) */
        var sName = '', sBrand = '';
        var inners = card.querySelectorAll('*');
        for (var j = 0; j < inners.length; j++) {
            var ic = clsOf(inners[j]);
            if (!sName && NAME_CLS.test(ic)) sName = inners[j].textContent.trim();
            if (!sBrand && BRAND_CLS.test(ic)) sBrand = inners[j].textContent.trim();
            if (sName && sBrand) break;
        }

        /* 2) TreeWalker: 텍스트·가격 수집 (배지 필터링) */
        var texts = [], prices = [], pIsOrig = [];
        var wk = document.createTreeWalker(card, NodeFilter.SHOW_TEXT, null);
        while (wk.nextNode()) {
            var t = wk.currentNode.textContent.trim();
            if (t.length < 2) continue;

            if (PRICE_RE.test(t)) {
                prices.push(t);
                var pe = wk.currentNode.parentElement;
                var isO = (pe && (pe.tagName === 'DEL' || pe.tagName === 'S')) ||
                          ORIG_CLS.test(ancestorCls(pe, 3));
                pIsOrig.push(isO);
                continue;
            }
            if (t.length > 200) continue;

            /* 배지 필터링: 클래스 + 빈도 */
            var pe2 = wk.currentNode.parentElement;
            if (BADGE_CLS.test(clsOf(pe2))) continue;
            if (badgeTexts[t]) continue;

            texts.push(t);
        }

        /* 3) 이름: 시멘틱 > 가장 긴 텍스트 */
        var name = sName;
        if (!name && texts.length > 0) {
            var bestT = '', bestL = 0;
            for (var ti = 0; ti < texts.length; ti++) {
                if (texts[ti].length > bestL) { bestL = texts[ti].length; bestT = texts[ti]; }
            }
            name = bestT;
        }

        /* 4) 브랜드: 시멘틱 > 이름 제외 첫 텍스트 */
        var brand = sBrand;
        if (!brand && texts.length > 1) {
            for (var bi = 0; bi < texts.length; bi++) {
                if (texts[bi] !== name) { brand = texts[bi]; break; }
            }
        }

        /* 5) 가격: DEL/S 태그·클래스 컨텍스트 기반 원가/판매가 분류 */
        var saleP = '', origP = '';
        if (prices.length === 1) {
            saleP = prices[0];
        } else if (prices.length >= 2) {
            var oi = -1, si2 = -1;
            for (var px = 0; px < pIsOrig.length; px++) {
                if (pIsOrig[px] && oi < 0) oi = px;
                else if (!pIsOrig[px] && si2 < 0) si2 = px;
            }
            if (oi >= 0 && si2 >= 0) {
                origP = prices[oi]; saleP = prices[si2];
            } else {
                var v0 = parseFloat(prices[0].replace(/[^0-9.]/g,''))||0;
                var v1 = parseFloat(prices[1].replace(/[^0-9.]/g,''))||0;
                if (v0 >= v1) { origP = prices[0]; saleP = prices[1]; }
                else { origP = prices[1]; saleP = prices[0]; }
            }
        }

        if (!name && !saleP && !origP) continue;

        /* product_url: 실제 URL 또는 data 속성, javascript: → 상품ID */
        var pUrl = link ? link.href : '';
        var pId = '';
        /* data 속성에서 URL 탐색 */
        if (!pUrl) {
            var dAttrs = ['data-url','data-href','data-link','data-detail-url'];
            var dEls = [card].concat(Array.from(cardLinks));
            for (var da = 0; da < dAttrs.length && !pUrl; da++) {
                for (var de = 0; de < dEls.length && !pUrl; de++) {
                    var dv = dEls[de].getAttribute(dAttrs[da]);
                    if (dv && dv.length > 1) {
                        if (dv.indexOf('http') === 0) pUrl = dv;
                        else if (dv.charAt(0) === '/') pUrl = location.origin + dv;
                    }
                }
            }
        }
        /* javascript: 링크에서 상품ID 추출 */
        if (!pUrl && jsLink) {
            var jh = jsLink.getAttribute('href') || '';
            var m = jh.match(/\d{8,}/);
            if (m) pId = m[0];
        }

        items.push({
            name: name || '',
            brand: brand || '',
            price: saleP || '',
            original_price: origP || '',
            image: img ? img.src : '',
            product_url: pUrl,
            product_id: pId || ''
        });
    }
    if (items.length < 3) return null;

    return {selector: bestTag, count: items.length, items: items};
})()"""

# ══════════════════════════════════════════════════════════════════
# JS 스니펫: 카드 클릭 (product_id 또는 image URL로 카드를 찾아 클릭)
# ══════════════════════════════════════════════════════════════════

_JS_CLICK_CARD = """(args) => {
    var productId = args.productId || '';
    var imageUrl  = args.imageUrl  || '';
    /* 1) product_id가 포함된 링크 찾기 (javascript: 포함) */
    if (productId) {
        var links = document.querySelectorAll('a[href]');
        for (var i = 0; i < links.length; i++) {
            var href = links[i].getAttribute('href') || '';
            if (href.indexOf(productId) >= 0) {
                links[i].click();
                return true;
            }
        }
    }
    /* 2) image URL로 카드 찾기 → 클릭 가능한 부모 링크 */
    if (imageUrl) {
        var imgs = document.querySelectorAll('img');
        for (var i = 0; i < imgs.length; i++) {
            if (imgs[i].src === imageUrl) {
                var target = imgs[i].closest('a') || imgs[i].parentElement;
                if (target) { target.click(); return true; }
            }
        }
    }
    return false;
}"""

# ══════════════════════════════════════════════════════════════════
# JS 스니펫: 상품 상세 페이지에서 정보 추출
# ══════════════════════════════════════════════════════════════════

_JS_EXTRACT_DETAIL = r"""(() => {
    /* ── 1. 상품 설명 (description) ── */
    var desc = '';

    /* 1-a: OG description (보통 meta description보다 상품 특화) */
    var ogDesc = document.querySelector('meta[property="og:description"]');
    if (ogDesc) desc = (ogDesc.content || '').trim();

    /* 1-b: meta description (사이트 공통 문구 필터링) */
    if (!desc || desc.length < 20) {
        var metaDesc = document.querySelector('meta[name="description"]');
        if (metaDesc) desc = (metaDesc.content || '').trim();
    }

    /* 사이트 공통 문구 감지: 페이지 title과 동일하거나, 상품명 미포함 시 DOM 탐색 */
    var pageTitle = document.title || '';
    var isGenericDesc = !desc || desc.length < 20 ||
        desc === pageTitle ||
        /쇼핑몰|인터넷.*몰|면세점$|duty.?free$/i.test(desc);

    /* 1-c: DOM에서 실제 상품 설명 추출 */
    var NOISE_RE = /적립.*혜택|할부.*혜택|주문취소|반품안내|배송안내|인도안내|인도방법|카드.*무이자|이용약관|기본정보[\s\S]*본 상품은/;
    if (isGenericDesc) {
        desc = '';
        /* 상세 설명 후보 셀렉터 (우선순위순) */
        var descSels = [
            '.product-detail-info',
            '.prd_detail_area',
            '[class*="detailDesc"]',
            '[class*="detail_desc"]',
            '[class*="product_desc"]',
            '[class*="goods_desc"]',
            '.detail_info',
            '[class*="description"]:not(meta)',
            '[class*="product_info"]:not([class*="product_info_"])',
            'article.detail',
            'main [class*="detail"]',
            '.tabBody.infoBox',
            'dd.detail'
        ];
        for (var si = 0; si < descSels.length; si++) {
            var el = document.querySelector(descSels[si]);
            if (el && el.innerText && el.innerText.trim().length > 30) {
                var txt = el.innerText.trim();
                if (!NOISE_RE.test(txt.substring(0, 50))) {
                    desc = txt.substring(0, 2000);
                    break;
                }
            }
        }
    }

    /* 1-d: 최후 fallback — 가장 텍스트가 많은 상세 영역 (노이즈 필터링) */
    if (!desc || desc.length < 30) {
        var candidates = document.querySelectorAll(
            '[class*="detail"], [class*="spec"], [class*="info"]'
        );
        var best = null, bestLen = 0;
        for (var ci = 0; ci < candidates.length; ci++) {
            var txt = candidates[ci].innerText || '';
            if (txt.length > bestLen && txt.length > 50 && txt.length < 5000 &&
                !NOISE_RE.test(txt.substring(0, 50))) {
                bestLen = txt.length;
                best = txt;
            }
        }
        if (best) desc = best.trim().substring(0, 2000);
    }

    /* ── 2. 상품 스펙/기본정보 테이블 (spec) ── */
    var spec = {};
    var specSels = [
        '.tabBody.infoBox table',
        '.infoTable table',
        '.cmpsPrdInfo_pkg table',
        '[class*="spec"] table',
        '[class*="detail_info"] table',
        '.product-spec table',
        'table.product-info',
        'dl.product-info'
    ];
    for (var ti = 0; ti < specSels.length; ti++) {
        var table = document.querySelector(specSels[ti]);
        if (!table) continue;
        /* th-td 쌍 추출 */
        var rows = table.querySelectorAll('tr');
        for (var ri = 0; ri < rows.length; ri++) {
            var th = rows[ri].querySelector('th, td:first-child');
            var td = rows[ri].querySelector('td:last-child');
            if (th && td && th !== td) {
                var key = th.innerText.trim();
                var val = td.innerText.trim();
                if (key && val && key.length < 30) spec[key] = val;
            }
        }
        if (Object.keys(spec).length > 0) break;
    }

    /* dl 기반 스펙 추출 */
    if (Object.keys(spec).length === 0) {
        var dls = document.querySelectorAll(
            '.tabBody dl, .infoBox dl, [class*="spec"] dl, [class*="detail"] dl'
        );
        for (var di = 0; di < dls.length; di++) {
            var dts = dls[di].querySelectorAll('dt');
            var dds = dls[di].querySelectorAll('dd');
            for (var ddi = 0; ddi < Math.min(dts.length, dds.length); ddi++) {
                var dk = dts[ddi].innerText.trim();
                var dv = dds[ddi].innerText.trim();
                if (dk && dv && dk.length < 30) spec[dk] = dv.substring(0, 200);
            }
            if (Object.keys(spec).length > 0) break;
        }
    }

    /* ── 3. 상세 이미지 (detail_images) ── */
    var imgs = [];
    var MIN_IMG_SIZE = 150;
    var imgSels = [
        '[class*="detail_desc"] img[src]',
        '[class*="product_detail"] img[src]',
        '.detail_info img[src]',
        '[class*="description"] img[src]',
        '.tabBody img[src]',
        '[class*="content"] img[src]',
        'dd.detail img[src]'
    ];
    for (var ii = 0; ii < imgSels.length; ii++) {
        var imgEls = document.querySelectorAll(imgSels[ii]);
        for (var j = 0; j < Math.min(imgEls.length, 20); j++) {
            var src = imgEls[j].src || imgEls[j].dataset.src || '';
            var w = imgEls[j].naturalWidth || imgEls[j].width || 0;
            var h = imgEls[j].naturalHeight || imgEls[j].height || 0;
            /* resize/NxN 패턴으로 작은 썸네일 제외 */
            var isThumbnail = /resize\/\d{1,3}x\d{1,3}|\/\d{2,3}x\d{2,3}\//i.test(src);
            if (src && !src.includes('icon') && !src.includes('logo') &&
                !src.includes('pixel') && !src.includes('tracking') &&
                !isThumbnail &&
                (w > MIN_IMG_SIZE || h > MIN_IMG_SIZE ||
                 src.includes('/prod/') || src.includes('/product/'))) {
                if (imgs.indexOf(src) === -1) imgs.push(src);
            }
        }
        if (imgs.length >= 3) break;
    }

    /* 이미지 fallback: 메인 상품 이미지 (zoom, og:image) */
    if (imgs.length === 0) {
        var zoomImg = document.querySelector('#detailZoom, .product-image img, .prd_img img');
        if (zoomImg && zoomImg.src) imgs.push(zoomImg.src);
        var ogImg = document.querySelector('meta[property="og:image"]');
        if (ogImg && ogImg.content && imgs.indexOf(ogImg.content) === -1) {
            imgs.push(ogImg.content);
        }
    }

    /* ── 4. 카테고리 breadcrumb (category_breadcrumb) ── */
    var breadcrumb = '';
    var bcSels = [
        '.location_area', '.breadcrumb', '.path_area',
        '[class*="breadcrumb"]', '[class*="location"]', '[class*="path"]',
        'nav[aria-label*="breadcrumb"]', '.gnb_area .path',
        '.cmpsTit_pkg .location', '.locationWrap'
    ];
    var BC_NOISE = /위치안내|현재위치|닫기|열기|^\s*$/;
    var BC_STORE = /\d{2,3}-\d{3,4}-\d{4}|\d{2}:\d{2}\s*~|터미널|층\s|매장안내|영업시간/;
    for (var bi = 0; bi < bcSels.length; bi++) {
        var bcEl = document.querySelector(bcSels[bi]);
        if (bcEl && bcEl.innerText && bcEl.innerText.trim().length > 3) {
            var bcFullText = bcEl.innerText.trim();
            /* 매장 안내 영역이면 건너뛰기 (전화번호/영업시간 포함 or 텍스트 300자 초과) */
            if (BC_STORE.test(bcFullText) || bcFullText.length > 300) continue;
            /* a 태그 우선 (실제 카테고리 링크) */
            var bcLinks = bcEl.querySelectorAll('a');
            var parts = [];
            for (var bj = 0; bj < bcLinks.length; bj++) {
                var t = bcLinks[bj].innerText.trim();
                if (t && t.length > 0 && t.length < 30 &&
                    parts.indexOf(t) === -1 && !BC_NOISE.test(t)) {
                    parts.push(t);
                }
            }
            /* a 태그가 부족하면 span/li 포함 */
            if (parts.length < 2) {
                parts = [];
                var bcAll = bcEl.querySelectorAll('a, span, li');
                for (var bk = 0; bk < bcAll.length; bk++) {
                    var t2 = bcAll[bk].innerText.trim();
                    if (t2 && t2.length > 0 && t2.length < 30 &&
                        parts.indexOf(t2) === -1 && !BC_NOISE.test(t2)) {
                        parts.push(t2);
                    }
                }
            }
            /* 최대 6단계로 제한 */
            if (parts.length > 6) parts = parts.slice(0, 6);
            if (parts.length >= 2) {
                breadcrumb = parts.join(' > ');
            } else {
                breadcrumb = bcEl.innerText.trim()
                    .replace(/위치안내[^\n]*/g, '').replace(/[\t ]*\n+[\t ]*/g, ' > ')
                    .replace(/ > ( > )+/g, ' > ').replace(/^\s*>\s*|\s*>\s*$/g, '').trim();
            }
            if (breadcrumb.length > 3) break;
        }
    }

    /* ── 5. 상품코드 / 레퍼런스코드 (product_code, reference_code) ── */
    var productCode = '';
    var referenceCode = '';
    var bodyText = document.body.innerText || '';

    /* 텍스트에서 코드를 분리 추출하는 헬퍼 */
    function _extractCodes(text) {
        var rc = text.match(/레퍼런스[\s]*코드[\s:：]*([A-Z0-9\-]+)/i);
        var pc = text.match(/상품[\s]*코드[\s:：]*([A-Z0-9\-]+)/i);
        return {ref: rc ? rc[1] : '', prd: pc ? pc[1] : ''};
    }

    /* 5-a: 신라면세점 특화 — .product_number 내 REF.NO / SKU.NO */
    var pnumEl = document.querySelector('.product_number');
    if (pnumEl) {
        var pnumLis = pnumEl.querySelectorAll('li');
        for (var pni = 0; pni < pnumLis.length; pni++) {
            var titleEl = pnumLis[pni].querySelector('.number_title');
            var textEl = pnumLis[pni].querySelector('.number_text');
            if (!titleEl || !textEl) continue;
            var pnTitle = titleEl.innerText.trim();
            var pnText = textEl.innerText.trim();
            if (/REF|레퍼런스/i.test(pnTitle) && pnText && !referenceCode) {
                referenceCode = pnText.substring(0, 50);
            }
            if (/SKU|상품코드|품목/i.test(pnTitle) && pnText && !productCode) {
                productCode = pnText.replace(/[^A-Z0-9\-]/gi, '').substring(0, 50);
            }
        }
    }

    /* 5-a2: 현대면세점 특화 — li.ref / li.sku */
    var hdRefEl = document.querySelector('li.ref');
    var hdSkuEl = document.querySelector('li.sku');
    if (hdRefEl && !referenceCode) {
        var hdRefSpan = hdRefEl.querySelector('span');
        if (hdRefSpan) {
            referenceCode = hdRefSpan.innerText.trim().substring(0, 50);
        } else {
            var hdRefM = hdRefEl.innerText.match(/REF\s*(?:NO\.?)?\s*[：:]\s*(\S+)/i);
            if (hdRefM) referenceCode = hdRefM[1].substring(0, 50);
        }
    }
    if (hdSkuEl && !productCode) {
        var hdSkuSpan = hdSkuEl.querySelector('span');
        if (hdSkuSpan) {
            productCode = hdSkuSpan.innerText.trim().replace(/[^A-Z0-9\-]/gi, '').substring(0, 50);
        } else {
            var hdSkuM = hdSkuEl.innerText.match(/SKU\s*(?:NO\.?)?\s*[：:]\s*(\S+)/i);
            if (hdSkuM) productCode = hdSkuM[1].replace(/[^A-Z0-9\-]/gi, '').substring(0, 50);
        }
    }

    /* 5-b: dt-dd 패턴 */
    var allDts = document.querySelectorAll('dt');
    for (var dti = 0; dti < allDts.length; dti++) {
        var dtText = allDts[dti].innerText.trim();
        var ddEl = allDts[dti].nextElementSibling;
        if (!ddEl) continue;
        var ddText = ddEl.innerText.trim();
        /* dd 안에 여러 코드가 합쳐진 경우 분리 */
        if (/레퍼런스.*코드.*상품.*코드|상품.*코드.*레퍼런스/i.test(ddText)) {
            var codes = _extractCodes(ddText);
            if (codes.ref && !referenceCode) referenceCode = codes.ref;
            if (codes.prd && !productCode) productCode = codes.prd;
            continue;
        }
        if (/상품코드|품목코드|Item\s*Code/i.test(dtText) && ddText && !productCode) {
            productCode = ddText.replace(/[^A-Z0-9\-]/gi, '').substring(0, 50);
        }
        if (/레퍼런스|Ref(?:erence)?\s*(?:Code|No)?/i.test(dtText) && ddText && !referenceCode) {
            referenceCode = ddText.replace(/[^A-Z0-9\-]/gi, '').substring(0, 50);
        }
    }
    /* th-td 패턴 */
    if (!productCode || !referenceCode) {
        var allThs = document.querySelectorAll('th');
        for (var thi = 0; thi < allThs.length; thi++) {
            var thText = allThs[thi].innerText.trim();
            var tdNext = allThs[thi].parentElement ? allThs[thi].parentElement.querySelector('td') : null;
            if (!tdNext) continue;
            var tdText = tdNext.innerText.trim();
            if (!productCode && /상품코드|품목코드/i.test(thText) && tdText) {
                productCode = tdText.substring(0, 50);
            }
            if (!referenceCode && /레퍼런스|Ref/i.test(thText) && tdText) {
                referenceCode = tdText.substring(0, 50);
            }
        }
    }
    /* 텍스트 정규식 fallback */
    if (!productCode) {
        var pcm = bodyText.match(/상품[\s]*코드[\s:：]*([A-Z0-9\-]+)/i);
        if (pcm) productCode = pcm[1];
    }
    if (!referenceCode) {
        var rcm = bodyText.match(/레퍼런스[\s]*코드[\s:：]*([A-Z0-9\-]+)/i);
        if (!rcm) rcm = bodyText.match(/[Rr]ef(?:erence)?[\s.]*(?:[Cc]ode|[Nn]o)?[\s:：.]*([A-Z0-9\-\.]+)/);
        if (rcm) referenceCode = rcm[1];
    }

    /* ── 6. 가격: 정상가 / 할인율 / 판매가 ── */
    var regularPriceUsd = '', regularPriceKrw = '';
    var discountRate = '';
    var salePriceUsd = '', salePriceKrw = '';

    /* 6-a: 롯데면세점 특화 — li.regular_price + ID 기반 */
    var regPriceEl = document.querySelector('li.regular_price');
    if (regPriceEl) {
        var regSpans = regPriceEl.querySelectorAll('span');
        for (var rsi = 0; rsi < regSpans.length; rsi++) {
            var rsText = regSpans[rsi].innerText.trim();
            var ruM = rsText.match(/\$([\d,\.]+)/);
            var rkM = rsText.match(/([\d,]+)\s*원|^\(([\d,]+)원\)$/);
            if (ruM && !regularPriceUsd) regularPriceUsd = '$' + ruM[1];
            if (rkM && !regularPriceKrw) {
                var kwVal = rkM[1] || rkM[2];
                regularPriceKrw = kwVal + '원';
            }
        }
    }
    var rateEl = document.querySelector('#grdDscntRt, strong.rate');
    if (rateEl) {
        var rateText = rateEl.innerText.trim();
        if (/\d+%/.test(rateText)) discountRate = rateText;
    }
    /* 현대면세점 할인율 — span.sale_percent > em */
    if (!discountRate) {
        var hdRateEl = document.querySelector('span.sale_percent em, span.sale_percent');
        if (hdRateEl) {
            var hdRateText = hdRateEl.innerText.trim().replace(/\s+/g, '');
            if (/^\d+$/.test(hdRateText)) discountRate = hdRateText + '%';
            else if (/\d+%/.test(hdRateText)) discountRate = hdRateText.match(/(\d+%)/)[1];
        }
    }
    var saleUsdEl = document.querySelector('#grdSrpDscntAmt');
    var saleKrwEl = document.querySelector('#grdGlblDscntAmt');
    if (saleUsdEl) {
        var suM = saleUsdEl.innerText.trim().match(/\$([\d,\.]+)/);
        if (suM) salePriceUsd = '$' + suM[1];
    }
    if (saleKrwEl) {
        var skM = saleKrwEl.innerText.trim().match(/([\d,]+)\s*원|^\(([\d,]+)원\)/);
        if (skM) salePriceKrw = (skM[1] || skM[2]) + '원';
    }

    /* 6-a2: 신라면세점 특화 — #salePrice / #mileageDcPrice 기반 */
    if (!regularPriceUsd && !regularPriceKrw) {
        var shillaRegUsd = document.querySelector('#salePrice');
        var shillaRegKrw = document.querySelector('#salePriceWon');
        if (shillaRegUsd || shillaRegKrw) {
            if (shillaRegUsd) {
                var sruVal = (shillaRegUsd.getAttribute('data-value') || shillaRegUsd.innerText).trim();
                var sruM = sruVal.match(/\$?([\d,\.]+)/);
                if (sruM) regularPriceUsd = '$' + sruM[1];
            }
            if (shillaRegKrw) {
                var srkVal = (shillaRegKrw.getAttribute('data-value') || shillaRegKrw.innerText).trim();
                var srkM = srkVal.match(/([\d,]+)/);
                if (srkM) regularPriceKrw = srkM[1] + '원';
            }
            /* 할인율 — span.rate */
            var shillaRate = document.querySelector('span.rate, .discount_rate .rate');
            if (shillaRate && !discountRate) {
                var srText = shillaRate.innerText.trim();
                if (/\d+%/.test(srText)) discountRate = srText;
            }
            /* 할인가 */
            var shillaSaleUsd = document.querySelector('#mileageDcPrice');
            var shillaSaleKrw = document.querySelector('#mileageDcPriceWon');
            if (shillaSaleUsd) {
                var ssuVal = (shillaSaleUsd.getAttribute('data-value') || shillaSaleUsd.innerText).trim();
                var ssuM = ssuVal.match(/\$?([\d,\.]+)/);
                if (ssuM) salePriceUsd = '$' + ssuM[1];
            }
            if (shillaSaleKrw) {
                var sskVal = (shillaSaleKrw.getAttribute('data-value') || shillaSaleKrw.innerText).trim();
                var sskM = sskVal.match(/([\d,]+)/);
                if (sskM) salePriceKrw = sskM[1] + '원';
            }
        }
    }

    /* 6-b: 범용 라벨 매칭 fallback */
    if (!regularPriceUsd && !regularPriceKrw) {
        var priceLabels = document.querySelectorAll('dt, th, .label, .tit, [class*="tit"]');
        for (var pi = 0; pi < priceLabels.length; pi++) {
            var plText = priceLabels[pi].innerText.trim();
            var pNext = priceLabels[pi].nextElementSibling;
            if (!pNext) continue;
            var pVal = pNext.innerText.trim().replace(/\s+/g, ' ');
            if (!pVal || /로그인|login/i.test(pVal)) continue;

            if (/정상가|정가|retail|original/i.test(plText) && !/세일|할인|판매/i.test(plText)) {
                var usdM = pVal.match(/\$([\d,\.]+)/);
                var krwM = pVal.match(/([\d,]+)\s*원/);
                if (usdM && !regularPriceUsd) regularPriceUsd = '$' + usdM[1];
                if (krwM && !regularPriceKrw) regularPriceKrw = krwM[1] + '원';
            }
            if (!discountRate && /할인율|할인|discount/i.test(plText)) {
                var drM = pVal.match(/(\d+)\s*%/);
                if (drM) discountRate = drM[1] + '%';
            }
            if (/판매가|세일가|할인가|sale/i.test(plText)) {
                var usdM2 = pVal.match(/\$([\d,\.]+)/);
                var krwM2 = pVal.match(/([\d,]+)\s*원/);
                if (usdM2 && !salePriceUsd) salePriceUsd = '$' + usdM2[1];
                if (krwM2 && !salePriceKrw) salePriceKrw = krwM2[1] + '원';
            }
        }
    }

    /* 6-c: 가격 래퍼 fallback */
    if (!regularPriceUsd && !regularPriceKrw) {
        var priceWrap = document.querySelector('.cmpsPrice_pkg, .price_wrap, .priceInfo, .price_area');
        if (priceWrap) {
            var pwText = priceWrap.innerText || '';
            var prUsd = pwText.match(/정상가[^$]*\$([\d,\.]+)/);
            var prKrw = pwText.match(/정상가[^원]*([\d,]+)\s*원/);
            if (prUsd) regularPriceUsd = '$' + prUsd[1];
            if (prKrw) regularPriceKrw = prKrw[1] + '원';
            if (!discountRate) {
                var drWrap = pwText.match(/(\d+)\s*%/);
                if (drWrap) discountRate = drWrap[1] + '%';
            }
            var psUsd = pwText.match(/(?:판매가|세일가)[^$]*\$([\d,\.]+)/);
            var psKrw = pwText.match(/(?:판매가|세일가)[^원]*([\d,]+)\s*원/);
            if (psUsd && !salePriceUsd) salePriceUsd = '$' + psUsd[1];
            if (psKrw && !salePriceKrw) salePriceKrw = psKrw[1] + '원';
        }
    }

    /* 6-d: del/s 태그 기반 fallback (원가=del, 판매가=인접 요소) */
    if (!regularPriceUsd && !regularPriceKrw) {
        var delEl = document.querySelector('del, s, .original-price, [class*="origin"]');
        if (delEl) {
            var delText = delEl.innerText.trim();
            var duM = delText.match(/\$([\d,\.]+)/);
            var dkM = delText.match(/([\d,]+)\s*원/);
            if (duM) regularPriceUsd = '$' + duM[1];
            if (dkM) regularPriceKrw = dkM[1] + '원';
        }
    }

    /* ── 6-e: 최대혜택가 영역 (max_benefit_info) ── */
    var maxBenefitInfo = '';
    var mbEl = document.querySelector('dl[data-ganame="maxBenefit"]');
    if (!mbEl) mbEl = document.querySelector('[class*="maxBenefit"], [class*="benefit_price"]');
    if (mbEl) {
        var lines = [];
        var mbDls = mbEl.querySelectorAll('dl');
        for (var mbi = 0; mbi < mbDls.length; mbi++) {
            var mbDt = mbDls[mbi].querySelector('dt');
            var mbDd = mbDls[mbi].querySelector('dd');
            if (mbDt && mbDd) {
                var label = mbDt.innerText.trim().replace(/\s+/g, ' ');
                var value = mbDd.innerText.trim().replace(/\s+/g, ' ');
                if (label && value && label.length < 40) {
                    lines.push(label + ': ' + value);
                }
            }
        }
        if (lines.length > 0) {
            maxBenefitInfo = lines.join('\n');
        }
        /* 쿠폰 정보 추가 */
        var couponTag = mbEl.querySelector('.coupon_info_tag, [class*="coupon_info"]');
        if (couponTag) {
            var coupons = [];
            var couponSpans = couponTag.querySelectorAll('span');
            for (var ci = 0; ci < couponSpans.length; ci++) {
                var ct = couponSpans[ci].innerText.trim();
                if (ct && !/주문|적용|가능/i.test(ct)) coupons.push(ct);
            }
            if (coupons.length > 0) {
                maxBenefitInfo += '\n적용가능쿠폰: ' + coupons.join(', ');
            }
        }
    }

    /* ── 7. 구매혜택 (benefits) ── */
    var benefits = '';
    var bnfSels = [
        '[class*="benefit"]', '[class*="Benefit"]', '[class*="bnft"]',
        '.coupon_area', '.point_area', '.prd_benefit',
        '.cmpsOption_pkg', '[class*="addInfo"]'
    ];
    for (var bni = 0; bni < bnfSels.length; bni++) {
        var bnfEl = document.querySelector(bnfSels[bni]);
        if (bnfEl && bnfEl.innerText && bnfEl.innerText.trim().length > 5) {
            benefits = bnfEl.innerText.trim().substring(0, 500);
            break;
        }
    }

    /* ── 8. 관련상품 (related_products) ── */
    var relatedProducts = [];
    var relSels = [
        '[class*="together"]', '[class*="Together"]',
        '[class*="related"]', '[class*="recommend"]',
        '.cmpsPrdListH_pkg', '[class*="Also"]'
    ];
    var REL_NOISE = /최근검색|최근본|검색어|로그인|장바구니|고객센터/;
    for (var rli = 0; rli < relSels.length; rli++) {
        var relEl = document.querySelector(relSels[rli]);
        if (!relEl) continue;
        if (REL_NOISE.test(relEl.innerText.substring(0, 100))) continue;
        var relLinks = relEl.querySelectorAll('a[href*="product"], a[href*="prdNo"]');
        if (relLinks.length === 0) {
            relLinks = relEl.querySelectorAll('[class*="item"], li, .prd');
        }
        for (var rj = 0; rj < Math.min(relLinks.length, 20); rj++) {
            var rName = relLinks[rj].innerText.trim().substring(0, 80);
            var rImg = relLinks[rj].querySelector('img');
            var rLink = relLinks[rj].closest('a') || relLinks[rj].querySelector('a');
            var rUrl = rLink ? (rLink.href || '') : '';
            if (rName && rName.length > 2 && !REL_NOISE.test(rName) &&
                (rUrl.includes('product') || rImg)) {
                relatedProducts.push({
                    name: rName,
                    image: rImg ? (rImg.src || '') : '',
                    url: rUrl
                });
            }
        }
        if (relatedProducts.length > 0) break;
    }

    return {
        description: desc, detail_images: imgs, spec: spec,
        category_breadcrumb: breadcrumb,
        product_code: productCode, reference_code: referenceCode,
        regular_price_usd: regularPriceUsd, regular_price_krw: regularPriceKrw,
        discount_rate: discountRate,
        sale_price_usd: salePriceUsd, sale_price_krw: salePriceKrw,
        max_benefit_info: maxBenefitInfo,
        benefits: benefits,
        related_products: relatedProducts
    };
})()"""


# ══════════════════════════════════════════════════════════════════
# 유틸리티 함수
# ══════════════════════════════════════════════════════════════════

def _log(msg: str):
    """인코딩 안전 로그 출력. Windows cp949 콘솔에서도 유니코드 문자 안전 처리."""
    line = f"{_TAG} {msg}"
    try:
        print(line)
    except UnicodeEncodeError:
        import sys
        sys.stdout.buffer.write((line + "\n").encode("utf-8", errors="replace"))
        sys.stdout.buffer.flush()


def _safe(text: str) -> str:
    try:
        return text.encode("cp949", errors="replace").decode("cp949")
    except Exception:
        return text


def _js_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _find_product_array(data, depth: int = 0) -> list | None:
    """JSON 데이터에서 상품 배열을 재귀적으로 탐색한다."""
    if depth > 5:
        return None

    if isinstance(data, list) and len(data) >= 3:
        if isinstance(data[0], dict) and _looks_like_product(data[0]):
            return data

    if isinstance(data, dict):
        for key, val in data.items():
            result = _find_product_array(val, depth + 1)
            if result:
                return result

    return None


def _looks_like_product(obj: dict) -> bool:
    keys_lower = " ".join(str(k) for k in obj.keys()).lower()
    has_name = bool(re.search(r"name|title|product|goods", keys_lower))
    has_price = bool(re.search(r"price|cost|amount|sell", keys_lower))
    return has_name and has_price


def _product_key(item: dict) -> str:
    pid = item.get("product_id") or item.get("productId") or item.get("id")
    if pid:
        return str(pid)
    name = (item.get("name") or item.get("product_name")
            or item.get("productName") or item.get("title") or "")
    return str(name)[:80] if name else ""


def _build_seen_set(products: list) -> set:
    seen = set()
    for p in products:
        key = _product_key(p)
        if key:
            seen.add(key)
    return seen


def _resolve_product_url(prod: dict, base_url: str) -> str | None:
    for key in ("product_url", "productUrl", "url", "link", "detailUrl"):
        val = prod.get(key, "")
        if not val:
            continue
        if val.startswith("http"):
            return val
        if val.startswith("/"):
            parsed = urlparse(base_url)
            return f"{parsed.scheme}://{parsed.hostname}{val}"
    return None


def _increment_page_param(url: str, page_num: int) -> str:
    """API URL의 페이지 파라미터를 증가시킨다."""
    parsed = urlparse(url)
    params = parse_qs(parsed.query, keep_blank_values=True)

    page_keys = ["page", "pageNo", "pageNum", "pg", "p", "offset"]
    updated = False
    for key in page_keys:
        if key in params:
            if key in ("offset",):
                try:
                    size = int(params.get("size", params.get("limit", ["20"]))[0])
                    params[key] = [str((page_num - 1) * size)]
                except (ValueError, IndexError):
                    params[key] = [str(page_num)]
            else:
                params[key] = [str(page_num)]
            updated = True
            break

    if not updated:
        params["page"] = [str(page_num)]

    new_query = urlencode(
        {k: v[0] for k, v in params.items()}, doseq=False,
    )
    return urlunparse(parsed._replace(query=new_query))
