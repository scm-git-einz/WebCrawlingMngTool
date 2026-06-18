"""
쿠폰 다운로드 에이전트

이벤트 페이지에서 쿠폰을 다운로드한다.
OrderAgent에서 내부적으로 호출되어 이벤트 쿠폰을 사전 확보한다.
단독 실행도 가능하다.

수집 흐름:
  1. 로그인 (메인 + lps 서브도메인)
  2. 이벤트 페이지 순회 → 쿠폰 다운로드
  3. 쿠키 저장

쿠폰 버튼 탐색 (두 가지 모드):
  A. 수동 등록 모드 (event_coupons):
     사용자가 이벤트 URL + 버튼 텍스트/셀렉터를 개별 등록
  B. 자동 탐색 모드 (event_list_url + coupon_keywords):
     이벤트 목록 페이지에서 하위 이벤트 링크를 자동 수집,
     각 페이지에서 등록된 키워드로 쿠폰 버튼 탐색/클릭

  버튼 매칭:
  - 텍스트: "오늘의 혜택받기" → 해당 텍스트를 포함하는 클릭 가능 요소 탐색
  - CSS 셀렉터: ".btn-coupon" → 직접 셀렉터로 요소 탐색 ('#' 또는 '.' 시작)

쿠폰 설정 미등록 시 해당 단계를 건너뛴다.

OrderAgent 연계:
  OrderAgent.run_site()에서 로그인 후 CouponAgent.run_event_coupons()를 호출하여
  같은 브라우저 세션에서 이벤트 쿠폰을 다운로드한다.
  이때 page 객체를 직접 전달받아 브라우저/로그인 중복 없이 실행한다.

봇 차단 대응:
  BaseAgent 상속 (Stealth 브라우저, 적응형 백오프, 인간형 행동)
"""
import json
import os
import time
from datetime import datetime

from core.base_agent import BaseAgent, DEFAULT_SETTINGS
from core.failure_collector import FailureCollector


# _TAG 제거: BaseAgent._log() 공통 로그 사용

# ─── 쿠폰 버튼 클릭 JS ──────────────────────────────────────────
# selector_text: 사용자가 입력한 텍스트 또는 CSS 셀렉터
# CSS 셀렉터('#' 또는 '.' 시작)이면 직접 탐색, 아니면 텍스트 매칭
JS_CLICK_COUPON = """(selectorText) => {
    function isVisible(el) {
        if (!el) return false;
        if (el.offsetParent === null) return false;
        const r = el.getBoundingClientRect();
        if (r.width <= 0 || r.height <= 0) return false;
        const s = getComputedStyle(el);
        return s.visibility !== 'hidden' && s.display !== 'none';
    }

    const results = [];
    const selectors = selectorText.split('\\n').map(s => s.trim()).filter(Boolean);

    for (const sel of selectors) {
        // CSS 셀렉터 모드 ('#' 또는 '.' 또는 '[' 시작)
        if (/^[#.\\[]/.test(sel)) {
            const els = document.querySelectorAll(sel);
            for (const el of els) {
                if (isVisible(el)) {
                    el.click();
                    results.push({
                        ok: true,
                        method: 'css-selector',
                        selector: sel,
                        text: (el.textContent || '').trim().substring(0, 50),
                    });
                }
            }
            if (results.length === 0) {
                results.push({
                    ok: false,
                    method: 'css-selector',
                    selector: sel,
                    error: 'element not found or not visible',
                });
            }
            continue;
        }

        // 텍스트 매칭 모드
        const keyword = sel.replace(/\\s+/g, '');
        const clickable = [
            ...document.querySelectorAll('button, a, [role="button"], [onclick]')
        ];
        let found = false;
        for (const el of clickable) {
            if (!isVisible(el)) continue;
            const t = (el.textContent || '').replace(/\\s+/g, '');
            if (t.includes(keyword)) {
                el.click();
                results.push({
                    ok: true,
                    method: 'text-match',
                    keyword: sel,
                    text: (el.textContent || '').trim().substring(0, 50),
                });
                found = true;
                break;
            }
        }

        // img alt 매칭 폴백
        if (!found) {
            const imgs = document.querySelectorAll('a > img[alt], button > img[alt]');
            for (const img of imgs) {
                const alt = (img.alt || '').replace(/\\s+/g, '');
                if (alt.includes(keyword)) {
                    const parent = img.closest('a, button');
                    if (parent && isVisible(parent)) {
                        parent.click();
                        results.push({
                            ok: true,
                            method: 'img-alt',
                            keyword: sel,
                            alt: img.alt,
                        });
                        found = true;
                        break;
                    }
                }
            }
        }

        if (!found) {
            results.push({
                ok: false,
                method: 'text-match',
                keyword: sel,
                error: 'matching element not found',
            });
        }
    }
    return results;
}"""


