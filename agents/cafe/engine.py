"""
네이버 카페 인기글 수집 에이전트

네이버 카페의 인기글 게시판에서 게시글 목록을 수집하고,
각 게시글의 본문에서 상품 정보를 추출한다.

파이프라인:
  1. 인기글 목록 접속 (iframe URL 직접 접근)
  2. 페이지네이션 순회 (?p=1, ?p=2, ...)
  3. 날짜 필터 적용 (date_from ~ date_to)
  4. 각 게시글 상세 접속
  5. 본문 추출 (.se-main-container)
  6. 상품 정보 파싱 (상품명, 가격, 외부링크, 이미지)
  7. 결과 저장

crawl_config 예시:
  {"date_range_days": 3}         → 실행 시점 기준 최근 3일 게시글 수집
  {"date_from": "2026-05-20"}    → 해당 날짜 이후 게시글만 수집
  {"date_to": "2026-05-25"}      → 해당 날짜 이전 게시글만 수집
  {"collect_body": false}        → 본문 수집 생략 (목록만)
  {"collect_links": true}        → 본문 내 외부링크 수집
  {"collect_images": true}       → 본문 내 이미지 URL 수집
  {"collect_ocr": true}          → 이미지 OCR로 가격 추출 (Upstage API)

  date_range_days 설정 시 date_from/date_to는 자동 계산된다.
  모두 생략 시 전체 페이지 수집.
"""
import json
import os
import re
import time
from datetime import datetime, timedelta
from urllib.parse import urlparse

from core.base_agent import BaseAgent, DEFAULT_SETTINGS
from core.ocr import OCRManager


# ─── 카페 수집 기본 설정 ─────────────────────────────────────────
DEFAULT_CAFE_SETTINGS = {
    **DEFAULT_SETTINGS,
    "max_body_length": 8000,
    "max_pages": 200,           # 무한 루프 방지용 최대 페이지
}

# ─── 네이버 카페 인기글 iframe URL 패턴 ─────────────────────────
_CAFE_POPULAR_IFRAME_URL = (
    "https://cafe.naver.com/ca-fe/cafes/{cafe_id}/popular"
)

# ─── 인기글 목록 추출 JS ─────────────────────────────────────────
_JS_POPULAR_LIST_EXTRACT = r"""() => {
    var links = document.querySelectorAll('a.article[href]');
    var results = [];
    var seen = {};

    for (var i = 0; i < links.length; i++) {
        var a = links[i];
        var href = a.getAttribute('href') || '';
        var text = a.textContent.trim();

        if (text.length < 3) continue;
        if (href.indexOf('/articles/') === -1) continue;

        // article_id 추출
        var idMatch = href.match(/\/articles\/(\d+)/);
        if (!idMatch) continue;
        var articleId = idMatch[1];
        if (seen[articleId]) continue;
        seen[articleId] = true;

        // 같은 행(row)에서 작성자, 날짜, 조회수 추출
        // tr을 우선 탐색 (inner_list는 td 하위라 날짜 없음)
        var row = a.closest('tr');
        if (!row) row = a.closest('.inner_list, [class*="item"]');
        var author = '';
        var date = '';
        var views = '';

        if (row) {
            // 작성자 (td.td_name > .nickname)
            var authorEl = row.querySelector(
                'td.td_name .nickname, .nickname, .nick'
            );
            if (authorEl) author = authorEl.textContent.trim();

            // 날짜 (td.td_date)
            var dateEl = row.querySelector(
                'td.td_date, .date, td:nth-child(3)'
            );
            if (dateEl) date = dateEl.textContent.trim();

            // 조회수 (td.td_view)
            var viewEl = row.querySelector(
                'td.td_view, .view, td:nth-child(4)'
            );
            if (viewEl) views = viewEl.textContent.trim();
        }

        var fullUrl = href;
        if (href.indexOf('http') !== 0) {
            fullUrl = 'https://cafe.naver.com' + href;
        }

        results.push({
            article_id: articleId,
            title: text.substring(0, 200),
            url: fullUrl,
            author: author.substring(0, 50),
            date: date.substring(0, 30),
            views: views.substring(0, 20),
        });
    }

    return results;
}"""

