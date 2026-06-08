"""
프로모션/이벤트 수집 에이전트

경쟁사 면세점 등의 이벤트 페이지에서 이벤트 정보를 수집한다.
상품 수집(ProductAgent)과 분리된 별도의 수집 파이프라인으로 동작한다.

수집 대상:
  - 이벤트 목록 (제목, 기간, 이미지, 상태 등)
  - 이벤트 상세 정보 (내용, 조건, 혜택 등)
  - 이벤트 내 상품 정보 (선택, 존재하지 않을 수 있음)

파이프라인:
  1. 이벤트 목록 페이지 접속 → 이벤트 카드 수집
  2. (선택) 각 이벤트 상세 페이지 방문 → 상세 정보 수집
  3. (선택) 이벤트 상세에서 관련 상품 수집
"""
import json
import re
import time
import random
from urllib.parse import urlparse, urljoin

from core.base_agent import BaseAgent, DEFAULT_SETTINGS


# ─── 프로모션 수집 기본 설정 ────────────────────────────────────
DEFAULT_PROMOTION_SETTINGS = {
    **DEFAULT_SETTINGS,
    "max_events": 50,
    "max_event_products": 20,
}

# ─── 이벤트 목록 추출 JavaScript ────────────────────────────────
# 범용적으로 이벤트 카드 패턴을 탐지한다.
# 사이트별 하드코딩 없이 공통 패턴(반복 구조, 링크, 이미지, 텍스트)을 분석.
_JS_EXTRACT_EVENT_LIST = """() => {
    // 이벤트 카드 후보 셀렉터 (범용 패턴)
    const candidateSelectors = [
        // 시맨틱: event, promotion, campaign 관련
        '[class*="event"] a', '[class*="Event"] a',
        '[class*="promo"] a', '[class*="Promo"] a',
        '[class*="campaign"] a', '[class*="Campaign"] a',
        '[class*="bnr"] a', '[class*="banner"] a',
        // 리스트 구조
        '.event-list li a', '.event_list li a',
        '.promotion-list li a', '.promo-list li a',
        // 그리드/카드 구조
        '[class*="event"] [class*="card"]',
        '[class*="event"] [class*="item"]',
        '[class*="event"] [class*="thumb"]',
        // 일반적 반복 구조
        'ul[class*="event"] li a',
        'ul[class*="list"] li a[href*="event"]',
        'div[class*="list"] a[href*="event"]',
        'div[class*="list"] a[href*="evnt"]',
        'a[href*="eventDetail"]', 'a[href*="event_detail"]',
        'a[href*="evntDetail"]', 'a[href*="evnt_detail"]',
        'a[href*="eventView"]', 'a[href*="event_view"]',
    ];

    const events = [];
    const seenUrls = new Set();

    for (const sel of candidateSelectors) {
        try {
            const els = document.querySelectorAll(sel);
            for (const el of els) {
                // 링크 추출
                const anchor = el.tagName === 'A' ? el : el.querySelector('a');
                const href = anchor ? anchor.href : '';
                if (!href || href === '#' || href === window.location.href) continue;
                if (seenUrls.has(href)) continue;
                seenUrls.add(href);

                // 이미지
                const img = el.querySelector('img');
                const imageUrl = img ? (img.src || img.getAttribute('data-src') || '') : '';

                // 텍스트 추출 (제목 후보)
                const titleEl = el.querySelector(
                    '[class*="title"], [class*="tit"], [class*="name"], h2, h3, h4, strong, em, p'
                );
                let title = '';
                if (titleEl) {
                    title = titleEl.textContent.trim();
                } else {
                    // 이미지 alt 또는 전체 텍스트
                    title = (img && img.alt) ? img.alt.trim() : el.textContent.trim();
                }
                // 너무 긴 텍스트는 잘라냄 (DOM 전체 텍스트인 경우)
                if (title.length > 200) title = title.substring(0, 200);

                // 날짜 추출 시도
                const dateEl = el.querySelector(
                    '[class*="date"], [class*="period"], [class*="term"], time, .date'
                );
                let dateText = dateEl ? dateEl.textContent.trim() : '';

                // 상태 추출 시도
                const statusEl = el.querySelector(
                    '[class*="status"], [class*="state"], [class*="badge"], [class*="label"]'
                );
                let status = statusEl ? statusEl.textContent.trim() : '';

                if (title || imageUrl) {
                    events.push({
                        title: title || '(제목 없음)',
                        event_url: href,
                        image_url: imageUrl,
                        date_text: dateText,
                        status: status,
                    });
                }
            }
        } catch(e) { /* selector 실패 무시 */ }
    }

    // 중복 제거 후 반환
    return events;
}"""

