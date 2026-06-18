"""
뉴스 기사 수집 에이전트

뉴스 사이트에서 기사 목록을 수집하고,
각 기사의 본문 텍스트를 추출한다.

모드:
  1. 일반 모드: 단일 뉴스 사이트 URL에서 기사 목록 수집
  2. 키워드 검색 모드: 검색 엔진에서 키워드별 뉴스 기사 수집

파이프라인:
  1. 뉴스 사이트/검색 접속
  2. 기사 목록 수집 (키워드별 또는 페이지 전체)
  3. 개별 기사 본문 수집 (선택)

crawl_config 예시:
  {"max_articles": 50}                                → 최대 50개 기사
  {"collect_body": false}                             → 본문 수집 생략
  {"search_keywords": ["해외여행", "환율", "면세"]}   → 키워드별 검색
  {"max_articles_per_keyword": 10}                    → 키워드당 최대 기사
  {"keywords": ["AI", "반도체"]}                      → 수집 후 키워드 필터
"""
import json
import re
import time
from urllib.parse import urlparse, urljoin, quote

from playwright.sync_api import Page

from core.base_agent import BaseAgent, DEFAULT_SETTINGS
from core.failure_collector import FailureCollector
from core.network_interceptor import NetworkInterceptor
from core.strategies import get_strategy


# ─── 뉴스 수집 기본 설정 ─────────────────────────────────────────
DEFAULT_NEWS_SETTINGS = {
    **DEFAULT_SETTINGS,
    "max_articles": 100,
    "max_articles_per_keyword": 20,
    "max_body_length": 5000,
}

# ─── 네이버 뉴스 검색 결과 추출 JS ──────────────────────────────
_JS_NAVER_NEWS_SEARCH_EXTRACT = r"""() => {
    var container = document.querySelector('.list_news')
                 || document.querySelector('.group_news')
                 || document.body;

    var allLinks = container.querySelectorAll('a[href]');
    var articleMap = {};

    for (var i = 0; i < allLinks.length; i++) {
        var a = allLinks[i];
        var href = a.getAttribute('href') || '';
        var text = a.textContent.trim();

        // 비기사 링크 필터
        if (!href || href === '#' || href.indexOf('javascript:') === 0) continue;
        if (href.indexOf('keep.naver.com') > -1) continue;
        if (href.indexOf('media.naver.com/press') > -1) continue;

        // 네이버뉴스 라벨 링크 스킵
        var isNaverLabel = (
            (href.indexOf('n.news.naver.com') > -1 ||
             href.indexOf('mnews') > -1 ||
             href.indexOf('entertain.naver.com') > -1)
            && text.length < 10
        );
        if (isNaverLabel) continue;
        if (text.length < 5) continue;

        // URL 정규화
        var normUrl = href.split('?')[0].split('#')[0];
        if (href.indexOf('naver.com') > -1) normUrl = href;

        if (!articleMap[normUrl]) {
            articleMap[normUrl] = {url: href, texts: [], textLengths: []};
        }
        articleMap[normUrl].texts.push(text.substring(0, 200));
        articleMap[normUrl].textLengths.push(text.length);
    }

    // 제목/요약 분리
    var results = [];
    for (var url in articleMap) {
        var group = articleMap[url];
        var texts = group.texts;

        var title = '';
        var description = '';
        for (var j = 0; j < texts.length; j++) {
            var t = texts[j];
            if (t.length >= 10 && t.length <= 150) {
                if (!title || t.length < title.length) title = t;
            }
            if (t.length > 50) {
                if (!description || t.length > description.length) description = t;
            }
        }
        if (!title) continue;

        results.push({
            title: title,
            description: description !== title ? description : '',
            url: group.url,
        });
    }

    // 언론사 추출
    var pressLinks = container.querySelectorAll('a[href*="media.naver.com/press"]');
    var pressNames = [];
    for (var pi = 0; pi < pressLinks.length; pi++) {
        var ptext = pressLinks[pi].textContent.trim();
        if (ptext.length > 0 && ptext.length < 30) pressNames.push(ptext);
    }

    // 날짜 추출
    var allSpans = container.querySelectorAll('span');
    var dates = [];
    var datePattern = /(\d+분 전|\d+시간 전|\d+일 전|\d{4}\.\d{2}\.\d{2})/;
    for (var di = 0; di < allSpans.length; di++) {
        var dtText = allSpans[di].textContent.trim();
        var match = datePattern.exec(dtText);
        if (match) dates.push(match[1]);
    }

    // 순서 기반 매칭
    var pressIdx = 0;
    var dateIdx = 0;
    for (var ri = 0; ri < results.length; ri++) {
        if (pressIdx < pressNames.length) {
            results[ri].press = pressNames[pressIdx++];
        }
        if (dateIdx < dates.length) {
            results[ri].date = dates[dateIdx++];
        }
    }

    return results;
}"""