# ─── 게시글 본문 추출 JS ─────────────────────────────────────────
_JS_CAFE_ARTICLE_EXTRACT = r"""() => {
    // 본문 컨테이너 탐색
    var bodySelectors = [
        '.se-main-container',
        '.ContentRenderer',
        '.article_viewer',
        '.content_view',
        '#body',
    ];

    var bodyEl = null;
    var usedSelector = '';
    for (var i = 0; i < bodySelectors.length; i++) {
        var el = document.querySelector(bodySelectors[i]);
        if (el && el.innerText.trim().length > 20) {
            bodyEl = el;
            usedSelector = bodySelectors[i];
            break;
        }
    }

    if (!bodyEl) {
        return null;
    }

    var bodyText = bodyEl.innerText.trim();

    // 제목
    var titleEl = document.querySelector(
        '.title_text, .art_tit, h3.title_text,'
        + ' [class*="article_title"], [class*="subject"]'
    );
    var title = titleEl ? titleEl.innerText.trim() : '';

    // 작성자
    var authorEl = document.querySelector(
        '.nickname, .nick, [class*="nickname"]'
    );
    var author = authorEl ? authorEl.innerText.trim() : '';

    // 날짜
    var dateEl = document.querySelector(
        '.date, time, [class*="date"]'
    );
    var date = dateEl ? dateEl.textContent.trim() : '';

    // 조회수
    var viewEl = document.querySelector(
        '.count, [class*="view"], [class*="hit"]'
    );
    var views = viewEl ? viewEl.textContent.trim() : '';

    // 카테고리
    var catEl = document.querySelector(
        '.board_name, [class*="category"], [class*="board"]'
    );
    var category = catEl ? catEl.textContent.trim() : '';

    // 본문 내 링크 추출
    var linkEls = bodyEl.querySelectorAll('a[href]');
    var links = [];
    var seenHref = {};
    for (var j = 0; j < linkEls.length; j++) {
        var href = linkEls[j].getAttribute('href') || '';
        var linkText = linkEls[j].textContent.trim();
        if (!href || href === '#') continue;
        if (seenHref[href]) continue;
        seenHref[href] = true;
        links.push({
            text: linkText.substring(0, 150),
            url: href.substring(0, 500),
        });
    }

    // 본문 내 이미지 추출
    var imgEls = bodyEl.querySelectorAll('img');
    var images = [];
    for (var k = 0; k < imgEls.length; k++) {
        var src = imgEls[k].getAttribute('src') || '';
        var alt = imgEls[k].getAttribute('alt') || '';
        if (!src) continue;
        // 이모티콘/아이콘 제외 (작은 이미지)
        var w = imgEls[k].naturalWidth || imgEls[k].width || 0;
        var h = imgEls[k].naturalHeight || imgEls[k].height || 0;
        if (w > 0 && w < 50 && h > 0 && h < 50) continue;
        images.push({
            src: src.substring(0, 500),
            alt: alt.substring(0, 100),
        });
    }

    // ─── 가격 + 상품명 페어링 추출 ───
    // 비상품 키워드 (식대, 회비, 인당 등은 상품 가격이 아님)
    var nonProductWords = [
        '식대', '회비', '1인당', '인당', '÷', '나누기',
        '송금', '입금', '팔로워', '팔로잉', '게시물',
    ];

    var priceItems = [];
    var seenPrices = {};  // 중복 방지
    var bodyLines = bodyText.split('\n');

    for (var li = 0; li < bodyLines.length; li++) {
        var line = bodyLines[li].trim();
        if (!line) continue;

        // 가격 패턴: N,NNN원 또는 N,NNN (콤마 포함 숫자)
        var linePriceRe = /(\d{1,3}(?:,\d{3})+)\s*원?/g;
        var pm;
        while ((pm = linePriceRe.exec(line)) !== null) {
            var priceStr = pm[0];
            var priceNum = parseInt(pm[1].replace(/,/g, ''));
            if (priceNum < 1000 || priceNum > 100000000) continue;

            // 원 단위 정규화 (143,000원과 143,000 중복 방지)
            var normalizedPrice = pm[1];
            if (seenPrices[normalizedPrice]) continue;
            seenPrices[normalizedPrice] = true;

            // 비상품 키워드가 포함된 줄은 건너뛰기
            var isNonProduct = false;
            for (var npi = 0; npi < nonProductWords.length; npi++) {
                if (line.indexOf(nonProductWords[npi]) > -1) {
                    isNonProduct = true;
                    break;
                }
            }
            if (isNonProduct) continue;

            var product = '';

            // 패턴1: 슬래시 구분 (상품명/가격/구입처)
            var slashParts = line.split('/');
            if (slashParts.length >= 2) {
                // 가격이 포함된 파트 찾기
                for (var si = 0; si < slashParts.length; si++) {
                    if (slashParts[si].indexOf(pm[1]) > -1 && si > 0) {
                        product = slashParts[si - 1].trim();
                        // 앞 파트에서 번호 제거 (예: "1. 상품명")
                        product = product.replace(/^\d+\.\s*/, '');
                        break;
                    }
                }
            }

            // 패턴2: 번호+콜론 (N. 상품명 ... : 가격)
            if (!product) {
                var colonIdx = line.lastIndexOf(':');
                if (colonIdx > -1 && line.indexOf(pm[1]) > colonIdx) {
                    var beforeColon = line.substring(0, colonIdx).trim();
                    // 번호 접두사 제거
                    beforeColon = beforeColon.replace(/^\d+\.\s*/, '');
                    // ■구입가격 필드인 경우 → 제목을 상품명으로
                    if (beforeColon.indexOf('구입가격') > -1
                        || beforeColon.indexOf('구입 가격') > -1) {
                        product = title;
                    } else if (beforeColon.length > 1
                               && beforeColon.length < 100) {
                        product = beforeColon;
                    }
                }
            }

            // 패턴3: ■구입가격 가격 (콜론 없이)
            if (!product) {
                if (line.indexOf('구입가격') > -1
                    || line.indexOf('구입 가격') > -1) {
                    product = title;
                }
            }

            // 패턴4: 가격 앞 텍스트에서 상품명 추출 (자연어)
            if (!product) {
                var beforePrice = line.substring(0, pm.index).trim();
                // 뒤에서부터 가격/숫자/기호 제거
                beforePrice = beforePrice.replace(/[\s,.:;/]+$/, '');
                if (beforePrice.length > 1 && beforePrice.length < 100) {
                    // 번호 접두사 제거
                    beforePrice = beforePrice.replace(/^\d+\.\s*/, '');
                    // 일반적 접두사 제거
                    beforePrice = beforePrice.replace(
                        /^(현재\s*(금액)?|그렇게\s*적용하면\s*(가격이)?|무려)\s*/,
                        ''
                    );
                    if (beforePrice.length > 1) {
                        product = beforePrice;
                    }
                }
            }

            priceItems.push({
                product: product.substring(0, 150),
                price: priceStr.trim(),
                context: line.substring(0, 200),
            });
        }
    }

    return {
        title: title.substring(0, 300),
        author: author.substring(0, 50),
        date: date.substring(0, 50),
        views: views.substring(0, 30),
        category: category.substring(0, 50),
        body: bodyText.substring(0, 10000),
        links: links,
        images: images,
        prices: priceItems,
        selector: usedSelector,
    };
}"""