# ─── 이벤트 상세 추출 JavaScript ────────────────────────────────
_JS_EXTRACT_EVENT_DETAIL = """() => {
    // 페이지 제목
    const title = document.querySelector(
        '[class*="event"] h1, [class*="event"] h2, [class*="detail"] h1, ' +
        '[class*="detail"] h2, .event-title, .event_title, ' +
        '[class*="tit"], article h1, .content h1'
    );

    // 이벤트 본문 영역
    const contentEl = document.querySelector(
        '[class*="event"][class*="content"], [class*="event"][class*="detail"], ' +
        '[class*="detail"][class*="content"], [class*="cont"], ' +
        'article, .event-body, .event_body, [class*="evnt"][class*="cont"]'
    );

    // 날짜/기간
    const periodEl = document.querySelector(
        '[class*="period"], [class*="date"], [class*="term"], ' +
        '[class*="duration"], time'
    );

    // 이벤트 이미지들
    const images = [];
    const imgEls = contentEl
        ? contentEl.querySelectorAll('img')
        : document.querySelectorAll('[class*="event"] img, [class*="detail"] img');
    imgEls.forEach(img => {
        const src = img.src || img.getAttribute('data-src');
        if (src && !src.includes('icon') && !src.includes('logo') &&
            img.naturalWidth > 100) {
            images.push(src);
        }
    });

    // 혜택/조건 텍스트
    const benefitEl = document.querySelector(
        '[class*="benefit"], [class*="reward"], [class*="coupon"]'
    );
    const conditionEl = document.querySelector(
        '[class*="condition"], [class*="notice"], [class*="info"]'
    );

    return {
        title: title ? title.textContent.trim() : document.title || '',
        content_text: contentEl ? contentEl.innerText.trim().substring(0, 2000) : '',
        period: periodEl ? periodEl.textContent.trim() : '',
        images: images.slice(0, 10),
        benefits: benefitEl ? benefitEl.innerText.trim().substring(0, 500) : '',
        conditions: conditionEl ? conditionEl.innerText.trim().substring(0, 500) : '',
    };
}"""

# ─── 이벤트 내 상품 추출 JavaScript ─────────────────────────────
_JS_EXTRACT_EVENT_PRODUCTS = """() => {
    // 상품 후보 셀렉터 (이벤트 상세 페이지 내)
    const productSelectors = [
        '[class*="product"] [class*="item"]',
        '[class*="goods"] [class*="item"]',
        '[class*="prd"] [class*="item"]',
        'ul[class*="product"] li',
        'ul[class*="goods"] li',
        'div[class*="product-list"] > div',
        '[class*="item-list"] > div',
        '[class*="item-list"] > li',
    ];

    const products = [];
    const seenNames = new Set();

    for (const sel of productSelectors) {
        try {
            const items = document.querySelectorAll(sel);
            for (const item of items) {
                // 상품명
                const nameEl = item.querySelector(
                    '[class*="name"], [class*="title"], [class*="tit"], ' +
                    '[class*="brand"], h3, h4, strong, a'
                );
                const name = nameEl ? nameEl.textContent.trim() : '';
                if (!name || name.length < 2 || seenNames.has(name)) continue;
                seenNames.add(name);

                // 가격
                const priceEl = item.querySelector(
                    '[class*="price"], [class*="cost"], [class*="won"]'
                );
                let price = priceEl ? priceEl.textContent.trim() : '';

                // 이미지
                const img = item.querySelector('img');
                const imgUrl = img ? (img.src || img.getAttribute('data-src') || '') : '';

                // 링크
                const link = item.querySelector('a');
                const productUrl = link ? link.href : '';

                // 브랜드
                const brandEl = item.querySelector(
                    '[class*="brand"], [class*="maker"]'
                );
                const brand = brandEl ? brandEl.textContent.trim() : '';

                products.push({
                    product_name: name,
                    brand_name: brand,
                    price: price,
                    image_url: imgUrl,
                    product_url: productUrl,
                });
            }
        } catch(e) { /* selector 실패 무시 */ }

        if (products.length > 0) break;  // 첫 매칭에서 중단
    }

    return products;
}"""