# ─── 일반 뉴스 사이트 기사 탐지 JS ──────────────────────────────
_JS_NEWS_ARTICLE_SCAN = r"""() => {
    var links = document.querySelectorAll('a[href]');
    var candidates = [];
    var seenHrefs = {};

    for (var i = 0; i < links.length; i++) {
        var a = links[i];
        var href = a.getAttribute('href') || '';
        if (!href || href === '#' || href === '/') continue;

        var isArticle = /\/(article|news|view|story|post|entry|read)\//.test(href)
            || /\/\d{4,}/.test(href)
            || /[?&](id|articleId|newsId|seq)=\d+/.test(href);
        if (!isArticle) continue;

        var fullHref = href;
        try { fullHref = new URL(href, location.origin).href; } catch(e) {}
        if (seenHrefs[fullHref]) continue;
        seenHrefs[fullHref] = true;

        var title = a.textContent.trim();
        if (title.length < 5 || title.length > 200) continue;

        var parent = a.closest('li, article, div, tr');
        var dateText = '';
        if (parent) {
            var timeEl = parent.querySelector('time, [class*="date"], [class*="time"]');
            if (timeEl) dateText = timeEl.textContent.trim().substring(0, 30);
        }

        candidates.push({
            href: fullHref,
            title: title.substring(0, 200),
            date: dateText,
        });
    }

    return {
        totalFound: candidates.length,
        articles: candidates.slice(0, 50),
    };
}"""

# ─── 기사 본문 추출 JS ──────────────────────────────────────────
_JS_ARTICLE_BODY_EXTRACT = r"""() => {
    var selectors = [
        '#dic_area', '#newsct_article', '#articeBody',
        '#news_body_area', '.news_end',
        'article .content', 'article .body',
        '[class*="article-body"]', '[class*="article_body"]',
        '[class*="article-content"]', '[class*="article_content"]',
        '[class*="news-body"]', '[class*="news_body"]',
        '[class*="news-content"]', '[class*="news_content"]',
        '[id*="article"]', '[id*="content"]',
        'article',
        '.post-content', '.entry-content',
    ];

    for (var i = 0; i < selectors.length; i++) {
        try {
            var el = document.querySelector(selectors[i]);
            if (el) {
                var text = el.innerText.trim();
                if (text.length > 50) {
                    var titleEl = document.querySelector(
                        'h1, h2.media_end_head_headline,'
                        + ' [class*="title"], [class*="headline"]'
                    );
                    var title = titleEl ? titleEl.innerText.trim() : '';

                    var dateEl = document.querySelector(
                        'time, .media_end_head_info_datestamp_time,'
                        + ' [class*="date"], [class*="published"]'
                    );
                    var date = dateEl ? dateEl.textContent.trim() : '';

                    var authorEl = document.querySelector(
                        '.media_end_head_journalist_name,'
                        + ' [class*="author"], [class*="writer"],'
                        + ' [class*="reporter"], [class*="byline"]'
                    );
                    var author = authorEl ? authorEl.textContent.trim() : '';

                    return {
                        title: title.substring(0, 300),
                        body: text.substring(0, 10000),
                        date: date.substring(0, 50),
                        author: author.substring(0, 100),
                        selector: selectors[i],
                    };
                }
            }
        } catch(e) {}
    }

    var paragraphs = document.querySelectorAll('p');
    var bodyParts = [];
    for (var j = 0; j < paragraphs.length; j++) {
        var pText = paragraphs[j].innerText.trim();
        if (pText.length > 20) bodyParts.push(pText);
    }
    if (bodyParts.length >= 2) {
        return {
            title: (document.querySelector('h1') || {}).innerText || '',
            body: bodyParts.join('\n\n').substring(0, 10000),
            date: '',
            author: '',
            selector: 'p (fallback)',
        };
    }

    return null;
}"""