# ─── 이벤트 목록 페이지에서 하위 이벤트 링크 추출 JS ────────────
# #setEvtListDetail 내 a[data-value] 링크에서 evtDispNo를 추출하여
# 이벤트 상세 URL 목록을 반환한다.
JS_EXTRACT_EVENT_LINKS = """() => {
    const links = document.querySelectorAll('#setEvtListDetail a[data-value]');
    const events = [];
    const seen = new Set();
    for (const a of links) {
        const value = a.getAttribute('data-value');
        if (!value || seen.has(value)) continue;
        seen.add(value);
        const title = (a.textContent || '').trim();
        events.push({ evtDispNo: value, title: title });
    }
    return events;
}"""


class CouponAgent(BaseAgent):
    """이벤트 페이지 쿠폰 다운로드 에이전트.

    두 가지 실행 모드:
      1. 단독 실행: run_site(site_id) — 자체 브라우저+로그인+이벤트 쿠폰+결과 저장
      2. OrderAgent 종속: run_event_coupons(page, event_coupons) — 전달받은 page로 이벤트 쿠폰만

    crawl_config 필드:
      - login_url: 메인 로그인 URL
      - lps_login_url: lps 서브도메인 로그인 URL
      - event_coupons: [{ url, selector }] — 이벤트 페이지별 쿠폰 설정 (수동)
      - event_list_url: 이벤트 목록 페이지 URL (자동 탐색용)
      - coupon_keywords: [str] — 쿠폰 버튼 키워드 목록 (자동 탐색용)
      - login_config: 로그인 폼 셀렉터 (자동 탐지 시 비워둠)
    """

    @property
    def agent_type(self) -> str:
        return "coupon"

    def _normalize_config(self, crawl_cfg: dict) -> dict:
        """UI crawl_config -> Agent 내부 config 변환."""
        cfg = dict(crawl_cfg)
        cfg.setdefault("login_url", "")
        if not cfg.get("lps_login_url"):
            cfg["lps_login_url"] = (
                "https://kor.lps.lottedfs.com/kr/member/login"
            )
        cfg.setdefault("event_coupons", [])
        cfg.setdefault("event_list_url", "")
        cfg.setdefault("coupon_keywords", [])
        cfg.setdefault("login_config", {})
        return cfg

    def _click_coupon(self, selector_text: str) -> list:
        """페이지에서 쿠폰 버튼을 찾아 클릭한다.

        Args:
            selector_text: 사용자 입력 텍스트 또는 CSS 셀렉터 (줄바꿈 구분 복수 가능)

        Returns:
            클릭 결과 리스트
        """
        if not selector_text or not selector_text.strip():
            return []
        try:
            results = self.page.evaluate(JS_CLICK_COUPON, selector_text)
            return results if isinstance(results, list) else []
        except Exception as e:
            self._log(f"  쿠폰 클릭 오류: {e}")
            return [{"ok": False, "error": str(e)}]

    # ═══════════════════════════════════════════════════════════════
    # 이벤트 목록 자동 탐색
    # ═══════════════════════════════════════════════════════════════

    def _discover_event_pages(self, event_list_url: str) -> list:
        """이벤트 목록 페이지에서 하위 이벤트 URL을 자동 수집한다.

        Args:
            event_list_url: 이벤트 목록 페이지 URL (예: eventDetail?evtDispNo=1044712)

        Returns:
            [{"url": "...", "title": "..."}, ...] 형태의 이벤트 목록
        """
        self._log(f"\n이벤트 목록 자동 탐색: {event_list_url[:80]}")
        resp = self._safe_goto(event_list_url)
        if self._is_blocked(resp):
            self._log("  이벤트 목록 페이지 차단됨")
            return []

        self.page.wait_for_timeout(DEFAULT_SETTINGS["initial_wait_ms"])
        self._human_dwell()

        try:
            events = self.page.evaluate(JS_EXTRACT_EVENT_LINKS)
            if not isinstance(events, list):
                events = []
        except Exception as e:
            self._log(f"  이벤트 링크 추출 오류: {e}")
            return []

        # evtDispNo → 전체 URL 변환
        from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
        parsed = urlparse(event_list_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

        result = []
        for ev in events:
            evt_no = ev.get("evtDispNo", "")
            title = ev.get("title", "")
            if not evt_no:
                continue
            url = f"{base_url}?evtDispNo={evt_no}"
            result.append({"url": url, "title": title})

        self._log(f"  발견된 이벤트 페이지: {len(result)}건")
        return result

    def run_auto_discovery_coupons(self, page, event_list_url: str,
                                    coupon_keywords: list) -> list:
        """이벤트 목록을 자동 탐색하여 각 페이지에서 쿠폰 키워드로 다운로드한다.

        Args:
            page: 로그인 완료된 Playwright Page 객체
            event_list_url: 이벤트 목록 진입 URL
            coupon_keywords: 쿠폰 버튼 키워드 목록 (줄바꿈 없이 개별 문자열)

        Returns:
            [{"url", "title", "results", "success"}, ...] 형태의 결과 리스트
        """
        self.page = page
        all_results = []

        if not event_list_url or not coupon_keywords:
            self._log("자동 탐색 설정 미입력 (event_list_url 또는 coupon_keywords 없음)")
            return all_results

        # 1. 이벤트 목록 페이지에서 하위 이벤트 URL 수집
        event_pages = self._discover_event_pages(event_list_url)
        if not event_pages:
            self._log("  발견된 이벤트 페이지 없음")
            return all_results

        # 키워드를 줄바꿈 구분 텍스트로 결합 (JS_CLICK_COUPON 형식)
        keywords_text = "\n".join(coupon_keywords)

        self._log(f"\n자동 탐색 쿠폰 다운로드 ({len(event_pages)}건, 키워드 {len(coupon_keywords)}개)")
        for kw in coupon_keywords:
            self._log(f"  키워드: {kw}")

        # 2. 각 이벤트 페이지 방문 → 키워드로 쿠폰 버튼 탐색
        for i, ev in enumerate(event_pages):
            url = ev["url"]
            title = ev.get("title", "")
            self._log(f"\n  [{i+1}/{len(event_pages)}] {title[:40]} — {url[:80]}")

            resp = self._safe_goto(url)
            if self._is_blocked(resp):
                self._log(f"    차단됨")
                all_results.append({
                    "url": url, "title": title,
                    "results": [], "success": 0,
                    "error": "blocked",
                })
                continue

            self.page.wait_for_timeout(DEFAULT_SETTINGS["initial_wait_ms"])
            self._human_dwell()

            results = self._click_coupon(keywords_text)
            success = sum(1 for r in results if r.get("ok"))

            if success > 0:
                self._log(f"    ✓ 쿠폰 {success}건 클릭 성공")
            else:
                self._log(f"    - 쿠폰 버튼 없음")

            for r in results:
                if r.get("ok"):
                    self._log(f"      {r}")

            all_results.append({
                "url": url,
                "title": title,
                "results": results,
                "success": success,
            })

            self._delay()

        total_success = sum(1 for r in all_results if r.get("success", 0) > 0)
        self._log(f"\n자동 탐색 완료: {total_success}/{len(all_results)}건 이벤트에서 쿠폰 발견")
        return all_results

    # ═══════════════════════════════════════════════════════════════
    # OrderAgent에서 호출하는 종속 메서드
    # ═══════════════════════════════════════════════════════════════

    def run_event_coupons(self, page, event_coupons: list) -> list:
        """OrderAgent가 전달한 page로 이벤트 페이지 쿠폰을 다운로드한다.

        이미 로그인된 page를 받아 이벤트 URL만 순회하며 쿠폰을 클릭한다.
        브라우저 시작/로그인/종료는 호출자(OrderAgent)가 관리한다.

        Args:
            page: 로그인 완료된 Playwright Page 객체
            event_coupons: [{"url": "...", "selector": "..."}]

        Returns:
            [{"url", "selector", "results", "success"}, ...] 형태의 결과 리스트
        """
        self.page = page
        all_results = []

        if not event_coupons:
            self._log("이벤트 쿠폰 설정 없음 — 건너뜀")
            return all_results

        self._log(f"\n이벤트 페이지 쿠폰 다운로드 ({len(event_coupons)}건)")

        for i, ec in enumerate(event_coupons):
            url = ec.get("url", "").strip()
            selector = ec.get("selector", "").strip()
            if not url or not selector:
                self._log(f"  [{i+1}] URL 또는 셀렉터 미입력 — 건너뜀")
                continue

            self._log(f"  [{i+1}/{len(event_coupons)}] {url[:80]}")
            resp = self._safe_goto(url)
            if self._is_blocked(resp):
                self._log(f"    차단됨")
                all_results.append({
                    "url": url, "selector": selector,
                    "results": [], "success": 0,
                    "error": "blocked",
                })
                continue

            self.page.wait_for_timeout(DEFAULT_SETTINGS["initial_wait_ms"])
            self._human_dwell()

            results = self._click_coupon(selector)
            success = sum(1 for r in results if r.get("ok"))
            self._log(f"    쿠폰 클릭: {success}/{len(results)}건 성공")
            for r in results:
                self._log(f"      {r}")
            all_results.append({
                "url": url,
                "selector": selector,
                "results": results,
                "success": success,
            })

            self._delay()

        return all_results

    # ═══════════════════════════════════════════════════════════════
    # 단독 실행
    # ═══════════════════════════════════════════════════════════════

    def run_site(self, site_id: int):
        """이벤트 쿠폰 다운로드 단독 실행."""
        site = self.db.get_site(site_id)
        if not site:
            self._log(f"사이트 ID={site_id} 없음")
            return

        raw_cfg = self.get_crawl_config(site)
        cfg = self._normalize_config(raw_cfg)
        site_name = site["site_name"]
        site_url = site["site_url"]

        event_coupons = cfg.get("event_coupons") or []
        event_list_url = cfg.get("event_list_url", "").strip()
        coupon_keywords = cfg.get("coupon_keywords") or []

        has_manual = bool(event_coupons)
        has_auto = bool(event_list_url and coupon_keywords)

        if not has_manual and not has_auto:
            self._log("이벤트 쿠폰 설정이 없습니다. (event_coupons 또는 event_list_url+coupon_keywords)")
            return

        self._log(f"{'='*50}")
        self._log(f"  쿠폰 다운로드: {site_name}")
        if has_manual:
            self._log(f"  수동 이벤트 페이지: {len(event_coupons)}건")
        if has_auto:
            self._log(f"  자동 탐색 URL: {event_list_url[:60]}")
            self._log(f"  쿠폰 키워드: {len(coupon_keywords)}개")
        self._log(f"{'='*50}")

        start_time = time.time()
        result_id = self.db.create_result(site_id)
        self._failure_collector = FailureCollector(site_id, result_id, self.agent_type)

        try:
            # ── 1. 브라우저 시작 ──────────────────────────────────
            raw_domain = self._get_cookie_domain(site_url)
            parts = raw_domain.split(".")
            cookie_domain = ".".join(parts[-2:]) if len(parts) > 2 else raw_domain
            self._log(f"브라우저 시작 (cookie: {cookie_domain}, headless)...")
            self.page = self._create_page(
                cookie_domain=cookie_domain, headless=True,
            )

            # ── 2. 로그인 (메인 + lps) ────────────────────────────
            credential = self._get_next_credential(site_id)
            if not credential:
                self._log("등록된 로그인 계정이 없습니다.")
                self._finish_result(result_id, "error", start_time, "로그인 계정 없음")
                return

            # 메인 로그인
            login_url = cfg.get("login_url") or site_url
            self._log(f"로그인 페이지 이동: {login_url}")
            resp = self._safe_goto(login_url)
            if self._is_blocked(resp):
                self._log(f"로그인 페이지 차단됨 (proxy={self._proxy_ip})")
                self._finish_result(result_id, "blocked", start_time, "로그인 차단")
                return

            self.page.wait_for_timeout(DEFAULT_SETTINGS["initial_wait_ms"])
            has_pwd = self.page.evaluate(
                "() => !!document.querySelector('input[type=\"password\"]')"
            )
            if has_pwd:
                self._log(f"로그인 시도: {credential['login_id']}")
                if not self._do_login(self.page, credential, cfg.get("login_config")):
                    self._log("로그인 실패")
                    self._finish_result(result_id, "error", start_time, "로그인 실패")
                    return
                self._log("로그인 성공")
            else:
                self._log(f"쿠키로 이미 로그인 상태 (-> {self.page.url[:60]})")

            self._human_dwell()
            self._delay()

            # lps 서브도메인 로그인
            lps_login_url = cfg.get("lps_login_url")
            self._log(f"lps 서브도메인 로그인: {lps_login_url}")
            self._safe_goto(lps_login_url)
            self.page.wait_for_timeout(3000)
            lps_has_pwd = self.page.evaluate(
                "() => !!document.querySelector('input[type=\"password\"]')"
            )
            if lps_has_pwd:
                if self._do_login(self.page, credential, cfg.get("login_config")):
                    self._log("lps 로그인 성공")
                else:
                    self._log("[WARN] lps 로그인 실패")
            else:
                self._log("lps 이미 로그인 상태")

            self._human_dwell()
            self._delay()

            # ── 3. 이벤트 페이지 쿠폰 다운로드 ───────────────────
            all_results = []

            # 3a. 수동 등록 이벤트 쿠폰
            if has_manual:
                manual_results = self.run_event_coupons(self.page, event_coupons)
                all_results.extend(manual_results)

            # 3b. 자동 탐색 이벤트 쿠폰
            if has_auto:
                auto_results = self.run_auto_discovery_coupons(
                    self.page, event_list_url, coupon_keywords,
                )
                all_results.extend(auto_results)

            # ── 4. 결과 저장 ──────────────────────────────────────
            event_success = sum(
                1 for r in all_results if r.get("success", 0) > 0
            )
            elapsed = time.time() - start_time

            self._log(f"\n{'='*50}")
            self._log(f"  이벤트 쿠폰: {event_success}/{len(all_results)}건 성공")
            self._log(f"  총 소요시간: {elapsed:.1f}초")

            coupon_data = {
                "event_coupons": all_results,
                "collected_at": datetime.now().isoformat(),
                "credential_used": credential["login_id"],
                "elapsed_seconds": round(elapsed, 1),
            }

            self._save_json(site_id, site_name, coupon_data, filename="coupons.json")
            self._finish_result(result_id, "success", start_time)

        except Exception as e:
            self._log(f"오류 발생: {e}")
            import traceback
            self._log(traceback.format_exc())
            self._record_failure("exception", f"오류 발생: {e}")
            self._finish_result(result_id, "error", start_time, str(e))

        finally:
            if self._failure_collector:
                self._failure_collector.save(self.db)
            self._close_browser()

    def _save_json(self, site_id, site_name, data, filename="coupons.json"):
        """쿠폰 수집 결과를 JSON으로 저장."""
        safe_name = "".join(
            c if c.isalnum() or c in " _-" else "_"
            for c in (site_name or str(site_id))
        ).strip()
        out_dir = os.path.join("output", f"{site_id}_{safe_name}")
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, filename)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        self._log(f"저장: {out_path}")
