"""
크롤링 메인 엔진

하위 호환성을 위해 유지되며, 내부적으로 에이전트에 위임한다.
신규 코드는 agents/ 패키지의 에이전트를 직접 사용할 것을 권장한다.

전체 파이프라인을 실행한다:
  1. DB 에서 활성 사이트 조회
  2. 사이트 접속 → 플랫폼 감지 (DB 매칭)
  3. 플랫폼 미등록 시 → 네트워크 인터셉트 + 규칙 기반 자동 분석 → DB 저장
  4. 템플릿 기반 데이터 수집 (store → category → products → details)
  5. 수집 결과를 DB 에 저장
"""
import json
import re
import time
import random
from urllib.parse import urlparse

from playwright.sync_api import Page

from core.db import CrawlDB
from core.browser import BrowserManager
from core.rule_analyzer import RuleAnalyzer
from core.network_interceptor import NetworkInterceptor
from core.strategies import get_strategy


# ─── 수집 설정 기본값 ─────────────────────────────────────────────
DEFAULT_CRAWL_SETTINGS = {
    "max_detail_products": 20,
    "delay_min": 1.0,
    "delay_max": 2.0,
    "page_size": 40,
    "page_wait_ms": 3000,
    "initial_wait_ms": 5000,
}


class CrawlEngine:
    """
    크롤링 메인 엔진 (하위 호환 래퍼)

    기존 코드와의 호환성을 위해 ProductAgent 를 내부적으로 위임한다.
    신규 코드는 agents.product.engine.ProductAgent 를 직접 사용할 것을 권장한다.
    """

    def __init__(self, db: CrawlDB | None = None):
        self.db = db or CrawlDB()
        self.browser_mgr = BrowserManager()
        self.page: Page | None = None

    # ═══════════════════════════════════════════════════════════════
    # 공개 메서드
    # ═══════════════════════════════════════════════════════════════

    def run_all(self):
        """DB 의 모든 활성 사이트를 수집한다."""
        sites = self.db.get_active_sites()
        if not sites:
            print("[engine] 활성 사이트가 없습니다")
            return

        print(f"[engine] {len(sites)}개 사이트 수집 시작")
        for i, site in enumerate(sites, 1):
            print(f"\n{'='*60}")
            print(f"  [{i}/{len(sites)}] {site['site_name']}")
            print(f"  URL: {site['site_url']}")
            print(f"{'='*60}")
            self.run_site(site["id"])

        print(f"\n[engine] 전체 수집 완료")

    def run_site(self, site_id: int):
        """특정 사이트를 수집한다."""
        site = self.db.get_site(site_id)
        if not site:
            print(f"[engine] 사이트 ID={site_id} 를 찾을 수 없습니다")
            return

        result_id = self.db.create_result(site_id)
        start_time = time.time()

        try:
            # 1. 플랫폼 확보 (감지 또는 자동 분석)
            platform, templates = self._ensure_platform(site)
            if not platform or not templates:
                raise RuntimeError("플랫폼 감지 및 자동 분석 모두 실패")

            # 2. 브라우저 설정 적용
            browser_config = platform.get("browser", {})
            self.page = self.browser_mgr.create(browser_config)

            # 3. 수집 실행
            store_info = self._crawl_store(site, templates)
            products = self._crawl_products(site, templates)
            products = self._crawl_details(site, templates, products)

            # 4. 결과 저장
            elapsed = time.time() - start_time
            self.db.update_result(
                result_id,
                status="success",
                store_info=store_info,
                products=products,
                product_count=len(products),
                elapsed_sec=elapsed,
            )

            # JSON 파일로도 저장
            self._save_json(site, store_info, products)

            print(f"\n[engine] 수집 완료: {site['site_name']}")
            print(f"  매장명: {store_info.get('store_name', 'N/A')}")
            print(f"  상품 수: {len(products)}")
            print(f"  소요 시간: {elapsed:.1f}초")

        except Exception as e:
            elapsed = time.time() - start_time
            self.db.update_result(
                result_id,
                status="failed",
                error_msg=str(e),
                elapsed_sec=elapsed,
            )
            print(f"[engine] 수집 실패: {e}")

        finally:
            self.browser_mgr.close()
            self.page = None

    # ═══════════════════════════════════════════════════════════════
    # 플랫폼 감지 / 규칙 기반 자동 분석
    # ═══════════════════════════════════════════════════════════════

    def _ensure_platform(self, site: dict) -> tuple[dict | None, list[dict]]:
        """
        사이트에 매칭되는 플랫폼을 확보한다.
        1) 이미 연결된 플랫폼이 있으면 사용
        2) DB 의 감지 규칙으로 매칭 시도
        3) 네트워크 인터셉트 + 규칙 기반 자동 분석으로 신규 생성
        """
        # 1. 이미 연결된 플랫폼 확인
        if site.get("platform_id"):
            platform = self.db.get_platform(site["platform_id"])
            if platform:
                templates = self.db.get_templates_for_platform(platform["id"])
                if templates:
                    print(f"[engine] 기존 플랫폼 사용: {platform['display_name']}")
                    return platform, templates

        # 2. 네트워크 인터셉터 설정 후 사이트 접속
        print("[engine] 사이트 접속하여 플랫폼 감지 중...")
        interceptor = NetworkInterceptor()
        self.page = self.browser_mgr.create()
        interceptor.start(self.page)

        resp = self._safe_goto(site["site_url"], wait_until="domcontentloaded")
        if self._is_blocked(resp):
            print(f"[engine] 사이트 접근 차단됨 (HTTP {resp.status}) → 분석 중단")
            interceptor.stop(self.page)
            self.browser_mgr.close()
            self.page = None
            return None, []

        self.page.wait_for_timeout(DEFAULT_CRAWL_SETTINGS["initial_wait_ms"])

        # 클라이언트 렌더링 완료를 위해 스크롤 트리거
        self._trigger_client_render(self.page)

        interceptor.stop(self.page)
        captured = list(interceptor.captured)

        print(f"[engine] 네트워크 요청 {len(captured)}건 캡처")

        # 3. DB 감지 규칙으로 기존 플랫폼 매칭 시도
        platform = self._try_db_detection(site)
        if platform:
            templates = self.db.get_templates_for_platform(platform["id"])
            # product_list 가 있어야 완전한 매칭으로 인정
            has_product = any(
                t["target"] in ("product_list", "product_list_dom")
                for t in templates
            )
            if templates and has_product:
                self.db.update_site_platform(site["id"], platform["id"])
                print(f"[engine] 기존 플랫폼 매칭: {platform['display_name']}")
                self.browser_mgr.close()
                self.page = None
                return platform, templates
            elif templates:
                print(f"[engine] 기존 플랫폼 '{platform['display_name']}' 에 "
                      f"product_list 없음 → 재분석 진행")

        # 4. 규칙 기반 자동 분석 (인터셉트 결과 포함)
        print("[engine] 등록된 플랫폼 없음 → 자동 분석 시작")
        analyzer = RuleAnalyzer()
        analysis = analyzer.analyze(self.page, site["site_url"], captured)

        self.browser_mgr.close()
        self.page = None

        if not analysis:
            return None, []

        # 5. 분석 결과 DB 저장
        platform_id = self.db.save_llm_analysis(analysis, site["id"])
        platform = self.db.get_platform(platform_id)
        templates = self.db.get_templates_for_platform(platform_id)

        return platform, templates

    def _try_db_detection(self, site: dict) -> dict | None:
        """현재 페이지에서 DB 감지 규칙 매칭을 시도한다."""
        from core.rule_analyzer import _JS_FIND_STATE_VARS

        try:
            detected_vars = self.page.evaluate(_JS_FIND_STATE_VARS) or []
        except Exception:
            detected_vars = []

        meta = {}
        try:
            meta_raw = self.page.evaluate("""() => {
                var metas = document.querySelectorAll('meta');
                var r = {};
                for (var i = 0; i < metas.length; i++) {
                    var n = metas[i].getAttribute('name')
                         || metas[i].getAttribute('property') || '';
                    var c = metas[i].getAttribute('content') || '';
                    if (n && c) r[n] = c;
                }
                return r;
            }""")
            if meta_raw:
                meta = meta_raw
        except Exception:
            pass

        return self.db.find_platform_by_detection(
            site["site_url"], detected_vars, meta,
        )

    @staticmethod
    def _trigger_client_render(page: Page):
        """SPA 클라이언트 렌더링을 트리거하기 위해 스크롤한다."""
        try:
            page.evaluate("""() => {
                window.scrollTo(0, document.body.scrollHeight / 3);
            }""")
            page.wait_for_timeout(2000)
            page.evaluate("""() => {
                window.scrollTo(0, 0);
            }""")
            page.wait_for_timeout(1000)
        except Exception:
            pass

    # ═══════════════════════════════════════════════════════════════
    # 안전한 페이지 이동 (429/503 재시도)
    # ═══════════════════════════════════════════════════════════════

    def _safe_goto(
        self, url: str,
        wait_until: str = "domcontentloaded",
        timeout: int = 60000,
        max_retries: int = 5,
    ):
        """
        page.goto() 래퍼: 429/503 응답 시 적응형 지수 백오프 재시도.
        모든 재시도가 실패하면 마지막 응답을 반환한다.
        """
        import random as _random

        last_resp = None
        for attempt in range(max_retries):
            try:
                resp = self.page.goto(
                    url, wait_until=wait_until, timeout=timeout,
                )
                last_resp = resp
                if resp and resp.status in (429, 503):
                    # 적응형 백오프: 120초 기반 지수 증가 + 지터
                    base = 120
                    wait_secs = base * (2 ** attempt)
                    wait_secs = min(wait_secs, 600)
                    jitter = wait_secs * 0.3
                    wait_secs += _random.uniform(-jitter, jitter)
                    wait_secs = max(60, wait_secs)
                    print(
                        f"[engine] HTTP {resp.status} 응답 → "
                        f"{wait_secs:.0f}초 대기 후 재시도 "
                        f"({attempt + 1}/{max_retries})"
                    )
                    import time as _time
                    _time.sleep(wait_secs)
                    continue
                return resp
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_secs = (attempt + 1) * 15
                    print(
                        f"[engine] 페이지 로딩 오류: {e} → "
                        f"{wait_secs}초 대기 후 재시도"
                    )
                    try:
                        import time as _time
                        _time.sleep(wait_secs)
                    except Exception:
                        pass
                else:
                    raise
        return last_resp

    @staticmethod
    def _is_blocked(resp) -> bool:
        """응답이 차단(429/403/503)인지 확인한다."""
        if resp is None:
            return False
        return resp.status in (429, 403, 503)

    # ═══════════════════════════════════════════════════════════════
    # 데이터 수집
    # ═══════════════════════════════════════════════════════════════

    def _crawl_store(self, site: dict, templates: list[dict]) -> dict:
        """매장 정보를 수집한다."""
        print("\n[engine] ── 매장 정보 수집 ──")
        tmpl = self._find_template(templates, "store")
        if not tmpl:
            print("[engine] store 템플릿 없음 → 스킵")
            return {"store_name": "N/A"}

        resp = self._safe_goto(site["site_url"])
        if self._is_blocked(resp):
            print(f"[engine] 매장 페이지 차단됨 (HTTP {resp.status})")
            return {"store_name": "N/A"}
        self.page.wait_for_timeout(DEFAULT_CRAWL_SETTINGS["initial_wait_ms"])

        strategy = get_strategy(tmpl["strategy"])
        data = strategy.extract(self.page, tmpl["config"])

        result = data or {"store_name": "N/A"}
        safe_name = _safe_print(result.get("store_name", "N/A"))
        print(f"[engine] 매장명: {safe_name}")
        return result

    def _crawl_products(self, site: dict, templates: list[dict]) -> list[dict]:
        """상품 목록을 수집한다."""
        print("\n[engine] ── 상품 목록 수집 ──")

        cat_tmpl = self._find_template(templates, "category")
        prod_tmpl = self._find_template(templates, "product_list")

        if not prod_tmpl:
            print("[engine] product_list 템플릿 없음 → 스킵")
            return []

        strategy = get_strategy(prod_tmpl["strategy"])
        config = prod_tmpl["config"]
        page_size = config.get("page_size", DEFAULT_CRAWL_SETTINGS["page_size"])

        # 상품 페이지 URL이 지정된 경우 (메인 페이지와 다른 URL)
        page_url = config.get("page_url")
        if page_url and page_url != site["site_url"]:
            current_url = self.page.url
            if current_url != page_url:
                print(f"[engine] 상품 페이지로 이동: {page_url}")
                resp = self._safe_goto(
                    page_url, wait_until="networkidle", timeout=60000,
                )
                if self._is_blocked(resp):
                    print(f"[engine] 상품 페이지 차단됨 (HTTP {resp.status})")
                    return []
                self.page.wait_for_timeout(DEFAULT_CRAWL_SETTINGS["initial_wait_ms"])
                for _ in range(3):
                    self.page.evaluate("window.scrollBy(0, window.innerHeight)")
                    self.page.wait_for_timeout(1000)

        # ── 페이지네이션 타입 확인 ────────────────────────────────
        pagination = config.get("pagination", {})
        pag_type = pagination.get("type")

        # 무한 스크롤이면 별도 처리
        if pag_type == "scroll":
            return self._crawl_products_scroll(
                site, prod_tmpl, cat_tmpl,
            )

        # 클릭 페이지네이션이면 별도 처리
        if pag_type == "click":
            return self._crawl_products_click(
                site, prod_tmpl, cat_tmpl,
            )

        # ── 카테고리 기반 또는 단일 페이지 (URL 이동) ─────────────
        categories = []
        if cat_tmpl:
            categories = self._extract_categories(site, cat_tmpl)
            if categories:
                print(f"[engine] {len(categories)}개 카테고리 발견")

        all_products = []
        seen_ids = set()
        display_order = 0

        if categories:
            for cat_idx, cat in enumerate(categories, 1):
                cat_name = cat.get("name", "N/A")
                safe_cat = _safe_print(cat_name)
                print(f"\n[engine] [{cat_idx}/{len(categories)}] 카테고리: {safe_cat}")

                cat_products = self._crawl_category_products(
                    site, cat, cat_tmpl, prod_tmpl,
                    seen_ids, display_order,
                )
                for p in cat_products:
                    p["category_name"] = cat_name

                display_order += len(cat_products)
                all_products.extend(cat_products)

                if cat_idx < len(categories):
                    self._delay()
        else:
            # 카테고리 없이 현재 페이지에서 수집
            raw = strategy.extract(self.page, config)
            items = self._extract_items(raw)
            for p in items:
                display_order += 1
                p["display_order"] = display_order
            all_products = items

        # API product_list 가 0개면 DOM 폴백 시도
        if not all_products:
            dom_prod_tmpl = self._find_template(templates, "product_list_dom")
            if dom_prod_tmpl:
                print("[engine] API 결과 0개 → DOM 폴백 시도")
                # SPA 사이트는 페이지 완전 로드 + 스크롤 필요
                resp = self._safe_goto(
                    site["site_url"],
                    wait_until="networkidle",
                    timeout=60000,
                )
                if self._is_blocked(resp):
                    print(f"[engine] DOM 폴백 페이지 차단됨")
                    return []
                self.page.wait_for_timeout(
                    DEFAULT_CRAWL_SETTINGS["initial_wait_ms"],
                )
                # 스크롤로 지연 로드 콘텐츠 트리거
                for _ in range(3):
                    self.page.evaluate(
                        "window.scrollBy(0, window.innerHeight)"
                    )
                    self.page.wait_for_timeout(1000)

                dom_strategy = get_strategy(dom_prod_tmpl["strategy"])
                raw = dom_strategy.extract(self.page, dom_prod_tmpl["config"])
                items = self._extract_items(raw)
                for p in items:
                    display_order += 1
                    p["display_order"] = display_order
                all_products = items

        print(f"\n[engine] 총 {len(all_products)}개 상품 수집 완료")
        return all_products

    def _extract_categories(
        self, site: dict, cat_tmpl: dict,
    ) -> list[dict]:
        """카테고리 목록을 추출한다."""
        cat_strategy = get_strategy(cat_tmpl["strategy"])
        config = cat_tmpl["config"]

        # DOM 카테고리 (링크 기반)
        if config.get("categories_from_links"):
            raw = cat_strategy.extract(self.page, config)
            items = self._extract_items(raw)
            # URL 을 카테고리 ID 대용으로 사용
            for item in items:
                if not item.get("id") and item.get("url"):
                    item["id"] = item["url"]
            return items

        # state_var / api 카테고리
        raw = cat_strategy.extract(self.page, config)
        if raw:
            return raw if isinstance(raw, list) else raw.get("items", raw)
        return []

    def _crawl_category_products(
        self, site: dict, cat: dict,
        cat_tmpl: dict, prod_tmpl: dict,
        seen_ids: set, display_order_start: int,
    ) -> list[dict]:
        """한 카테고리의 상품을 페이지 순회하여 수집한다."""
        strategy = get_strategy(prod_tmpl["strategy"])
        config = prod_tmpl["config"]
        page_size = config.get("page_size", DEFAULT_CRAWL_SETTINGS["page_size"])

        cat_config = cat_tmpl["config"]
        url_pattern = cat_config.get("url_pattern", "")
        base_url = site["site_url"].rstrip("/")

        cat_id = cat.get("id", "")
        cat_url = cat.get("url", "")  # DOM 카테고리의 경우 URL 직접 사용

        products = []
        display_order = display_order_start
        page_num = 1

        while True:
            # URL 구성
            if cat_url and cat_url.startswith("http"):
                # 절대 URL (DOM 카테고리)
                url = cat_url
                if page_num > 1:
                    sep = "&" if "?" in url else "?"
                    url = f"{url}{sep}page={page_num}"
            elif cat_url and cat_url.startswith("/"):
                # 상대 URL (DOM 카테고리)
                parsed = urlparse(base_url)
                url = f"{parsed.scheme}://{parsed.hostname}{cat_url}"
                if page_num > 1:
                    sep = "&" if "?" in url else "?"
                    url = f"{url}{sep}page={page_num}"
            else:
                # URL 패턴 기반 (state_var 카테고리)
                url = self._build_url(
                    base_url, url_pattern,
                    cat_id=cat_id, page=page_num,
                )

            resp = self._safe_goto(url)
            if self._is_blocked(resp):
                print(f"[engine]   페이지 차단됨 (HTTP {resp.status}) → 중단")
                break
            self.page.wait_for_timeout(DEFAULT_CRAWL_SETTINGS["page_wait_ms"])

            raw = strategy.extract(self.page, config)
            items = self._extract_items(raw)

            if not items:
                break

            new_count = 0
            for p in items:
                pid = str(p.get("product_id", ""))
                if pid and pid not in seen_ids:
                    seen_ids.add(pid)
                    display_order += 1
                    p["display_order"] = display_order
                    products.append(p)
                    new_count += 1

            print(f"[engine]   page {page_num}: {len(items)}개 "
                  f"(신규 {new_count}개, 총 {len(products) + display_order_start}개)")

            if new_count == 0 or len(items) < page_size:
                break

            page_num += 1
            self._delay()

        return products

    def _crawl_products_scroll(
        self, site: dict, prod_tmpl: dict,
        cat_tmpl: dict | None,
    ) -> list[dict]:
        """무한 스크롤 페이지에서 상품을 수집한다."""
        print("[engine] 무한 스크롤 수집 모드")

        strategy = get_strategy(prod_tmpl["strategy"])
        config = prod_tmpl["config"]
        pagination = config.get("pagination", {})
        max_scrolls = pagination.get("max_scrolls", 30)
        scroll_wait = pagination.get("scroll_wait_ms", 2000)

        all_products = []
        seen_ids = set()
        prev_count = 0

        for scroll_idx in range(max_scrolls):
            # 스크롤
            self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            self.page.wait_for_timeout(scroll_wait)

            raw = strategy.extract(self.page, config)
            items = self._extract_items(raw)

            new_count = 0
            for p in items:
                pid = str(p.get("product_id", p.get("product_name", "")))
                if pid and pid not in seen_ids:
                    seen_ids.add(pid)
                    p["display_order"] = len(all_products) + 1
                    all_products.append(p)
                    new_count += 1

            if len(all_products) == prev_count:
                # 새 상품 없음 → 끝
                print(f"[engine] 스크롤 {scroll_idx + 1}: 추가 상품 없음 → 완료")
                break

            prev_count = len(all_products)
            print(f"[engine] 스크롤 {scroll_idx + 1}: "
                  f"신규 {new_count}개, 총 {len(all_products)}개")

        print(f"\n[engine] 총 {len(all_products)}개 상품 수집 완료")
        return all_products

    def _crawl_products_click(
        self, site: dict, prod_tmpl: dict,
        cat_tmpl: dict | None,
    ) -> list[dict]:
        """클릭 페이지네이션으로 상품을 수집한다."""
        print("[engine] 클릭 페이지네이션 수집 모드")

        strategy = get_strategy(prod_tmpl["strategy"])
        config = prod_tmpl["config"]
        pagination = config.get("pagination", {})
        next_selector = pagination.get("next_button", "")
        max_pages = pagination.get("max_pages", 50)

        if not next_selector:
            # 기본 선택자
            next_selector = (
                "a[class*='next'], button[class*='next'], "
                "[class*='btn_next'], [aria-label='next']"
            )

        all_products = []
        seen_ids = set()

        for page_num in range(1, max_pages + 1):
            raw = strategy.extract(self.page, config)
            items = self._extract_items(raw)

            new_count = 0
            for p in items:
                pid = str(p.get("product_id", p.get("product_name", "")))
                if pid and pid not in seen_ids:
                    seen_ids.add(pid)
                    p["display_order"] = len(all_products) + 1
                    all_products.append(p)
                    new_count += 1

            print(f"[engine] page {page_num}: {len(items)}개 "
                  f"(신규 {new_count}개, 총 {len(all_products)}개)")

            if new_count == 0:
                break

            # 다음 버튼 클릭
            try:
                next_btn = self.page.query_selector(next_selector)
                if not next_btn or not next_btn.is_visible():
                    print("[engine] 다음 버튼 없음 → 완료")
                    break
                next_btn.click()
                self.page.wait_for_timeout(DEFAULT_CRAWL_SETTINGS["page_wait_ms"])
            except Exception as e:
                print(f"[engine] 다음 페이지 이동 실패: {e}")
                break

        print(f"\n[engine] 총 {len(all_products)}개 상품 수집 완료")
        return all_products

    def _crawl_details(
        self, site: dict, templates: list[dict], products: list[dict],
    ) -> list[dict]:
        """상품 상세 정보를 수집한다."""
        print("\n[engine] ── 상품 상세 수집 ──")
        tmpl = self._find_template(templates, "product_detail")
        if not tmpl:
            print("[engine] product_detail 템플릿 없음 → 스킵")
            return products

        strategy = get_strategy(tmpl["strategy"])
        config = tmpl["config"]
        url_pattern = config.get("url_pattern", "")
        base_url = site["site_url"].rstrip("/")
        max_detail = DEFAULT_CRAWL_SETTINGS["max_detail_products"]

        targets = products[:max_detail]
        print(f"[engine] 상세 수집 대상: {len(targets)}개")

        for i, prod in enumerate(targets, 1):
            desc = prod.get("description", "")
            if desc and desc != "N/A" and len(desc) > 20:
                continue

            product_id = prod.get("product_id", "")
            product_url = prod.get("product_url", "")

            # URL 결정: product_url 직접 사용 또는 패턴 생성
            if product_url and product_url.startswith("http"):
                url = product_url
            elif product_url and product_url.startswith("/"):
                parsed = urlparse(base_url)
                url = f"{parsed.scheme}://{parsed.hostname}{product_url}"
            elif product_id and url_pattern:
                url = self._build_url(base_url, url_pattern, product_id=product_id)
            else:
                continue

            safe_name = _safe_print(prod.get("product_name", "N/A")[:30])
            print(f"[engine] [{i}/{len(targets)}] {safe_name}...")

            try:
                resp = self._safe_goto(url)
                if self._is_blocked(resp):
                    print(f"[engine]   상세 페이지 차단됨 → 스킵")
                    continue
                self.page.wait_for_timeout(DEFAULT_CRAWL_SETTINGS["page_wait_ms"])

                detail = strategy.extract(self.page, config)
                if detail:
                    desc_val = detail.get("description", "")
                    if desc_val:
                        prod["description"] = _clean_html(desc_val)[:2000]
                    imgs = detail.get("detail_images", [])
                    if imgs:
                        prod["detail_images"] = imgs
            except Exception as e:
                print(f"[engine]   상세 수집 오류: {e}")

            if i < len(targets):
                self._delay()

        print(f"[engine] 상세 수집 완료")
        return products

    # ═══════════════════════════════════════════════════════════════
    # 유틸리티
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    def _find_template(templates: list[dict], target: str) -> dict | None:
        """템플릿 리스트에서 target 에 해당하는 것을 찾는다."""
        for t in templates:
            if t.get("target") == target:
                return t
        return None

    @staticmethod
    def _extract_items(raw) -> list[dict]:
        """추출 결과에서 아이템 리스트를 꺼낸다."""
        if raw is None:
            return []
        if isinstance(raw, list):
            return raw
        if isinstance(raw, dict):
            return raw.get("items", raw.get("products", []))
        return []

    @staticmethod
    def _build_url(
        base_url: str, pattern: str, **kwargs,
    ) -> str:
        """URL 패턴에 변수를 치환하여 완성한다."""
        if not pattern:
            return base_url

        # {slug} 는 base_url 의 마지막 경로 세그먼트
        slug = base_url.rstrip("/").split("/")[-1]
        kwargs["slug"] = slug

        url_path = pattern
        for key, val in kwargs.items():
            url_path = url_path.replace(f"{{{key}}}", str(val))

        # 쿼리 파라미터 패턴인지 확인
        if url_path.startswith("?"):
            return base_url + url_path

        # 전체 URL 패턴 (외부 API 등)
        if url_path.startswith("http"):
            return url_path

        # 상대 경로 패턴
        origin = "/".join(base_url.rstrip("/").split("/")[:-1])
        return origin + url_path

    @staticmethod
    def _delay():
        """랜덤 딜레이를 적용한다."""
        d = random.uniform(
            DEFAULT_CRAWL_SETTINGS["delay_min"],
            DEFAULT_CRAWL_SETTINGS["delay_max"],
        )
        time.sleep(d)

    def _save_json(self, site: dict, store_info: dict, products: list[dict]):
        """수집 결과를 JSON 파일로 저장한다."""
        import os

        site_name = site["site_name"].replace(" ", "_")
        output_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "output", f"{site['id']}_{site_name}",
        )
        os.makedirs(output_dir, exist_ok=True)

        store_path = os.path.join(output_dir, "store_info.json")
        products_path = os.path.join(output_dir, "products.json")
        result_path = os.path.join(output_dir, "crawl_result.json")

        from datetime import datetime

        result = {
            "crawl_meta": {
                "site_name": site["site_name"],
                "site_url": site["site_url"],
                "crawl_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            },
            "store_info": store_info,
            "products": products,
            "total_products": len(products),
        }

        for path, data in [
            (store_path, store_info),
            (products_path, products),
            (result_path, result),
        ]:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"[engine] 파일 저장: {output_dir}")


# ─── 유틸 ────────────────────────────────────────────────────────

def _safe_print(text: str) -> str:
    """Windows cp949 콘솔에서 안전하게 출력할 수 있는 문자열로 변환한다."""
    try:
        return text.encode("cp949", errors="replace").decode("cp949")
    except Exception:
        return text


def _clean_html(html_text: str) -> str:
    """HTML 태그를 제거하고 순수 텍스트를 반환한다."""
    if not html_text:
        return "N/A"
    cleaned = re.sub(r"<[^>]+>", " ", str(html_text))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned if cleaned else "N/A"