# ─── 네이버 뉴스 검색 URL 패턴 ──────────────────────────────────
_NAVER_NEWS_SEARCH_URL = (
    "https://search.naver.com/search.naver"
    "?where=news&query={keyword}&sort=1&sm=tab_smr"
)


class NewsAgent(BaseAgent):
    """뉴스 기사 수집 에이전트"""

    @property
    def agent_type(self) -> str:
        return "news"

    # ═══════════════════════════════════════════════════════════════
    # UI config → Agent 내부 config 변환
    # ═══════════════════════════════════════════════════════════════

    def _normalize_config(self, crawl_cfg: dict) -> dict:
        """UI 설정 필드를 Agent 내부 필드로 정규화한다.

        UI 필드와 Agent 필드는 대부분 동일하지만,
        기본값 적용 및 타입 보정을 수행한다.

        UI 필드 → Agent 필드:
          max_articles_per_keyword → max_articles_per_keyword (동일)
          collect_body             → collect_body (동일)
          (DB news_keywords)       → Agent가 직접 조회
        """
        cfg = dict(crawl_cfg)

        # 기본값 적용
        cfg.setdefault(
            "max_articles_per_keyword",
            DEFAULT_NEWS_SETTINGS["max_articles_per_keyword"],
        )
        cfg.setdefault(
            "max_articles",
            DEFAULT_NEWS_SETTINGS["max_articles"],
        )
        cfg.setdefault("collect_body", True)

        # 타입 보정
        for key in ("max_articles_per_keyword", "max_articles"):
            if key in cfg:
                try:
                    cfg[key] = int(cfg[key])
                except (ValueError, TypeError):
                    cfg[key] = DEFAULT_NEWS_SETTINGS.get(key, 20)

        return cfg

    # ═══════════════════════════════════════════════════════════════
    # 메인 실행
    # ═══════════════════════════════════════════════════════════════

    def run_site(self, site_id: int, override_keywords: list[str] | None = None):
        """
        특정 뉴스 사이트에서 기사를 수집한다.

        키워드 우선순위:
          1. override_keywords (CLI --keywords 로 전달)
          2. DB news_keywords 테이블의 활성 키워드
          3. crawl_config.search_keywords (하위 호환)
        """
        site = self.db.get_site(site_id)
        if not site:
            self._log(f"사이트 ID={site_id} 를 찾을 수 없습니다")
            return

        result_id = self.db.create_result(site_id)
        start_time = time.time()
        raw_cfg = self.get_crawl_config(site)
        crawl_cfg = self._normalize_config(raw_cfg)
        self._failure_collector = FailureCollector(site_id, result_id, self.agent_type)

        try:
            # 쿠키 영속화
            cookie_domain = self._get_cookie_domain(site["site_url"])
            self.page = self._create_page(cookie_domain=cookie_domain)

            # 키워드 결정 (우선순위 적용)
            search_keywords = self._resolve_keywords(
                site_id, crawl_cfg, override_keywords,
            )
            is_naver_search = "search.naver.com" in site["site_url"]

            if search_keywords or is_naver_search:
                articles = self._run_keyword_search(
                    site, crawl_cfg, search_keywords,
                )
            else:
                articles = self._run_single_page(site, crawl_cfg)

            # 결과 저장
            elapsed = time.time() - start_time
            self.db.update_result(
                result_id,
                status="success",
                store_info={"site_name": site["site_name"]},
                products=articles,
                product_count=len(articles),
                elapsed_sec=elapsed,
            )

            self._save_json(site, articles)

            self._log(f"수집 완료: {site['site_name']}")
            self._log(f"  기사 수: {len(articles)}")
            self._log(f"  소요 시간: {elapsed:.1f}초")

        except Exception as e:
            elapsed = time.time() - start_time
            self.db.update_result(
                result_id,
                status="failed",
                error_msg=str(e),
                elapsed_sec=elapsed,
            )
            self._record_failure("exception", f"수집 실패: {e}")
            self._log(f"수집 실패: {e}")

        finally:
            if self._failure_collector:
                self._failure_collector.save(self.db)
            self.browser_mgr.close()
            self.page = None

    # ═══════════════════════════════════════════════════════════════
    # 키워드 결정 (우선순위)
    # ═══════════════════════════════════════════════════════════════

    def _resolve_keywords(
        self,
        site_id: int,
        crawl_cfg: dict,
        override_keywords: list[str] | None = None,
    ) -> list[str]:
        """
        수집에 사용할 키워드를 결정한다.

        우선순위:
          1. override_keywords  (CLI --keywords)
          2. DB news_keywords   (활성 키워드)
          3. crawl_config       (search_keywords, 하위 호환)

        최초 실행 시 crawl_config → DB 자동 마이그레이션 수행.
        """
        # 1순위: CLI override
        if override_keywords:
            self._log(f"키워드 소스: CLI override ({len(override_keywords)}개)")
            return override_keywords

        # 2순위: DB 활성 키워드
        # (최초 실행 시 crawl_config 에서 자동 마이그레이션)
        migrated = self.db.migrate_keywords_from_config(site_id)
        if migrated > 0:
            self._log(f"crawl_config → DB 키워드 마이그레이션: {migrated}개")

        db_keywords = self.db.get_active_keywords(site_id)
        if db_keywords:
            self._log(f"키워드 소스: DB ({len(db_keywords)}개)")
            return db_keywords

        # 3순위: crawl_config fallback
        config_keywords = crawl_cfg.get("search_keywords", [])
        if config_keywords:
            self._log(f"키워드 소스: crawl_config ({len(config_keywords)}개)")
        return config_keywords

    # ═══════════════════════════════════════════════════════════════
    # 키워드 검색 모드
    # ═══════════════════════════════════════════════════════════════

    def _run_keyword_search(
        self, site: dict, crawl_cfg: dict,
        search_keywords: list[str],
    ) -> list[dict]:
        """키워드별로 뉴스 검색 결과를 수집한다."""
        self._log("── 키워드 검색 모드 ──")

        max_per_kw = crawl_cfg.get(
            "max_articles_per_keyword",
            DEFAULT_NEWS_SETTINGS["max_articles_per_keyword"],
        )
        max_total = crawl_cfg.get(
            "max_articles",
            DEFAULT_NEWS_SETTINGS["max_articles"],
        )

        # 검색 URL 패턴 (crawl_config에서 커스터마이즈 가능)
        search_url_pattern = crawl_cfg.get(
            "search_url_pattern",
            _NAVER_NEWS_SEARCH_URL,
        )

        all_articles = []
        seen_urls = set()
        display_order = 0

        for kw_idx, keyword in enumerate(search_keywords, 1):
            safe_kw = _safe_print(keyword)
            self._log(f"[{kw_idx}/{len(search_keywords)}] "
                  f"키워드: '{safe_kw}'")

            # 검색 URL 생성
            search_url = search_url_pattern.replace(
                "{keyword}", quote(keyword),
            )

            resp = self._safe_goto(
                search_url, wait_until="domcontentloaded",
            )
            if self._is_blocked(resp):
                self._log(f"  검색 차단됨 → 스킵")
                self._delay()
                continue

            # 인간형 체류 + 스크롤
            self._human_dwell()
            self._human_scroll()

            # 네이버 뉴스 검색 결과 추출
            try:
                raw_articles = self.page.evaluate(
                    _JS_NAVER_NEWS_SEARCH_EXTRACT,
                )
            except Exception as e:
                self._log(f"  추출 실패: {e}")
                self._delay()
                continue

            kw_count = 0
            for art in raw_articles:
                if kw_count >= max_per_kw:
                    break
                if len(all_articles) >= max_total:
                    break

                url = art.get("url", "")
                # URL 정규화 후 중복 체크
                norm_url = url.split("?")[0].split("#")[0]
                if norm_url in seen_urls:
                    continue
                seen_urls.add(norm_url)

                display_order += 1
                all_articles.append({
                    "article_id": display_order,
                    "title": art.get("title", ""),
                    "url": url,
                    "press": art.get("press", ""),
                    "date": art.get("date", ""),
                    "description": art.get("description", ""),
                    "search_keyword": keyword,
                    "display_order": display_order,
                })
                kw_count += 1

            self._log(f"  {kw_count}개 기사 수집 "
                  f"(총 {len(all_articles)}개)")

            if len(all_articles) >= max_total:
                self._log(f"max_articles={max_total} 도달 → 중단")
                break

            # 키워드 간 인간형 딜레이
            if kw_idx < len(search_keywords):
                self._delay()

        # 기사 본문 수집 (선택)
        if crawl_cfg.get("collect_body", True) and all_articles:
            all_articles = self._collect_article_bodies(
                site, all_articles, crawl_cfg,
            )

        # 수집 후 키워드 필터 (추가 필터)
        post_keywords = crawl_cfg.get("keywords", [])
        if post_keywords:
            all_articles = self._filter_by_keywords(
                all_articles, post_keywords,
            )
            self._log(f"키워드 필터 적용 후: {len(all_articles)}개")

        return all_articles

    # ═══════════════════════════════════════════════════════════════
    # 단일 페이지 모드
    # ═══════════════════════════════════════════════════════════════

    def _run_single_page(
        self, site: dict, crawl_cfg: dict,
    ) -> list[dict]:
        """단일 뉴스 사이트 페이지에서 기사를 수집한다."""
        self._log(f"사이트 접속: {site['site_url']}")
        resp = self._safe_goto(
            site["site_url"], wait_until="domcontentloaded",
        )
        if self._is_blocked(resp):
            raise RuntimeError(
                f"사이트 접근 차단됨 (HTTP {resp.status})"
            )

        self._human_dwell()
        self._human_scroll()

        articles = self._collect_article_list(site, crawl_cfg)

        # 키워드 필터
        keywords = crawl_cfg.get("keywords", [])
        if keywords:
            articles = self._filter_by_keywords(articles, keywords)
            self._log(f"키워드 필터 적용 후: {len(articles)}개")

        # 본문 수집
        if crawl_cfg.get("collect_body", True) and articles:
            articles = self._collect_article_bodies(
                site, articles, crawl_cfg,
            )

        return articles

    # ═══════════════════════════════════════════════════════════════
    # 기사 목록 수집 (단일 페이지)
    # ═══════════════════════════════════════════════════════════════

    def _collect_article_list(
        self, site: dict, crawl_cfg: dict,
    ) -> list[dict]:
        """현재 페이지에서 기사 목록을 추출한다."""
        self._log("── 기사 목록 수집 ──")

        max_articles = crawl_cfg.get(
            "max_articles",
            DEFAULT_NEWS_SETTINGS["max_articles"],
        )

        # 기존 템플릿이 있으면 사용
        if site.get("platform_id"):
            platform = self.db.get_platform(site["platform_id"])
            if platform:
                templates = self.db.get_templates_for_platform(
                    platform["id"],
                )
                article_tmpl = None
                for t in templates:
                    if t["target"] == "article_list":
                        article_tmpl = t
                        break

                if article_tmpl:
                    self._log("기존 article_list 템플릿 사용")
                    strategy = get_strategy(article_tmpl["strategy"])
                    raw = strategy.extract(
                        self.page, article_tmpl["config"],
                    )
                    items = self._extract_items(raw)
                    if items:
                        return items[:max_articles]

        # 자동 분석: DOM에서 기사 링크 탐지
        self._log("DOM 자동 분석으로 기사 탐지")
        try:
            scan_result = self.page.evaluate(_JS_NEWS_ARTICLE_SCAN)
        except Exception as e:
            self._log(f"DOM 스캔 실패: {e}")
            return []

        total = scan_result.get("totalFound", 0)
        raw_articles = scan_result.get("articles", [])
        self._log(f"{total}개 기사 링크 탐지됨")

        articles = []
        for i, item in enumerate(raw_articles[:max_articles]):
            articles.append({
                "article_id": i + 1,
                "title": item.get("title", ""),
                "url": item.get("href", ""),
                "date": item.get("date", ""),
                "display_order": i + 1,
            })

        return articles

    # ═══════════════════════════════════════════════════════════════
    # 기사 본문 수집
    # ═══════════════════════════════════════════════════════════════

    def _collect_article_bodies(
        self, site: dict, articles: list[dict],
        crawl_cfg: dict,
    ) -> list[dict]:
        """각 기사 페이지에 접속하여 본문을 수집한다."""
        max_body_articles = crawl_cfg.get(
            "max_body_articles", len(articles),
        )
        targets = articles[:max_body_articles]
        self._log(f"── 기사 본문 수집 ({len(targets)}개) ──")

        max_body_len = DEFAULT_NEWS_SETTINGS["max_body_length"]

        for i, article in enumerate(targets, 1):
            url = article.get("url", "")
            if not url:
                continue

            # 상대 URL → 절대 URL 변환
            if url.startswith("/"):
                parsed = urlparse(site["site_url"])
                url = f"{parsed.scheme}://{parsed.hostname}{url}"

            title_preview = article.get("title", "N/A")[:40]
            safe_title = _safe_print(title_preview)
            self._log(f"[{i}/{len(targets)}] {safe_title}...")

            try:
                resp = self._safe_goto(url)
                if self._is_blocked(resp):
                    self._log("  차단됨 → 스킵")
                    continue

                # 인간형 체류
                self._human_dwell()

                # 본문 추출
                detail = self.page.evaluate(_JS_ARTICLE_BODY_EXTRACT)
                if detail:
                    body = detail.get("body", "")
                    if body:
                        article["body"] = body[:max_body_len]
                    if detail.get("author"):
                        article["author"] = detail["author"]
                    detail_title = detail.get("title", "")
                    if detail_title and len(detail_title) > len(
                        article.get("title", "")
                    ):
                        article["title"] = detail_title
                    if detail.get("date") and not article.get("date"):
                        article["date"] = detail["date"]
                else:
                    self._log("  본문 추출 실패")

            except Exception as e:
                self._log(f"  오류: {e}")

            if i < len(targets):
                self._delay()

        body_count = sum(1 for a in targets if a.get("body"))
        self._log(f"본문 수집 완료: "
              f"{body_count}/{len(targets)}개 성공")
        return articles

    # ═══════════════════════════════════════════════════════════════
    # 키워드 필터
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    def _filter_by_keywords(
        articles: list[dict], keywords: list[str],
    ) -> list[dict]:
        """기사 제목/본문에서 키워드가 포함된 것만 필터링한다."""
        filtered = []
        for article in articles:
            text = (
                article.get("title", "")
                + " "
                + article.get("description", "")
                + " "
                + article.get("body", "")
            ).lower()
            for kw in keywords:
                if kw.lower() in text:
                    article["matched_keyword"] = kw
                    filtered.append(article)
                    break
        return filtered

    # ═══════════════════════════════════════════════════════════════
    # 유틸리티
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    def _extract_items(raw) -> list[dict]:
        """추출 결과에서 아이템 리스트를 꺼낸다."""
        if raw is None:
            return []
        if isinstance(raw, list):
            return raw
        if isinstance(raw, dict):
            return raw.get("items", raw.get("articles", []))
        return []

    def _save_json(self, site: dict, articles: list[dict]):
        """수집 결과를 JSON 파일로 저장한다."""
        import os
        from datetime import datetime

        site_name = site["site_name"].replace(" ", "_")
        output_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "output", f"{site['id']}_{site_name}",
        )
        os.makedirs(output_dir, exist_ok=True)

        articles_path = os.path.join(output_dir, "articles.json")
        result_path = os.path.join(output_dir, "crawl_result.json")

        result = {
            "crawl_meta": {
                "site_name": site["site_name"],
                "site_url": site["site_url"],
                "agent_type": "news",
                "crawl_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            },
            "articles": articles,
            "total_articles": len(articles),
        }

        for path, data in [
            (articles_path, articles),
            (result_path, result),
        ]:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

        self._log(f"파일 저장: {output_dir}")


# ─── 유틸 ────────────────────────────────────────────────────────

def _safe_print(text: str) -> str:
    """Windows cp949 콘솔에서 안전하게 출력할 수 있는 문자열로 변환한다."""
    try:
        return text.encode("cp949", errors="replace").decode("cp949")
    except Exception:
        return text