class CafeAgent(BaseAgent):
    """네이버 카페 인기글 수집 에이전트"""

    @property
    def agent_type(self) -> str:
        return "cafe"

    # ═══════════════════════════════════════════════════════════════
    # UI config → Agent 내부 config 변환
    # ═══════════════════════════════════════════════════════════════

    def _normalize_config(self, crawl_cfg: dict) -> dict:
        """UI 설정 필드를 Agent 내부 필드로 정규화한다.

        UI 필드와 Agent 필드는 동일하지만,
        기본값 적용 및 타입 보정을 수행한다.

        UI 필드 → Agent 필드:
          date_from       → date_from (동일)
          date_to         → date_to (동일)
          collect_body    → collect_body (동일)
          collect_links   → collect_links (동일)
          collect_images  → collect_images (동일)
          collect_ocr     → collect_ocr (동일)
        """
        cfg = dict(crawl_cfg)

        # 기본값 적용
        cfg.setdefault("collect_body", True)
        cfg.setdefault("collect_links", True)
        cfg.setdefault("collect_images", True)
        cfg.setdefault("collect_ocr", False)
        cfg.setdefault(
            "max_pages",
            DEFAULT_CAFE_SETTINGS["max_pages"],
        )

        # 빈 문자열 날짜 → None 변환 (UI에서 빈 값 전송 시)
        for date_key in ("date_from", "date_to"):
            if date_key in cfg and not cfg[date_key]:
                cfg[date_key] = None

        return cfg

    # ═══════════════════════════════════════════════════════════════
    # 메인 실행
    # ═══════════════════════════════════════════════════════════════

    def run_site(self, site_id: int):
        """카페 인기글에서 게시글과 상품 정보를 수집한다."""
        site = self.db.get_site(site_id)
        if not site:
            print(f"[cafe] 사이트 ID={site_id} 를 찾을 수 없습니다")
            return

        result_id = self.db.create_result(site_id)
        start_time = time.time()
        raw_cfg = self.get_crawl_config(site)
        crawl_cfg = self._normalize_config(raw_cfg)

        try:
            cookie_domain = self._get_cookie_domain(site["site_url"])
            self.page = self._create_page(cookie_domain=cookie_domain)

            # 1. 인기글 목록 수집 (날짜 필터 적용)
            posts = self._collect_popular_list(site, crawl_cfg)

            # 2. 각 게시글 상세 + 상품 정보 수집
            if crawl_cfg.get("collect_body", True) and posts:
                posts = self._collect_post_details(site, posts, crawl_cfg)

            # 결과 저장
            elapsed = time.time() - start_time
            self.db.update_result(
                result_id,
                status="success",
                store_info={"site_name": site["site_name"]},
                products=posts,
                product_count=len(posts),
                elapsed_sec=elapsed,
            )

            self._save_json(site, posts)

            print(f"\n[cafe] 수집 완료: {site['site_name']}")
            print(f"  게시글 수: {len(posts)}")
            body_count = sum(1 for p in posts if p.get("body"))
            print(f"  본문 수집: {body_count}개")
            product_count = sum(
                1 for p in posts
                if p.get("prices") or p.get("product_links")
            )
            print(f"  상품 정보 포함: {product_count}개")
            print(f"  소요 시간: {elapsed:.1f}초")

        except Exception as e:
            elapsed = time.time() - start_time
            self.db.update_result(
                result_id,
                status="failed",
                error_msg=str(e),
                elapsed_sec=elapsed,
            )
            print(f"[cafe] 수집 실패: {e}")

        finally:
            self.browser_mgr.close()
            self.page = None

    # ═══════════════════════════════════════════════════════════════
    # 인기글 목록 수집 (SPA 버튼 클릭 페이지네이션 + 날짜 필터)
    # ═══════════════════════════════════════════════════════════════

    def _collect_popular_list(
        self, site: dict, crawl_cfg: dict,
    ) -> list[dict]:
        """인기글 게시판을 SPA 버튼 클릭으로 순회하며 게시글 목록을 수집한다.

        네이버 카페 인기글은 SPA 방식으로 페이징된다.
        URL 직접 접속 시 항상 1페이지로 리다이렉트되므로,
        페이지 내 버튼 클릭으로 페이지를 이동해야 한다.

        crawl_config에서 date_from/date_to가 지정되면 해당 범위 내
        게시글만 수집하고, 범위 밖 게시글은 건너뛴다.
        두 값 모두 생략 시 전체 페이지를 수집한다.

        종료 조건:
          - 현재 페이지에 새 게시글이 0개 (마지막 페이지 또는 중복)
          - 현재 페이지 게시글 전체가 date_from 이전 (오래된 글)
          - 다음 페이지 버튼이 없음 (마지막 그룹)
          - max_pages 도달 (안전 장치)
        """
        print("\n[cafe] ── 인기글 목록 수집 (전체 페이지) ──")

        # 날짜 범위 결정
        # 우선순위: date_from/date_to 직접 지정 > date_range_days 자동 계산
        date_from = _parse_date_config(crawl_cfg.get("date_from"))
        date_to = _parse_date_config(crawl_cfg.get("date_to"))
        date_range_days = crawl_cfg.get("date_range_days")

        if date_range_days and not date_from:
            today = datetime.now().replace(
                hour=0, minute=0, second=0, microsecond=0,
            )
            date_from = today - timedelta(days=int(date_range_days) - 1)
            date_to = today

        max_pages = crawl_cfg.get(
            "max_pages",
            DEFAULT_CAFE_SETTINGS["max_pages"],
        )

        if date_from:
            print(f"[cafe] 수집 시작일: {date_from.strftime('%Y-%m-%d')}")
        if date_to:
            print(f"[cafe] 수집 종료일: {date_to.strftime('%Y-%m-%d')}")
        if not date_from and not date_to:
            print("[cafe] 날짜 필터 없음 → 전체 수집")

        # cafe_id 추출
        cafe_id = self._extract_cafe_id(site["site_url"])
        if not cafe_id:
            raise RuntimeError(
                f"카페 ID를 추출할 수 없습니다: {site['site_url']}"
            )
        print(f"[cafe] 카페 ID: {cafe_id}")

        # 1페이지 접속 (iframe URL 직접 접근)
        popular_url = _CAFE_POPULAR_IFRAME_URL.replace(
            "{cafe_id}", cafe_id,
        )
        print(f"[cafe] 인기글 URL: {popular_url}")

        resp = self._safe_goto(
            popular_url, wait_until="domcontentloaded",
        )
        if self._is_blocked(resp):
            raise RuntimeError(
                f"인기글 페이지 접근 차단됨 (HTTP {resp.status})"
            )

        self._human_dwell()
        self._human_scroll()

        all_posts = []
        seen_ids = set()
        page_num = 1

        while page_num <= max_pages:
            print(f"\n[cafe] ── 페이지 {page_num} ──")

            # 게시글 목록 추출
            try:
                raw_posts = self.page.evaluate(
                    _JS_POPULAR_LIST_EXTRACT,
                )
            except Exception as e:
                print(f"[cafe] 페이지 {page_num} 추출 실패: {e}")
                break

            # 빈 페이지 → 종료
            if not raw_posts:
                print(f"[cafe] 페이지 {page_num}: 게시글 없음 → 종료")
                break

            # 중복 제거 + 날짜 필터
            page_added = 0
            page_before_range = 0

            for post in raw_posts:
                aid = post.get("article_id", "")
                if aid in seen_ids:
                    continue
                seen_ids.add(aid)

                # 날짜 파싱
                post_date = _parse_post_date(post.get("date", ""))

                # date_to 이후 게시글 건너뛰기
                if date_to and post_date and post_date > date_to:
                    continue

                # date_from 이전 게시글 카운트
                if date_from and post_date and post_date < date_from:
                    page_before_range += 1
                    continue

                post["display_order"] = len(all_posts) + 1
                all_posts.append(post)
                page_added += 1

            print(
                f"[cafe] 페이지 {page_num}: "
                f"{len(raw_posts)}개 발견, {page_added}개 추가"
                f" (누적 {len(all_posts)}개)"
            )

            # 추가된 게시글 미리보기
            preview_start = len(all_posts) - page_added
            for p in all_posts[preview_start:preview_start + 3]:
                safe_title = _safe_print(p["title"][:50])
                safe_date = _safe_print(p.get("date", ""))
                print(
                    f"  [{p['display_order']}] "
                    f"{safe_title} ({safe_date})"
                )
            if page_added > 3:
                print(f"  ... 외 {page_added - 3}개")

            # 조기 종료 1: 새 게시글 없음 (중복 페이지)
            if page_added == 0 and page_before_range == 0:
                print(
                    f"[cafe] 페이지 {page_num}: "
                    f"새 게시글 없음 → 종료"
                )
                break

            # 조기 종료 2: 전체가 date_from 이전
            if (date_from and page_before_range > 0
                    and page_added == 0):
                print(
                    f"[cafe] 페이지 {page_num} 전체가 "
                    f"수집 시작일 이전 → 종료"
                )
                break

            # 다음 페이지로 이동 (SPA 버튼 클릭)
            next_page = page_num + 1
            clicked = self._click_page_button(next_page)
            if not clicked:
                print(
                    f"[cafe] 페이지 {next_page} 버튼 없음 → "
                    f"마지막 페이지"
                )
                break

            # 페이지 전환 대기
            self.page.wait_for_timeout(
                DEFAULT_CAFE_SETTINGS.get("page_wait_ms", 3000)
            )
            self._human_dwell()

            page_num = next_page

        print(
            f"\n[cafe] 목록 수집 완료: 총 {len(all_posts)}개 "
            f"({page_num}페이지 탐색)"
        )
        return all_posts

    def _click_page_button(self, target_page: int) -> bool:
        """SPA 페이지네이션에서 특정 페이지 번호 버튼을 클릭한다.

        직접 숫자 버튼이 보이면 클릭하고,
        보이지 않으면 '다음' 버튼으로 페이지 그룹을 이동한 뒤 재시도한다.

        Returns:
            True if 클릭 성공, False if 버튼을 찾을 수 없음
        """
        result = self.page.evaluate(r"""(targetPage) => {
            var container = document.querySelector(
                '.ArticlePaginate, [class*="Paginate"]'
            );
            if (!container) return {error: 'no container'};

            // 1. 직접 숫자 버튼 클릭 시도
            var buttons = container.querySelectorAll('button');
            for (var i = 0; i < buttons.length; i++) {
                var text = buttons[i].textContent.trim();
                if (text === String(targetPage)) {
                    buttons[i].click();
                    return {clicked: true, method: 'direct'};
                }
            }

            // 2. '다음' 그룹 버튼 클릭 (현재 보이는 페이지보다 큰 경우)
            for (var j = 0; j < buttons.length; j++) {
                var cls = buttons[j].className || '';
                if (cls.indexOf('type_next') > -1
                    || cls.indexOf('btn_next') > -1
                    || cls.indexOf('next') > -1) {
                    if (!buttons[j].disabled) {
                        buttons[j].click();
                        return {clicked: true, method: 'next_group'};
                    } else {
                        return {error: 'next disabled'};
                    }
                }
            }

            return {error: 'button not found'};
        }""", target_page)

        if not result or result.get("error"):
            return False

        # '다음' 그룹 버튼으로 이동한 경우 → 대기 후 숫자 버튼 재클릭
        if result.get("method") == "next_group":
            self.page.wait_for_timeout(2000)
            retry = self.page.evaluate(r"""(targetPage) => {
                var container = document.querySelector(
                    '.ArticlePaginate, [class*="Paginate"]'
                );
                if (!container) return {error: 'no container'};
                var buttons = container.querySelectorAll('button');
                for (var i = 0; i < buttons.length; i++) {
                    if (buttons[i].textContent.trim()
                        === String(targetPage)) {
                        buttons[i].click();
                        return {clicked: true};
                    }
                }
                // 다음 그룹 후 자동으로 올바른 페이지일 수도 있음
                return {clicked: true, auto: true};
            }""", target_page)
            return bool(retry and not retry.get("error"))

        return True

    # ═══════════════════════════════════════════════════════════════
    # 게시글 상세 + 상품 정보 수집
    # ═══════════════════════════════════════════════════════════════

    def _collect_post_details(
        self, site: dict, posts: list[dict], crawl_cfg: dict,
    ) -> list[dict]:
        """각 게시글 상세 페이지에서 본문과 상품 정보를 추출한다."""
        print(f"\n[cafe] ── 게시글 상세 수집 ({len(posts)}개) ──")

        max_body_len = DEFAULT_CAFE_SETTINGS["max_body_length"]
        collect_links = crawl_cfg.get("collect_links", True)
        collect_images = crawl_cfg.get("collect_images", True)
        collect_ocr = crawl_cfg.get("collect_ocr", True)

        # OCR 클라이언트 초기화 (실패해도 크롤링은 계속)
        ocr_client = None
        site_id = site.get("id", 0)
        if collect_ocr:
            try:
                ocr_client = OCRManager()
            except ValueError as e:
                print(f"[cafe] OCR 비활성화: {e}")

        for i, post in enumerate(posts, 1):
            url = post.get("url", "")
            if not url:
                continue

            safe_title = _safe_print(post.get("title", "N/A")[:40])
            print(f"[cafe] [{i}/{len(posts)}] {safe_title}...")

            try:
                resp = self._safe_goto(url, wait_until="domcontentloaded")
                if self._is_blocked(resp):
                    print("[cafe]   차단됨 → 스킵")
                    continue

                self._human_dwell()

                # 본문 + 상품 정보 추출
                detail = self.page.evaluate(_JS_CAFE_ARTICLE_EXTRACT)
                if not detail:
                    print("[cafe]   본문 추출 실패")
                    continue

                # 본문 텍스트
                body = detail.get("body", "")
                if body:
                    post["body"] = body[:max_body_len]

                # 메타 정보 보강
                if detail.get("title"):
                    post["title"] = detail["title"]
                if detail.get("author") and not post.get("author"):
                    post["author"] = detail["author"]
                if detail.get("date") and not post.get("date"):
                    post["date"] = detail["date"]
                if detail.get("views"):
                    post["views"] = detail["views"]
                if detail.get("category"):
                    post["category"] = detail["category"]

                # 가격 정보 (본문 텍스트)
                prices = detail.get("prices", [])
                if prices:
                    post["prices"] = prices

                # 외부 링크 (상품 링크 분류)
                if collect_links:
                    links = detail.get("links", [])
                    product_links = []
                    other_links = []
                    for lnk in links:
                        link_url = lnk.get("url", "")
                        if self._is_product_link(link_url):
                            product_links.append(lnk)
                        else:
                            other_links.append(lnk)
                    if product_links:
                        post["product_links"] = product_links
                    if other_links:
                        post["other_links"] = other_links

                # 이미지
                images = detail.get("images", [])
                if collect_images and images:
                    post["images"] = images

                # ── 이미지 OCR로 추가 가격 추출 ──
                if ocr_client and images:
                    ocr_prices = self._extract_prices_from_images(
                        ocr_client, images, post.get("title", ""),
                        site_id=site_id,
                        post_id=post.get("post_id", ""),
                    )
                    if ocr_prices:
                        existing = post.get("prices", [])
                        # 기존 가격과 합산 (중복 제거)
                        existing_set = set()
                        for p in existing:
                            if isinstance(p, dict):
                                existing_set.add(p.get("price", ""))
                            else:
                                existing_set.add(p)
                        for op in ocr_prices:
                            if op["price"] not in existing_set:
                                existing.append(op)
                                existing_set.add(op["price"])
                        post["prices"] = existing

            except Exception as e:
                print(f"[cafe]   오류: {e}")

            if i < len(posts):
                self._delay()

        body_count = sum(1 for p in posts if p.get("body"))
        print(f"[cafe] 상세 수집 완료: {body_count}/{len(posts)}개 성공")
        return posts

    def _extract_prices_from_images(
        self,
        ocr_client: OCRManager,
        images: list[dict],
        post_title: str,
        site_id: int = 0,
        post_id: str = "",
    ) -> list[dict]:
        """이미지 OCR 텍스트에서 가격-상품명 쌍을 추출한다.

        Document Parse 우선 → 실패 시 Tesseract fallback.
        elements 좌표가 있으면 좌표 기반 매칭, 없으면 텍스트 기반.
        각 가격 항목에 사용한 엔진(ocr_engine) 비고를 기록한다.
        DB에 OCR 사용 이력을 기록한다.

        Args:
            ocr_client: OCR 매니저
            images: 이미지 목록 [{"src": ..., "alt": ...}, ...]
            post_title: 게시글 제목 (상품명 fallback)
            site_id: 사이트 ID (DB 이력 기록용)
            post_id: 게시글 ID (DB 이력 기록용)

        Returns:
            가격-상품명 쌍 리스트
            [{"product", "price", "context", "source", "ocr_engine"}, ...]
        """
        all_ocr_prices = []

        for img in images:
            src = img.get("src", "")
            if not src or not src.startswith("http"):
                continue

            # 작은 이미지 건너뛰기 (아이콘 등)
            w = img.get("w", 0)
            h = img.get("h", 0)
            if w and h and w < 100 and h < 100:
                continue

            # OCR 추출 (Document Parse → Tesseract fallback)
            parsed = ocr_client.extract(src)
            engine = parsed.get("engine", "")
            status = parsed.get("status", "fail")
            ocr_text = parsed.get("text", "")
            elements = parsed.get("elements", [])
            elapsed_ms = parsed.get("elapsed_ms", 0)
            error = parsed.get("error", "")

            # 가격 추출
            prices = []
            if ocr_text and len(ocr_text) >= 5:
                if elements:
                    prices = _extract_prices_from_elements(
                        elements, post_title,
                    )
                else:
                    prices = _extract_prices_from_text(
                        ocr_text, post_title,
                    )

            if prices:
                for p in prices:
                    p["source"] = "ocr"
                    p["ocr_engine"] = engine
                all_ocr_prices.extend(prices)
                print(
                    f"[cafe]   OCR({engine}): "
                    f"{len(prices)}개 가격 추출"
                )

            # ── DB에 사용 이력 기록 ──
            if site_id:
                try:
                    self.db.add_ocr_usage(
                        site_id=site_id,
                        engine=engine or "unknown",
                        status=status,
                        post_id=str(post_id),
                        image_url=src,
                        text_length=len(ocr_text),
                        price_count=len(prices),
                        elapsed_ms=elapsed_ms,
                        error_msg=error,
                    )
                except Exception:
                    pass  # 이력 기록 실패해도 크롤링 계속

        return all_ocr_prices

    # ═══════════════════════════════════════════════════════════════
    # 유틸리티
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    def _extract_cafe_id(url: str) -> str:
        """사이트 URL에서 카페 ID를 추출한다."""
        # /cafes/14538121 패턴
        match = re.search(r"/cafes/(\d+)", url)
        if match:
            return match.group(1)
        # cafeId=14538121 패턴
        match = re.search(r"cafeId=(\d+)", url)
        if match:
            return match.group(1)
        return ""

    @staticmethod
    def _is_product_link(url: str) -> bool:
        """URL이 상품/쇼핑 관련 링크인지 판별한다."""
        product_domains = [
            "smartstore.naver.com", "brand.naver.com",
            "shopping.naver.com", "search.shopping.naver.com",
            "koreanairdfs.com", "lottedfs.com", "shilladfs.com",
            "ssgdfs.com", "galleria.co.kr",
            "coupang.com", "gmarket.co.kr", "auction.co.kr",
            "11st.co.kr", "ssg.com",
            "musinsa.com", "29cm.co.kr", "wconcept.co.kr",
        ]
        product_patterns = [
            "/product", "/item", "/goods", "/shop",
            "/store", "/buy", "/order",
        ]
        url_lower = url.lower()
        for domain in product_domains:
            if domain in url_lower:
                return True
        for pattern in product_patterns:
            if pattern in url_lower:
                return True
        return False

    def _save_json(self, site: dict, posts: list[dict]):
        """수집 결과를 JSON 파일로 저장한다."""
        site_name = site["site_name"].replace(" ", "_")
        output_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "output", f"{site['id']}_{site_name}",
        )
        os.makedirs(output_dir, exist_ok=True)

        posts_path = os.path.join(output_dir, "posts.json")
        result_path = os.path.join(output_dir, "crawl_result.json")

        result = {
            "crawl_meta": {
                "site_name": site["site_name"],
                "site_url": site["site_url"],
                "agent_type": "cafe",
                "crawl_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            },
            "posts": posts,
            "total_posts": len(posts),
            "posts_with_products": sum(
                1 for p in posts
                if p.get("prices") or p.get("product_links")
            ),
        }

        for path, data in [
            (posts_path, posts),
            (result_path, result),
        ]:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"[cafe] 파일 저장: {output_dir}")