class PromotionAgent(BaseAgent):
    """프로모션/이벤트 수집 에이전트

    경쟁사 면세점 등의 이벤트 정보를 수집한다.
    ProductAgent와 달리 이벤트 목록 → 이벤트 상세 → 이벤트 내 상품의
    3단계 계층 구조로 데이터를 수집한다.
    """

    @property
    def agent_type(self) -> str:
        return "promotion"

    # ═══════════════════════════════════════════════════════════════
    # UI config → Agent 내부 config 변환
    # ═══════════════════════════════════════════════════════════════

    def _normalize_config(self, crawl_cfg: dict) -> dict:
        """UI 설정 필드를 Agent 내부 필드로 변환한다.

        UI 필드 → Agent 필드 매핑:
          event_limit_type/count → max_events (0=전체)
          collect_details        → 이벤트 상세 수집 여부
          collect_event_products → 이벤트 내 상품 수집 여부
          event_status_filter    → 이벤트 상태 필터
        """
        cfg = dict(crawl_cfg)

        # ── 이벤트 수집 범위 ──
        event_limit_type = cfg.pop("event_limit_type", "all")
        event_limit_count = cfg.pop("event_limit_count", 50)
        if event_limit_type == "all":
            cfg["max_events"] = 0  # 0 = 전체
        else:
            cfg["max_events"] = int(event_limit_count) or 50

        # ── 상세 수집 여부 ──
        cfg.setdefault("collect_details", True)

        # ── 이벤트 내 상품 수집 ──
        cfg.setdefault("collect_event_products", True)

        # ── 이벤트 상태 필터 ──
        cfg.setdefault("event_status_filter", "all")

        # ── 타입 보정 ──
        if isinstance(cfg.get("max_events"), str):
            cfg["max_events"] = int(cfg["max_events"]) if cfg["max_events"].isdigit() else 50

        for bool_key in ("collect_details", "collect_event_products"):
            if isinstance(cfg.get(bool_key), str):
                cfg[bool_key] = cfg[bool_key].lower() in ("true", "1", "yes")

        return cfg

    # ═══════════════════════════════════════════════════════════════
    # 메인 실행
    # ═══════════════════════════════════════════════════════════════

    def run_site(self, site_id: int):
        """특정 사이트의 이벤트 정보를 수집한다."""
        site = self.db.get_site(site_id)
        if not site:
            print(f"[promotion] 사이트 ID={site_id} 를 찾을 수 없습니다")
            return

        result_id = self.db.create_result(site_id)
        start_time = time.time()
        raw_cfg = self.get_crawl_config(site)
        crawl_cfg = self._normalize_config(raw_cfg)

        print(f"[promotion] 이벤트 수집 시작: {site['site_name']}")
        print(f"[promotion] URL: {site['site_url']}")
        print(f"[promotion] 설정: max_events={crawl_cfg.get('max_events', 0)}, "
              f"collect_details={crawl_cfg.get('collect_details')}, "
              f"collect_event_products={crawl_cfg.get('collect_event_products')}")

        try:
            store_info, events = self._run_event_collection(site, crawl_cfg)

            # 결과 저장
            elapsed = time.time() - start_time
            self.db.update_result(
                result_id,
                status="success",
                store_info=store_info,
                products=events,  # events를 products 필드에 저장 (DB 호환)
                product_count=len(events),
                elapsed_sec=elapsed,
            )

            self._save_json(site, store_info, events)

            print(f"\n[promotion] 수집 완료: {site['site_name']}")
            print(f"  사이트명: {store_info.get('store_name', 'N/A')}")
            print(f"  이벤트 수: {len(events)}")
            detail_count = sum(1 for e in events if e.get("detail"))
            product_count = sum(len(e.get("products", [])) for e in events)
            if detail_count:
                print(f"  상세 수집: {detail_count}건")
            if product_count:
                print(f"  이벤트 내 상품: {product_count}건")
            print(f"  소요 시간: {elapsed:.1f}초")

        except Exception as e:
            elapsed = time.time() - start_time
            self.db.update_result(
                result_id,
                status="failed",
                error_msg=str(e),
                elapsed_sec=elapsed,
            )
            print(f"[promotion] 수집 실패: {e}")

        finally:
            self.browser_mgr.close()
            self.page = None

    # ═══════════════════════════════════════════════════════════════
    # 이벤트 수집 파이프라인
    # ═══════════════════════════════════════════════════════════════

    def _run_event_collection(
        self, site: dict, crawl_cfg: dict,
    ) -> tuple[dict, list[dict]]:
        """이벤트 목록 + 상세를 수집한다.

        파이프라인:
          1. 이벤트 목록 페이지 접속
          2. 이벤트 카드 수집
          3. (선택) 각 이벤트 상세 페이지 방문
          4. (선택) 이벤트 내 상품 수집
        """
        # 1. 브라우저 시작
        cookie_domain = self._get_cookie_domain(site["site_url"])
        self.page = self._create_page(cookie_domain=cookie_domain)

        # 2. 이벤트 목록 페이지 접속
        resp = self._safe_goto(
            site["site_url"], wait_until="domcontentloaded",
        )
        if self._is_blocked(resp):
            raise RuntimeError(
                f"이벤트 페이지 접근 차단됨 (HTTP {resp.status if resp else 'None'})"
            )
        self._human_dwell()
        self._human_scroll()

        # 3. 사이트 정보 수집
        store_info = self._collect_site_info(site)

        # 4. 이벤트 목록 수집
        events = self._collect_event_list(site, crawl_cfg)

        if not events:
            print("[promotion] 이벤트를 찾을 수 없습니다")
            return store_info, []

        # max_events 적용
        max_events = crawl_cfg.get("max_events", 0)
        if max_events > 0 and len(events) > max_events:
            print(f"[promotion] {len(events)}개 이벤트 중 {max_events}개만 수집")
            events = events[:max_events]
        else:
            print(f"[promotion] {len(events)}개 이벤트 발견")

        # 5. display_order 부여
        for i, event in enumerate(events):
            event["display_order"] = i + 1

        # 6. 이벤트 상세 수집
        if crawl_cfg.get("collect_details", True):
            self._collect_event_details(
                events, crawl_cfg, site,
            )

        return store_info, events

    # ═══════════════════════════════════════════════════════════════
    # 사이트 정보 수집
    # ═══════════════════════════════════════════════════════════════

    def _collect_site_info(self, site: dict) -> dict:
        """이벤트 페이지의 사이트(매장) 정보를 수집한다."""
        try:
            info = self.page.evaluate("""() => {
                const getMeta = (name) => {
                    const el = document.querySelector(
                        `meta[property="${name}"], meta[name="${name}"]`
                    );
                    return el ? el.getAttribute('content') : '';
                };
                return {
                    store_name: document.title || '',
                    description: getMeta('og:description') || getMeta('description') || '',
                    logo_url: getMeta('og:image') || '',
                    site_url: window.location.href,
                };
            }""")
            if info:
                # site_name을 우선 사용
                info["store_name"] = site.get("site_name") or info.get("store_name", "N/A")
            return info or {"store_name": site.get("site_name", "N/A")}
        except Exception:
            return {"store_name": site.get("site_name", "N/A")}

    # ═══════════════════════════════════════════════════════════════
    # 이벤트 목록 수집
    # ═══════════════════════════════════════════════════════════════

    def _collect_event_list(
        self, site: dict, crawl_cfg: dict,
    ) -> list[dict]:
        """이벤트 목록 페이지에서 이벤트 카드를 수집한다.

        범용 DOM 분석으로 이벤트 카드를 탐지한다.
        사이트 구조에 따라 여러 셀렉터를 시도한다.
        """
        print("[promotion] 이벤트 목록 수집 중...")

        # SPA 렌더링 대기
        self._trigger_client_render(self.page)

        # JavaScript로 이벤트 카드 추출
        try:
            raw_events = self.page.evaluate(_JS_EXTRACT_EVENT_LIST)
        except Exception as e:
            print(f"[promotion] JS 이벤트 추출 실패: {e}")
            raw_events = []

        if not raw_events:
            # 대안: 네트워크 인터셉트로 API 응답에서 이벤트 데이터 찾기
            raw_events = self._try_network_event_extraction()

        if not raw_events:
            # 최후의 대안: 페이지의 모든 링크에서 이벤트 URL 패턴 찾기
            raw_events = self._try_link_pattern_extraction()

        # URL 정규화
        base_url = site["site_url"]
        for event in raw_events:
            event_url = event.get("event_url", "")
            if event_url and not event_url.startswith("http"):
                event["event_url"] = urljoin(base_url, event_url)

        # 날짜 파싱 시도
        for event in raw_events:
            self._parse_event_dates(event)

        # 상태 필터 적용
        status_filter = crawl_cfg.get("event_status_filter", "all")
        if status_filter == "active":
            raw_events = [
                e for e in raw_events
                if self._is_event_active(e)
            ]
            print(f"[promotion] 진행 중 이벤트 필터: {len(raw_events)}건")

        return raw_events

    def _try_network_event_extraction(self) -> list[dict]:
        """네트워크 요청에서 이벤트 API 응답을 탐지한다."""
        try:
            # 페이지 리로드하면서 네트워크 캡처
            from core.network_interceptor import NetworkInterceptor
            interceptor = NetworkInterceptor(self.page)
            interceptor.start()

            # 스크롤로 추가 데이터 로드 유도
            self._human_scroll()
            self.page.wait_for_timeout(2000)

            interceptor.stop()

            # 이벤트 관련 API 응답 분석
            events = []
            for req in interceptor.captured_requests:
                url = req.get("url", "").lower()
                if any(kw in url for kw in ("event", "promo", "campaign", "evnt")):
                    data = req.get("response_json")
                    if data:
                        found = self._extract_events_from_json(data)
                        if found:
                            events.extend(found)
                            break

            return events
        except Exception:
            return []

    def _extract_events_from_json(
        self, data, depth: int = 0,
    ) -> list[dict]:
        """JSON 응답에서 이벤트 배열을 재귀적으로 탐지한다."""
        if depth > 3:
            return []

        # 리스트인 경우 이벤트 배열인지 확인
        if isinstance(data, list) and len(data) >= 2:
            if all(isinstance(item, dict) for item in data[:5]):
                # 이벤트 관련 필드가 있는지 확인
                sample = data[0]
                event_keys = {"title", "name", "eventName", "evntNm",
                              "eventTitle", "subject", "startDate",
                              "start_date", "endDate", "end_date",
                              "strtDt", "endDt", "imgUrl", "image",
                              "thumbnailUrl", "bannerUrl"}
                if event_keys & set(sample.keys()):
                    return [self._map_event_fields(item) for item in data]

        # dict인 경우 하위 탐색
        if isinstance(data, dict):
            for key, val in data.items():
                result = self._extract_events_from_json(val, depth + 1)
                if result:
                    return result

        return []

    def _map_event_fields(self, item: dict) -> dict:
        """API 응답의 이벤트 필드를 표준 스키마로 매핑한다."""
        # 제목
        title = (
            item.get("title") or item.get("eventTitle") or
            item.get("eventName") or item.get("evntNm") or
            item.get("name") or item.get("subject") or
            item.get("evntTitl") or ""
        )

        # 이벤트 URL
        event_url = (
            item.get("url") or item.get("eventUrl") or
            item.get("detailUrl") or item.get("linkUrl") or ""
        )

        # 이미지
        image_url = (
            item.get("imageUrl") or item.get("imgUrl") or
            item.get("thumbnailUrl") or item.get("bannerUrl") or
            item.get("image") or item.get("thumbImg") or ""
        )

        # 시작일
        start_date = (
            item.get("startDate") or item.get("start_date") or
            item.get("strtDt") or item.get("startDt") or
            item.get("fromDate") or ""
        )

        # 종료일
        end_date = (
            item.get("endDate") or item.get("end_date") or
            item.get("endDt") or item.get("toDate") or ""
        )

        # 상태
        status = (
            item.get("status") or item.get("eventStatus") or
            item.get("state") or ""
        )

        return {
            "title": str(title).strip(),
            "event_url": str(event_url).strip(),
            "image_url": str(image_url).strip(),
            "start_date": str(start_date).strip(),
            "end_date": str(end_date).strip(),
            "status": str(status).strip(),
            "date_text": f"{start_date} ~ {end_date}" if start_date else "",
            "raw_data": {k: str(v)[:200] for k, v in item.items()
                         if k not in ("title", "url", "imageUrl")},
        }

    def _try_link_pattern_extraction(self) -> list[dict]:
        """페이지 내 링크에서 이벤트 URL 패턴을 찾아 수집한다."""
        try:
            links = self.page.evaluate("""() => {
                const anchors = document.querySelectorAll('a[href]');
                const results = [];
                const seen = new Set();
                const eventPatterns = [
                    /event/i, /evnt/i, /promo/i, /campaign/i,
                ];
                for (const a of anchors) {
                    const href = a.href;
                    if (!href || seen.has(href)) continue;
                    if (!eventPatterns.some(p => p.test(href))) continue;
                    // 같은 페이지 링크 제외
                    if (href === window.location.href) continue;
                    // 상세 페이지 패턴 검사
                    if (/detail|view|seq|idx|no=/i.test(href)) {
                        seen.add(href);
                        // 주변 텍스트/이미지
                        const parent = a.closest('li, div, article') || a;
                        const img = parent.querySelector('img');
                        const text = parent.textContent.trim().substring(0, 200);
                        results.push({
                            title: text || (img ? img.alt : '') || '(제목 없음)',
                            event_url: href,
                            image_url: img ? (img.src || '') : '',
                            date_text: '',
                            status: '',
                        });
                    }
                }
                return results;
            }""")
            return links or []
        except Exception:
            return []

    # ═══════════════════════════════════════════════════════════════
    # 이벤트 상세 수집
    # ═══════════════════════════════════════════════════════════════

    def _collect_event_details(
        self, events: list[dict], crawl_cfg: dict, site: dict,
    ):
        """각 이벤트의 상세 페이지를 방문하여 상세 정보를 수집한다."""
        collect_products = crawl_cfg.get("collect_event_products", True)
        total = len(events)
        collected = 0
        max_event_products = crawl_cfg.get("max_event_products", 20)

        print(f"[promotion] 이벤트 상세 수집 시작 ({total}건)")

        for i, event in enumerate(events):
            event_url = event.get("event_url", "")
            if not event_url:
                continue

            title_preview = event.get("title", "")[:40]
            safe_title = _safe_print(title_preview)
            print(f"[promotion]   [{i+1}/{total}] {safe_title}")

            try:
                # 이벤트 상세 페이지 접속
                resp = self._safe_goto(event_url)
                if self._is_blocked(resp):
                    print(f"[promotion]     차단됨 → 스킵")
                    continue

                self._human_dwell()

                # 상세 정보 추출
                detail = self.page.evaluate(_JS_EXTRACT_EVENT_DETAIL)
                if detail:
                    event["detail"] = detail
                    # 상세에서 추출한 제목이 더 정확할 수 있음
                    if detail.get("title") and event.get("title") == "(제목 없음)":
                        event["title"] = detail["title"]

                    collected += 1

                # 이벤트 내 상품 수집 (선택)
                if collect_products:
                    products = self._collect_event_products(max_event_products)
                    if products:
                        event["products"] = products
                        print(f"[promotion]     상품 {len(products)}건")

                self._delay()

            except Exception as e:
                print(f"[promotion]     상세 수집 실패: {e}")
                continue

        print(f"[promotion] 이벤트 상세 수집 완료: {collected}/{total}건")

    def _collect_event_products(
        self, max_products: int = 20,
    ) -> list[dict]:
        """이벤트 상세 페이지에서 관련 상품을 수집한다.

        이벤트에 상품이 포함되지 않을 수 있으며, 그 경우 빈 리스트를 반환한다.
        """
        try:
            # 상품 영역이 있는지 빠르게 확인
            has_products = self.page.evaluate("""() => {
                const sel = '[class*="product"], [class*="goods"], [class*="prd"]';
                return document.querySelectorAll(sel).length > 0;
            }""")

            if not has_products:
                return []

            # 스크롤하여 lazy-load 상품 로드
            self._human_scroll()

            products = self.page.evaluate(_JS_EXTRACT_EVENT_PRODUCTS)
            if products and max_products > 0:
                products = products[:max_products]

            return products or []

        except Exception:
            return []

    # ═══════════════════════════════════════════════════════════════
    # 날짜 파싱 / 상태 판별
    # ═══════════════════════════════════════════════════════════════

    def _parse_event_dates(self, event: dict):
        """이벤트의 date_text에서 시작일/종료일을 파싱한다."""
        date_text = event.get("date_text", "")
        if not date_text:
            return

        # 일반적 날짜 패턴: YYYY.MM.DD, YYYY-MM-DD, MM/DD, MM.DD
        date_pattern = r'(\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2})'
        dates = re.findall(date_pattern, date_text)

        if len(dates) >= 2:
            event.setdefault("start_date", dates[0])
            event.setdefault("end_date", dates[1])
        elif len(dates) == 1:
            event.setdefault("start_date", dates[0])

    def _is_event_active(self, event: dict) -> bool:
        """이벤트가 현재 진행 중인지 판별한다."""
        status = event.get("status", "").lower()

        # 명시적 상태 텍스트
        inactive_keywords = ["종료", "마감", "ended", "closed", "expired", "완료"]
        if any(kw in status for kw in inactive_keywords):
            return False

        active_keywords = ["진행", "진행중", "ongoing", "active", "ing"]
        if any(kw in status for kw in active_keywords):
            return True

        # 상태를 판별할 수 없으면 포함 (보수적 접근)
        return True

    # ═══════════════════════════════════════════════════════════════
    # 결과 저장
    # ═══════════════════════════════════════════════════════════════

    def _save_json(
        self, site: dict, store_info: dict, events: list[dict],
    ):
        """수집 결과를 JSON 파일로 저장한다."""
        import os

        site_name = _safe_filename(site.get("site_name", "unknown"))
        site_id = site["id"]
        out_dir = os.path.join("output", f"{site_id}_{site_name}")
        os.makedirs(out_dir, exist_ok=True)

        # 매장 정보
        with open(
            os.path.join(out_dir, "store_info.json"), "w", encoding="utf-8",
        ) as f:
            json.dump(store_info, f, ensure_ascii=False, indent=2)

        # 이벤트 목록
        with open(
            os.path.join(out_dir, "events.json"), "w", encoding="utf-8",
        ) as f:
            json.dump(events, f, ensure_ascii=False, indent=2)

        # 통합 결과
        result = {
            "site_id": site_id,
            "site_name": site["site_name"],
            "agent_type": "promotion",
            "store_info": store_info,
            "events": events,
            "event_count": len(events),
            "detail_count": sum(1 for e in events if e.get("detail")),
            "product_count": sum(
                len(e.get("products", [])) for e in events
            ),
        }
        with open(
            os.path.join(out_dir, "crawl_result.json"), "w",
            encoding="utf-8",
        ) as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print(f"[promotion] 결과 저장: {out_dir}/")


# ═══════════════════════════════════════════════════════════════════
# 유틸리티
# ═══════════════════════════════════════════════════════════════════

def _safe_print(text: str) -> str:
    """cp949 인코딩 문제를 우회하여 안전하게 출력용 문자열을 반환한다."""
    try:
        text.encode("cp949")
        return text
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text.encode("ascii", errors="replace").decode("ascii")


def _safe_filename(name: str) -> str:
    """파일명에 사용할 수 없는 문자를 제거한다."""
    return re.sub(r'[\\/*?:"<>|]', "_", name)