# ─── 유틸 ────────────────────────────────────────────────────────

def _parse_date_config(value) -> datetime | None:
    """crawl_config의 날짜 문자열을 datetime으로 변환한다.

    지원 형식: 'YYYY-MM-DD', 'YYYY.MM.DD', 'YYYY.MM.DD.'
    None이나 빈 문자열이면 None을 반환한다.
    """
    if not value:
        return None
    s = str(value).strip().rstrip(".")
    for fmt in ("%Y-%m-%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _parse_post_date(date_str: str) -> datetime | None:
    """게시글 날짜 문자열을 datetime으로 변환한다.

    네이버 카페 인기글 목록의 날짜 형식:
      - '2026.05.24.'  (일반 날짜)
      - '05.24.'       (연도 생략 → 올해로 간주)
      - '23:45'        (오늘 작성 → 오늘 날짜)
      - '2시간 전'     (오늘 작성 → 오늘 날짜)
    """
    if not date_str:
        return None
    s = date_str.strip().rstrip(".")

    # YYYY.MM.DD
    match = re.match(r"(\d{4})\.(\d{1,2})\.(\d{1,2})", s)
    if match:
        try:
            return datetime(
                int(match.group(1)),
                int(match.group(2)),
                int(match.group(3)),
            )
        except ValueError:
            return None

    # MM.DD (연도 생략)
    match = re.match(r"(\d{1,2})\.(\d{1,2})$", s)
    if match:
        try:
            return datetime(
                datetime.now().year,
                int(match.group(1)),
                int(match.group(2)),
            )
        except ValueError:
            return None

    # HH:MM 또는 N시간/분 전 → 오늘
    if re.match(r"\d{1,2}:\d{2}", s) or "전" in s:
        now = datetime.now()
        return datetime(now.year, now.month, now.day)

    return None


def _safe_print(text: str) -> str:
    """Windows cp949 콘솔에서 안전하게 출력할 수 있는 문자열로 변환한다."""
    try:
        return text.encode("cp949", errors="replace").decode("cp949")
    except Exception:
        return text


# ─── OCR 텍스트에서 가격-상품명 추출 (Python) ─────────────────────

# 비상품 키워드
_NON_PRODUCT_WORDS = [
    "식대", "회비", "1인당", "인당", "나누기",
    "송금", "입금", "팔로워", "팔로잉", "게시물",
]

# OCR 이전 줄 탐색 시 건너뛸 UI 키워드 (정확 일치)
# Document Parse 결과에서 쇼핑몰 UI 라벨이 상품명으로 잡히는 것을 방지
_OCR_UI_SKIP_WORDS = {
    "세일", "클리어런스", "품절제외", "필터", "위스키",
    "전체", "인기", "추천", "신상품", "베스트",
    "할인", "이벤트", "무료배송", "즉시할인",
}

# 가격 정규식: N,NNN원 또는 N,NNN (콤마 포함)
_PRICE_RE = re.compile(r"(\d{1,3}(?:,\d{3})+)\s*원?")

# 연속 한글 2자 이상 (상품명 판별용)
_HANGUL_CONSECUTIVE_RE = re.compile(r"[가-힣]{2,}")

# 일반적 접두사 제거 패턴
_PREFIX_CLEAN_RE = re.compile(
    r"^(현재\s*(금액)?|그렇게\s*적용하면\s*(가격이)?|무려)\s*"
)


def _extract_prices_from_elements(
    elements: list[dict], title: str = "",
) -> list[dict]:
    """Document Parse 요소 좌표를 활용하여 가격-상품명을 매칭한다.

    2D 레이아웃(카탈로그, 그리드 등)에서 같은 컬럼에 위치한
    상품명과 가격을 x좌표 근접도로 매칭한다.

    매칭 전략:
      1. 요소 중 가격이 포함된 paragraph/heading을 찾는다.
      2. 요소 중 한글 상품명이 포함된 paragraph를 찾는다.
      3. 각 가격 요소에 대해 x좌표가 가장 가까운 상품명을 매칭한다.
         (같은 컬럼 = x좌표 유사 + y좌표가 가격보다 위)

    Args:
        elements: Document Parse 요소 리스트
                  [{"text": str, "category": str, "x": float, "y": float, ...}]
        title: 게시글 제목 (fallback 상품명)

    Returns:
        가격-상품명 쌍 리스트
    """
    results = []
    seen_prices = set()

    # ── 가격 요소 수집 ──
    price_elems = []
    for elem in elements:
        text = elem.get("text", "")
        if not text:
            continue
        # figure(이미지) 요소는 건너뛰기
        if elem.get("category") == "figure":
            continue
        for m in _PRICE_RE.finditer(text):
            price_num_str = m.group(1)
            price_num = int(price_num_str.replace(",", ""))
            if price_num < 1000 or price_num > 100_000_000:
                continue
            if price_num_str in seen_prices:
                continue
            # 비상품 키워드 필터
            if any(w in text for w in _NON_PRODUCT_WORDS):
                continue
            seen_prices.add(price_num_str)
            price_elems.append({
                "price_str": m.group(0).strip(),
                "context": text[:200],
                "x": elem.get("x", 0),
                "y": elem.get("y", 0),
            })

    if not price_elems:
        return results

    # ── 상품명 후보 요소 수집 ──
    # 한글 2자 이상 포함된 paragraph/heading (UI 키워드 제외)
    product_elems = []
    for elem in elements:
        text = elem.get("text", "").strip()
        cat = elem.get("category", "")
        if not text or cat == "figure":
            continue
        if not _HANGUL_CONSECUTIVE_RE.search(text):
            continue
        # UI 키워드 건너뛰기 (각 줄 단위로 체크)
        lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
        product_lines = [
            ln for ln in lines
            if (_HANGUL_CONSECUTIVE_RE.search(ln)
                and ln not in _OCR_UI_SKIP_WORDS)
        ]
        if not product_lines:
            continue

        # 가장 상세한 줄 선택 (가장 긴 한글 포함 줄)
        best = max(product_lines, key=len)
        # 가격/할인율/숫자만 있는 줄 제거
        cleaned = re.sub(r"[\d%$,.\s원]+", "", best).strip()
        if len(cleaned) <= 1:
            continue

        product_elems.append({
            "name": best[:150],
            "x": elem.get("x", 0),
            "y": elem.get("y", 0),
        })

    if not product_elems:
        # 상품명 후보가 없으면 제목을 사용
        for pe in price_elems:
            results.append({
                "product": title[:150] if title else "",
                "price": pe["price_str"],
                "context": pe["context"],
            })
        return results

    # ── x좌표 기반 매칭 ──
    # 각 가격에 대해 x좌표가 가장 가까운 상품명을 선택
    # (단, 상품명이 가격보다 위에 있어야 함 → y좌표 체크)
    for pe in price_elems:
        best_product = ""
        best_dist = float("inf")

        for prod in product_elems:
            # y좌표: 상품명이 가격 위에 있어야 함 (약간의 여유 허용)
            if prod["y"] > pe["y"] + 0.05:
                continue

            # x좌표 거리 (같은 컬럼이면 거의 0)
            x_dist = abs(prod["x"] - pe["x"])

            # y좌표 거리도 고려 (가까울수록 좋음)
            y_dist = abs(prod["y"] - pe["y"])

            # 가중 거리: x를 3배 중요하게 (같은 컬럼 우선)
            dist = x_dist * 3 + y_dist

            if dist < best_dist:
                best_dist = dist
                best_product = prod["name"]

        results.append({
            "product": best_product,
            "price": pe["price_str"],
            "context": pe["context"],
        })

    return results


def _extract_prices_from_text(
    text: str, title: str = "",
) -> list[dict]:
    """텍스트에서 가격-상품명 쌍을 추출한다.

    JS의 가격 추출 로직과 동일한 패턴을 Python으로 구현.
    OCR 텍스트에서 가격 정보를 추출할 때 사용한다.

    이전 줄 참조 로직:
      OCR 결과에서는 상품명과 가격이 다른 줄에 있을 수 있다.
      (예: "발렌타인 30년 700ml" 줄 → "$312.9 470,445원" 줄)
      가격 줄에서 상품명을 못 찾으면 최대 30줄 이전까지
      역순 탐색하여 한글이 2자 이상 포함된 줄을 상품명으로 사용.
      이미지 alt-text, UI 키워드(세일 등), 단위만 있는 줄은 건너뛴다.

    Args:
        text: OCR 등으로 추출된 텍스트
        title: 게시글 제목 (■구입가격 패턴 시 상품명으로 사용)

    Returns:
        가격-상품명 쌍 리스트
    """
    results = []
    seen_prices = set()
    lines = text.split("\n")

    # 한글 포함 여부 판별 패턴 (원, 엔 등 단위만 있는 경우 제외)
    hangul_re = re.compile(r"[가-힣]")
    hangul_unit_only_re = re.compile(r"^[\d%$,.\s원엔달러불]+$")
    # 달러 가격만인 문자열 판별
    dollar_only_re = re.compile(r"^\$[\d.,\s]+$")
    # 연속 한글 2자 이상 (OCR 노이즈 필터 — 영문 속 한글 1자 제외)
    hangul_consecutive_re = re.compile(r"[가-힣]{2,}")

    for li, raw_line in enumerate(lines):
        line = raw_line.strip()
        if not line:
            continue

        for m in _PRICE_RE.finditer(line):
            price_str = m.group(0)
            price_num_str = m.group(1)
            price_num = int(price_num_str.replace(",", ""))
            if price_num < 1000 or price_num > 100_000_000:
                continue

            # 중복 방지
            if price_num_str in seen_prices:
                continue
            seen_prices.add(price_num_str)

            # 비상품 키워드 필터
            if any(w in line for w in _NON_PRODUCT_WORDS):
                continue

            product = ""

            # 패턴1: 슬래시 구분 (상품명/가격/구입처)
            slash_parts = line.split("/")
            if len(slash_parts) >= 2:
                for si, part in enumerate(slash_parts):
                    if price_num_str in part and si > 0:
                        product = re.sub(
                            r"^\d+\.\s*", "", slash_parts[si - 1].strip(),
                        )
                        break

            # 패턴2: 콜론 구분 (상품명 : 가격)
            if not product:
                colon_idx = line.rfind(":")
                if colon_idx > -1 and line.find(price_num_str) > colon_idx:
                    before_colon = re.sub(
                        r"^\d+\.\s*", "", line[:colon_idx].strip(),
                    )
                    if "구입가격" in before_colon or "구입 가격" in before_colon:
                        product = title
                    elif 1 < len(before_colon) < 100:
                        product = before_colon

            # 패턴3: ■구입가격 (콜론 없이)
            if not product:
                if "구입가격" in line or "구입 가격" in line:
                    product = title

            # 패턴4: 가격 앞 텍스트
            if not product:
                before = line[:m.start()].strip().rstrip(" ,.:;/")
                # 달러 가격+숫자만 있는 텍스트는 상품명이 아님
                if 1 < len(before) < 100:
                    before = re.sub(r"^\d+\.\s*", "", before)
                    before = _PREFIX_CLEAN_RE.sub("", before)
                    # 한글이 포함되고, 단위만으로 이루어지지 않은 경우
                    if (len(before) > 1
                            and hangul_re.search(before)
                            and not hangul_unit_only_re.match(before)):
                        product = before

            # 패턴5 (OCR 대응): product가 비어있거나 달러가격만인 경우
            # → 이전 줄들을 역순 탐색하여 한글 포함 줄을 상품명으로
            #
            # Document Parse 텍스트에서는 이미지 alt-text(영문 병 라벨 등)가
            # 상품명과 가격 사이에 수십 줄 삽입될 수 있으므로 탐색 범위를 넓게.
            # 노이즈 방지:
            #   - 연속 한글 2자 이상 필요 (영문 속 한글 1자 제외)
            #   - OCR UI 키워드(세일, 클리어런스 등) 건너뛰기
            #   - ![image] 줄 건너뛰기
            if not product or dollar_only_re.match(product.strip()):
                product = ""
                for prev_i in range(li - 1, max(li - 30, -1), -1):
                    prev = lines[prev_i].strip()
                    if not prev:
                        continue
                    # 이미지 플레이스홀더 건너뛰기
                    if prev.startswith("![image]"):
                        continue
                    # 연속 한글 2자 이상 필요 (OCR 노이즈 제거)
                    if not hangul_consecutive_re.search(prev):
                        continue
                    # OCR UI 라벨 건너뛰기
                    if prev in _OCR_UI_SKIP_WORDS:
                        continue
                    # 가격/할인율/기호만 있는 줄 건너뛰기
                    cleaned = re.sub(
                        r"[\d%$,.\s원]+", "", prev,
                    ).strip()
                    if len(cleaned) > 1:
                        product = prev
                        break

            results.append({
                "product": product[:150],
                "price": price_str.strip(),
                "context": line[:200],
            })

    return results
