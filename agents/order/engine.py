"""
주문서 결제정보 수집 에이전트

상품 코드별로 상품상세 페이지 → 구매/주문 버튼 클릭 → 주문서 페이지 이동
을 반복하여 상품별 최종결제금액을 수집한다.

수집 필드 (상품 1건 기준):
  - product_code  : 상품코드 (입력값)
  - product_name  : 상품명 (주문서)
  - payment_usd   : 최종결제금액 (달러)
  - payment_krw   : 최종결제금액 (원화)
  - discount_rate : 할인율 (예: "50%")

파이프라인:
  1. 브라우저 시작 (Headless Stealth + 쿠키 로드)
  2. 메인 도메인 로그인 + lps 서브도메인 사전 로그인 (2단계)
  3. 상품 코드 목록(product_codes) 순회:
     a. 상품상세 URL 이동 (product_detail_url_template + prdNo)
     b. 구매하기/주문하기 버튼 클릭 → 주문서 페이지 이동
     c. 주문서에서 상품명 + 최종결제금액(USD/KRW/할인율) 추출
  4. 전체 결과 JSON 저장

봇 차단 대응:
  - BaseAgent 상속 (Stealth 브라우저, 적응형 백오프, 인간형 행동)
  - _safe_goto → _is_blocked → _human_dwell → _human_scroll 패턴 준수
  - 페이지 이동 간 _delay() 적용

대상: 롯데면세점 등 로그인 기반 면세점 주문 페이지

도메인 구조 (롯데면세점):
  - kor.lottedfs.com      → 메인 사이트 (로그인, 상품상세)
  - kor.lps.lottedfs.com  → 주문서 (별도 세션 체계, 사전 로그인 필요)
"""
import json
import os
import time
from datetime import datetime

from core.base_agent import BaseAgent, DEFAULT_SETTINGS


_TAG = "[order]"

# ─── 바로구매 팝업 내부의 최종 "주문" 버튼 클릭 ────────────────
# cartPopup('cartForm', '2') 호출 시 모달이 열리고, 그 안에서 수량/옵션 확인 후
# "주문하기" / "구매하기" / "확인" 등의 최종 버튼을 한 번 더 눌러야 newOrder로 이동.
_JS_CLICK_POPUP_CONFIRM = """() => {
    function isVisible(el) {
        if (!el) return false;
        if (el.offsetParent === null) return false;
        const r = el.getBoundingClientRect();
        if (r.width <= 0 || r.height <= 0) return false;
        const s = getComputedStyle(el);
        return s.visibility !== 'hidden' && s.display !== 'none';
    }

    // 팝업/모달 컨테이너 후보 (보이는 것만)
    const popupSelectors = [
        '.popup_wrap', '.popupWrap', '.layer_popup', '.layerPopup',
        '.modal', '.modal_wrap', '.modalWrap', '.dim_popup',
        '[class*="popup"]', '[class*="modal"]', '[class*="layer"]',
        '[role="dialog"]',
    ];
    let popup = null;
    for (const sel of popupSelectors) {
        const candidates = [...document.querySelectorAll(sel)];
        const visible = candidates.find(isVisible);
        if (visible) { popup = visible; break; }
    }
    if (!popup) return { ok: false, error: 'popup not visible' };

    // 팝업 내부에서 주문/구매/확인 버튼 탐색
    const btns = [...popup.querySelectorAll(
        'button, a, a[role="button"], input[type="button"], input[type="submit"]'
    )];
    const confirm = btns.find(b => {
        if (!isVisible(b)) return false;
        const t = (b.textContent || b.value || '').replace(/\\s+/g, '').trim();
        // 취소/닫기/장바구니는 제외
        if (/취소|닫기|장바구니|계속쇼핑|cancel|close/i.test(t)) return false;
        return /^(주문하기|주문|구매하기|구매|결제하기|결제|바로구매|확인|OK)$/i.test(t);
    });
    if (!confirm) {
        // 팝업 내부 버튼 텍스트 디버그
        const labels = btns
            .filter(isVisible)
            .map(b => (b.textContent || b.value || '').replace(/\\s+/g, ' ').trim())
            .filter(t => t.length > 0 && t.length < 30);
        return { ok: false, error: 'popup confirm not found', popup_buttons: labels };
    }
    const text = (confirm.textContent || confirm.value || '').replace(/\\s+/g, ' ').trim();
    confirm.click();
    return { ok: true, text };
}"""

# ─── 주문하기 버튼 클릭 ──────────────────────────────────────
# 롯데면세점 상품상세 "바로 구매" 버튼:
#   <a href="javascript:cartPopup('cartForm', '2');"
#      class="btn_type4 col1 gaEvtTg"
#      data-gaevtaction="바로구매" data-gaevtlabel="바로구매">바로 구매</a>
# → 2번째 파라미터 '2'가 바로구매 모드 (cartPopup(form, mode))
_JS_CLICK_ORDER_BUTTON = """() => {
    function isVisible(el) {
        if (!el) return false;
        if (el.offsetParent === null) return false;
        const r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0;
    }
    function clickAndReport(el, method, extra) {
        const text = (el.textContent || '').replace(/\\s+/g, ' ').trim();
        el.click();
        return { ok: true, method, text, ...(extra || {}) };
    }

    // ── 1) GA 데이터 속성 우선 (가장 정확) ──
    const gaSelectors = [
        'a[data-gaevtaction="바로구매"]',
        'a[data-gaevtlabel="바로구매"]',
        'button[data-gaevtaction="바로구매"]',
    ];
    for (const sel of gaSelectors) {
        const el = document.querySelector(sel);
        if (isVisible(el)) return clickAndReport(el, 'ga-attr', { selector: sel });
    }

    // ── 2) cartPopup(..., '2') href (바로구매 모드) ──
    const popupBtns = [...document.querySelectorAll('a[href*="cartPopup"]')];
    const buyNow = popupBtns.find(a => {
        const h = a.getAttribute('href') || '';
        return /cartPopup\\([^)]*,\\s*['"]2['"]/.test(h) && isVisible(a);
    });
    if (buyNow) return clickAndReport(buyNow, 'cartPopup-href');

    // ── 3) 이미지 alt 매칭 (img 기반 바로구매 버튼) ──
    const buyImgs = [...document.querySelectorAll(
        'a > img[alt], button > img[alt]'
    )];
    const imgBtn = buyImgs.find(img => {
        const alt = (img.alt || '').replace(/\\s+/g, '').trim();
        if (!/바로구매|주문하기|구매하기|ORDER/i.test(alt)) return false;
        const parent = img.closest('a, button');
        return parent && isVisible(parent);
    });
    if (imgBtn) {
        const parent = imgBtn.closest('a, button');
        return clickAndReport(parent, 'img-alt', { alt: imgBtn.alt });
    }

    // ── 4) 텍스트 매칭 ("바로 구매" 공백 포함 / "바로구매" 모두 허용) ──
    const allBtns = [...document.querySelectorAll(
        'button, a, a[role="button"], input[type="button"]'
    )];
    const textBtn = allBtns.find(b => {
        if (!isVisible(b)) return false;
        const t = (b.textContent || '').replace(/\\s+/g, '').trim();
        return /^(바로구매|주문하기|주문|구매하기|결제하기|ORDER)$/i.test(t);
    });
    if (textBtn) return clickAndReport(textBtn, 'text');

    // ── 5) 클래스 기반 폴백 ──
    const candidates = [
        '[class*="btn_buy_now"], [class*="btnBuyNow"]',
        'button[class*="order"], a[class*="order"]',
        'button[class*="buy"], a[class*="buy"]',
        '[class*="btn_order"], [class*="btnOrder"]',
        '[class*="btn_buy"], [class*="btnBuy"]',
    ];
    for (const sel of candidates) {
        const el = document.querySelector(sel);
        if (isVisible(el)) {
            const t = (el.textContent || '').trim();
            if (t && !/삭제|취소|닫기|장바구니/.test(t)) {
                return clickAndReport(el, 'class-selector', { selector: sel });
            }
        }
    }
    return { ok: false, error: 'order button not found' };
}"""

# ─── 주문서 결제정보 추출 ──────────────────────────────────────
# 수집 필드 (4건):
#   - product_name : 상품명
#   - payment_usd  : 최종 결제금액 (달러)
#   - payment_krw  : 최종 결제금액 (원화)
#   - discount_rate: 할인율 (예: "50%")
# (상품코드는 호출 측에서 전달한 prd_no를 사용)
_JS_EXTRACT_ORDER_PAYMENT = """() => {
    const result = {
        product_name: '',
        payment_usd: '',
        payment_krw: '',
        discount_rate: '',
    };
    const raw_texts = [];

    const FINAL_LABELS = [
        '최종결제금액', '총 결제금액', '결제금액', '결제 금액',
        '총합계', '합계금액', '합계 금액', '총 합계',
    ];

    function matchFinal(text) {
        const clean = (text || '').replace(/\\s+/g, ' ').trim();
        return FINAL_LABELS.some(l => clean.includes(l));
    }
    function pickUsd(text) {
        const m = (text || '').match(/-?\\$[\\d,.]+/);
        return m ? m[0] : '';
    }
    function pickKrw(text) {
        const m = (text || '').match(/\\(?(-?[\\d,]+)원\\)?/);
        return m ? m[1] + '원' : '';
    }
    function pickRate(text) {
        const m = (text || '').match(/(\\d+)\\s*%/);
        return m ? m[0].replace(/\\s+/g, '') : '';
    }
    function setIfEmpty(key, val) {
        if (val && !result[key]) result[key] = val;
    }

    // ═══════════════════════════════════════════════════════
    // 1) 면세점 신주문서 — dl.expected_payment
    //    <dl class="expected_payment">
    //      <dt>결제금액</dt>
    //      <dd class="price">
    //        <p><span>50%</span><strong>$251.49</strong></p>
    //        (380,076원)
    //      </dd>
    //    </dl>
    // ═══════════════════════════════════════════════════════
    const expectedDl = document.querySelector(
        'dl.expected_payment, dl[class*="expected"], dl[class*="payment_total"]'
    );
    if (expectedDl) {
        const dd = expectedDl.querySelector('dd');
        if (dd) {
            const rateEl = dd.querySelector('p > span, span[class*="rate"], span[class*="percent"]');
            if (rateEl) setIfEmpty('discount_rate', pickRate(rateEl.textContent));
            const usdEl = dd.querySelector('strong, p > strong');
            if (usdEl) setIfEmpty('payment_usd', pickUsd(usdEl.textContent));
            setIfEmpty('payment_krw', pickKrw(dd.textContent));
        }
    }

    // ═══════════════════════════════════════════════════════
    // 2) dl/dt-dd 라벨 매칭 (결제금액 라벨만)
    // ═══════════════════════════════════════════════════════
    document.querySelectorAll('dl').forEach(dl => {
        const dts = dl.querySelectorAll('dt');
        const dds = dl.querySelectorAll('dd');
        dts.forEach((dt, i) => {
            if (!matchFinal(dt.textContent) || !dds[i]) return;
            const ddText = dds[i].textContent || '';
            setIfEmpty('payment_usd', pickUsd(ddText));
            setIfEmpty('payment_krw', pickKrw(ddText));
            setIfEmpty('discount_rate', pickRate(ddText));
        });
    });

    // ═══════════════════════════════════════════════════════
    // 3) .tit + .price 페어 (롯데 신주문서 .totalPayment)
    //    <li><div class="tit">결제금액</div>
    //        <div class="price"><strong>$251.49</strong><span>(380,076원)</span></div>
    //    </li>
    // ═══════════════════════════════════════════════════════
    const payScope = document.querySelector(
        '.totalPayment, [class*="totalPayment"], [class*="payment_info"]'
    ) || document;
    function cleanTit(el) {
        const c = el.cloneNode(true);
        c.querySelectorAll(
            '.tooltipWrap, .ux_arrow, .btnTip, .contTip, .btnClose, i, em, script'
        ).forEach(n => n.remove());
        return c.textContent.trim().replace(/\\s+/g, ' ');
    }
    payScope.querySelectorAll('.tit').forEach(titEl => {
        if (!matchFinal(cleanTit(titEl))) return;
        let priceEl = titEl.nextElementSibling;
        if (!priceEl || !priceEl.classList || !priceEl.classList.contains('price')) {
            const parent = titEl.parentElement;
            if (parent) priceEl = parent.querySelector(':scope > .price');
        }
        if (!priceEl) return;
        const priceText = priceEl.textContent.replace(/\\s+/g, ' ').trim();
        setIfEmpty('payment_usd', pickUsd(priceText));
        setIfEmpty('payment_krw', pickKrw(priceText));
        setIfEmpty('discount_rate', pickRate(priceText));
    });

    // ═══════════════════════════════════════════════════════
    // 4) 상품명 — 롯데면세점 주문서 구조
    //    <div class="info">
    //      <a href="javascript:void(0)">
    //        <div class="brand"><strong>다이슨</strong> DYSON</div>
    //        <div class="product">다이슨 에어랩 i.d.™ ...</div>
    //      </a>
    //    </div>
    // ═══════════════════════════════════════════════════════
    const nameCandidates = [
        '.info > a > .product', '.info .product',  // 롯데면세점 신주문서
        '[class*="prd_name"]', '[class*="prdName"]',
        '[class*="goods_name"]', '[class*="productName"]',
        '[class*="item_name"]',
        '.order_prd_list .name', '.order_prd_list .tit',
    ];
    for (const sel of nameCandidates) {
        const el = document.querySelector(sel);
        if (!el) continue;
        const txt = el.textContent.replace(/\\s+/g, ' ').trim();
        if (txt) {
            result.product_name = txt.substring(0, 200);
            break;
        }
    }

    // ═══════════════════════════════════════════════════════
    // 디버그용 raw text (결제정보 누락 시 로그)
    // ═══════════════════════════════════════════════════════
    if (!result.payment_usd && !result.payment_krw) {
        const payAreas = document.querySelectorAll(
            '[class*="pay"], [class*="settle"], [class*="expected"], ' +
            '[class*="total"], [class*="summary"]'
        );
        payAreas.forEach(area => {
            const text = area.textContent.replace(/\\s+/g, ' ').trim().substring(0, 300);
            if (text.length > 10) raw_texts.push(text);
        });
    }

    return { ...result, raw_texts };
}"""


class OrderAgent(BaseAgent):
    """주문서 결제정보 수집 에이전트 — 장바구니 상품별 개별 주문서 확인

    ProductAgent와 동일한 봇 차단 우회 패턴 적용:
      - BrowserManager (Stealth Chromium + 쿠키 영속화)
      - _safe_goto() 적응형 백오프 (429/503 대응)
      - _human_dwell() + _human_scroll() 인간형 행동
      - _delay() 페이지 간 가변 딜레이
    """

    @property
    def agent_type(self) -> str:
        return "order"

    def _normalize_config(self, crawl_cfg: dict) -> dict:
        """UI crawl_config → Agent 내부 config 변환.

        Fields:
          - login_url: 로그인 페이지 URL
          - product_codes: list[str] — 수집 대상 상품 코드 목록 (멀티 등록)
          - product_detail_url_template: '{prdNo}' 플레이스홀더 포함 URL
          - order_url: 주문서 URL (구매 클릭 후 도달할 URL 패턴)
          - login_config: 로그인 폼 셀렉터 (자동 탐지 시 비워둠)
        """
        cfg = dict(crawl_cfg)
        cfg.setdefault("login_url", "")
        cfg.setdefault("product_codes", [])
        # 빈 문자열이면 기본값으로 대체 (DB에서 빈 값이 올 수 있음)
        if not cfg.get("product_detail_url_template"):
            cfg["product_detail_url_template"] = (
                "https://kor.lottedfs.com/kr/product/productDetail"
                "?prdNo={prdNo}&adltPrdYn=Y&onOff=on"
            )
        if not cfg.get("order_url"):
            cfg["order_url"] = "https://kor.lps.lottedfs.com/kr/newOrder"
        if not cfg.get("lps_login_url"):
            cfg["lps_login_url"] = (
                "https://kor.lps.lottedfs.com/kr/member/login"
            )
        cfg.setdefault("login_config", {})
        return cfg

    @staticmethod
    def _order_url_pattern(order_url: str) -> str:
        """주문서 URL → wait_for_url 매칭 패턴 (마지막 path 세그먼트 기반)."""
        if not order_url:
            return "**newOrder**"
        tail = order_url.rstrip("/").split("/")[-1].split("?")[0]
        return f"**{tail}**" if tail else "**newOrder**"

    def _login_challenge_visible(self) -> bool:
        """현재 페이지/모달에 가시 상태의 비밀번호 입력이 노출되어 있는지."""
        return bool(self.page.evaluate(
            "() => {"
            "  const inputs = document.querySelectorAll('input[type=\"password\"]');"
            "  for (const el of inputs) {"
            "    if (el.offsetParent === null) continue;"
            "    const r = el.getBoundingClientRect();"
            "    if (r.width > 0 && r.height > 0) return true;"
            "  }"
            "  return false;"
            "}"
        ))

    def _handle_login_popup(
        self, popup, credential: dict, login_config: dict,
    ) -> bool:
        """별도 창으로 열린 로그인 팝업 내부에서 로그인 수행.

        팝업이 자동 닫힘(window.close)되거나 타임아웃까지 대기한다.
        Returns: 로그인 성공 여부.
        """
        try:
            popup.wait_for_load_state("domcontentloaded", timeout=10000)
        except Exception:
            pass
        self._log(f"  로그인 팝업 감지: {popup.url[:120]}")

        # 팝업에 비밀번호 입력란이 있을 때만 로그인 시도
        try:
            has_pwd = bool(popup.evaluate(
                "() => !!document.querySelector('input[type=\"password\"]')"
            ))
        except Exception:
            has_pwd = False
        if not has_pwd:
            self._log("  팝업에 비밀번호 입력란이 없습니다.")
            return False

        # BaseAgent._do_login은 page 인자를 받아 해당 page에서 동작 → popup 직접 전달
        if not self._do_login(popup, credential, login_config):
            self._log("  팝업 로그인 실패")
            return False
        self._log("  팝업 로그인 성공")

        # 팝업이 알아서 닫히기를 기다림 (window.close on success)
        try:
            popup.wait_for_event("close", timeout=15000)
            self._log("  팝업 자동 종료 확인")
        except Exception:
            self._log("  팝업이 자동 종료되지 않음 (계속 진행)")
        return True

    def _navigate_to_order_page(
        self, detail_url: str, order_url_pattern: str,
        credential: dict, login_config: dict,
    ) -> bool:
        """상품상세에서 "바로구매" → 로그인 팝업 창/모달/cartPopup 처리 → 주문서 도달.

        롯데면세점 흐름:
          상품상세 → 바로구매 클릭 → 신규 창(loginPopup) 열림 → 팝업 내 로그인
          → 팝업 자동 종료 → 메인 페이지가 주문서(newOrder)로 이동.

        팝업 창이 열리지 않는 케이스(이미 SSO 세션 보유 등)에는 메인 페이지의
        cartPopup 모달 또는 로그인 모달을 처리한다.
        Returns: 주문서(order_url_pattern) 도달 여부.
        """
        target = order_url_pattern.replace("**", "")
        max_attempts = 3
        ctx = self.page.context

        for attempt in range(1, max_attempts + 1):
            popup_holder = {"page": None}

            def _on_new_page(p):
                if popup_holder["page"] is None:
                    popup_holder["page"] = p

            ctx.on("page", _on_new_page)
            try:
                # ── 1) 바로구매 클릭 ──────────────────────────────
                click_result = self.page.evaluate(_JS_CLICK_ORDER_BUTTON)
                if not click_result.get("ok"):
                    self._log(
                        f"  주문 버튼 못 찾음: {click_result.get('error')}"
                    )
                    return False
                self._log(
                    f"  주문 버튼: {click_result.get('text')} "
                    f"({click_result.get('method')})"
                )

                # ── 2) 신규 창(로그인 팝업) 또는 URL 변화 대기 ──
                deadline = time.time() + 5
                while time.time() < deadline:
                    if popup_holder["page"] is not None:
                        break
                    if target in self.page.url:
                        break
                    self.page.wait_for_timeout(200)

                # ── 3) 로그인 팝업 창이 열렸으면 그 안에서 로그인 ──
                popup = popup_holder["page"]
                if popup is not None and not popup.is_closed():
                    ok = self._handle_login_popup(
                        popup, credential, login_config,
                    )
                    if not ok:
                        return False
                    # 메인 페이지가 주문서로 자동 이동했는지 확인
                    try:
                        self.page.wait_for_url(
                            order_url_pattern, timeout=15000,
                        )
                    except Exception:
                        pass
                    if target in self.page.url:
                        break
                    # 메인이 그대로 상품상세에 머문 경우 → 바로구매부터 재시도
                    self._log(
                        f"  팝업 후 주문서 미도달 (현재: {self.page.url[:80]}) → 재시도"
                    )
                    continue

                # ── 4) 팝업 창이 안 떴다면 같은 페이지 모달 처리 ──
                if target in self.page.url:
                    break

                # 메인 페이지에 로그인 폼이 직접 노출된 경우
                if self._login_challenge_visible():
                    self._log(
                        f"  메인 페이지 로그인 폼 감지 → 재로그인 (시도 {attempt})"
                    )
                    if not self._do_login(self.page, credential, login_config):
                        self._log("  재로그인 실패")
                        return False
                    self._log("  재로그인 성공 → 상품상세 재진입")
                    self._safe_goto(detail_url)
                    self.page.wait_for_timeout(
                        DEFAULT_SETTINGS["initial_wait_ms"],
                    )
                    self._human_dwell()
                    continue

                # cartPopup 같은 페이지 모달 확정
                self.page.wait_for_timeout(1200)
                popup_result = self.page.evaluate(_JS_CLICK_POPUP_CONFIRM)
                if popup_result.get("ok"):
                    self._log(
                        f"  팝업 확정 버튼: {popup_result.get('text')}"
                    )
                    try:
                        self.page.wait_for_url(
                            order_url_pattern, timeout=15000,
                        )
                    except Exception:
                        pass
                else:
                    labels = popup_result.get("popup_buttons") or []
                    if labels:
                        self._log(
                            f"  팝업 확정 버튼 미발견. 팝업 내 버튼: {labels[:8]}"
                        )

                if target in self.page.url:
                    break

                # 확정 후 다시 로그인 폼이 떴다면 재로그인
                if self._login_challenge_visible():
                    self._log(
                        f"  확정 후 로그인 폼 감지 → 재로그인 (시도 {attempt})"
                    )
                    if not self._do_login(self.page, credential, login_config):
                        return False
                    self._safe_goto(detail_url)
                    self.page.wait_for_timeout(
                        DEFAULT_SETTINGS["initial_wait_ms"],
                    )
                    self._human_dwell()
                    continue

                break
            finally:
                try:
                    ctx.remove_listener("page", _on_new_page)
                except Exception:
                    pass

        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=10000)
        except Exception:
            pass
        self.page.wait_for_timeout(DEFAULT_SETTINGS["initial_wait_ms"])
        self._human_dwell()
        return target in self.page.url

    def run_site(self, site_id: int):
        """단일 사이트의 주문서 결제정보를 수집한다."""
        site = self.db.get_site(site_id)
        if not site:
            self._log(f"사이트 ID={site_id} 없음")
            return

        raw_cfg = self.get_crawl_config(site)
        cfg = self._normalize_config(raw_cfg)
        site_name = site["site_name"]
        site_url = site["site_url"]

        product_codes = cfg.get("product_codes") or []
        self._log(f"{'='*50}")
        self._log(f"  주문서 수집: {site_name}")
        self._log(f"  수집 대상 상품 {len(product_codes)}건")
        self._log(f"{'='*50}")

        start_time = time.time()
        result_id = self.db.create_result(site_id)
        all_results = []

        try:
            # ── 1. 브라우저 시작 (ProductAgent 동일 패턴) ──────────
            # 루트 도메인으로 쿠키 영속화 (서브도메인 간 쿠키 공유)
            # kor.lottedfs.com + kor.lps.lottedfs.com → lottedfs.com
            raw_domain = self._get_cookie_domain(site_url)
            parts = raw_domain.split(".")
            cookie_domain = ".".join(parts[-2:]) if len(parts) > 2 else raw_domain
            # Headless 모드로 실행 (AWS 등 화면 없는 서버 환경 지원)
            # lps 서브도메인은 사전 로그인으로 봇 차단 우회
            self._log(f"브라우저 시작 (cookie: {cookie_domain}, headless)...")
            self.page = self._create_page(
                cookie_domain=cookie_domain, headless=True,
            )

            # ── 2. 로그인 ─────────────────────────────────────────
            credential = self._get_next_credential(site_id)
            if not credential:
                self._log("등록된 로그인 계정이 없습니다.")
                self._finish_result(result_id, "error", start_time, "로그인 계정 없음")
                return

            login_url = cfg.get("login_url") or site_url
            self._log(f"로그인 페이지 이동: {login_url}")
            resp = self._safe_goto(login_url)
            if self._is_blocked(resp):
                self._log(f"로그인 페이지 차단됨 (HTTP {resp.status if resp else 'N/A'})")
                self._finish_result(result_id, "blocked", start_time, "로그인 페이지 차단")
                return

            self.page.wait_for_timeout(DEFAULT_SETTINGS["initial_wait_ms"])
            self._human_dwell()

            # 쿠키로 이미 로그인된 상태인지 확인
            # → 로그인 페이지가 아닌 다른 페이지로 리다이렉트되면 이미 로그인됨
            current_url = self.page.url
            has_pwd_field = self.page.evaluate(
                "() => !!document.querySelector('input[type=\"password\"]')"
            )

            if has_pwd_field:
                self._log(f"로그인 시도: {credential['login_id']}")
                login_ok = self._do_login(
                    self.page, credential, cfg.get("login_config"),
                )
                if not login_ok:
                    self._log("로그인 실패")
                    self._finish_result(
                        result_id, "error", start_time, "로그인 실패",
                    )
                    return
                self._log("로그인 성공")
            else:
                self._log(f"쿠키로 이미 로그인 상태 (→ {current_url[:60]})")

            self._human_dwell()
            self._delay()

            # ── 2-2. lps 서브도메인 사전 로그인 ──────────────────
            # kor.lps.lottedfs.com은 별도 세션 체계 → 사전 로그인 필요
            # (성인인증 상품 접근 + 팝업 없이 바로 주문서 도달)
            lps_login_url = cfg.get(
                "lps_login_url",
                "https://kor.lps.lottedfs.com/kr/member/login",
            )
            self._log(f"lps 서브도메인 로그인: {lps_login_url}")
            resp = self._safe_goto(lps_login_url)
            self.page.wait_for_timeout(3000)

            lps_has_pwd = self.page.evaluate(
                "() => !!document.querySelector('input[type=\"password\"]')"
            )
            if lps_has_pwd:
                lps_ok = self._do_login(
                    self.page, credential, cfg.get("login_config"),
                )
                if lps_ok:
                    self._log("lps 로그인 성공")
                else:
                    self._log("[WARN] lps 로그인 실패 - 팝업 로그인으로 대체 시도")
            else:
                self._log("lps 이미 로그인 상태")

            self._human_dwell()
            self._delay()

            # ── 3. 상품 코드 목록 확인 ────────────────────────────
            if not product_codes:
                self._log("등록된 상품 코드가 없습니다. (crawl_config.product_codes)")
                self._finish_result(result_id, "success", start_time)
                return

            url_template = cfg.get("product_detail_url_template", "")
            order_url_pattern = self._order_url_pattern(cfg.get("order_url", ""))
            self._log(f"상품 코드 {len(product_codes)}건 순회 시작")

            # ── 4. 상품별 반복: 상품상세 → 주문/구매 클릭 → 주문서 → 결제정보 ─
            for i, prd_no in enumerate(product_codes):
                detail_url = url_template.format(prdNo=prd_no)
                self._log(f"\n--- [{i+1}/{len(product_codes)}] 상품코드 {prd_no} ---")
                self._log(f"  상품상세 이동: {detail_url[:120]}")

                resp = self._safe_goto(detail_url)
                if self._is_blocked(resp):
                    self._log(f"  상품상세 차단됨 (HTTP {resp.status if resp else 'N/A'})")
                    all_results.append({
                        "product_code": prd_no,
                        "product_name": "",
                        "payment_usd": "",
                        "payment_krw": "",
                        "discount_rate": "",
                        "detail_url": detail_url,
                        "error": "상품상세 차단",
                    })
                    continue

                self.page.wait_for_timeout(DEFAULT_SETTINGS["initial_wait_ms"])

                # 성인인증 상품 감지
                # → 상품상세 진입 시 member/login?adultYn=Y로 리다이렉트
                # → lps 로그인 페이지에서 재로그인 후 상품상세 재접근
                cur_url = self.page.url
                if "member/login" in cur_url and "adultYn=Y" in cur_url:
                    self._log(f"  성인인증 리다이렉트 감지 → 재로그인 시도")
                    adult_has_pwd = self.page.evaluate(
                        "() => !!document.querySelector('input[type=\"password\"]')"
                    )
                    if adult_has_pwd:
                        adult_ok = self._do_login(
                            self.page, credential, cfg.get("login_config"),
                        )
                        if adult_ok:
                            self._log("  성인인증 로그인 성공 → 상품상세 재접근")
                            resp = self._safe_goto(detail_url)
                            self.page.wait_for_timeout(
                                DEFAULT_SETTINGS["initial_wait_ms"],
                            )
                            cur_url = self.page.url
                    # 재로그인 후에도 여전히 로그인 페이지이면 건너뜀
                    if "member/login" in cur_url:
                        self._log(f"  성인인증 상품 접근 실패 (→ {cur_url[:100]})")
                        all_results.append({
                            "product_code": prd_no,
                            "product_name": "",
                            "payment_usd": "",
                            "payment_krw": "",
                            "discount_rate": "",
                            "detail_url": detail_url,
                            "order_url": cur_url,
                            "error": "성인인증 상품 - 접근 실패",
                        })
                        continue

                self._human_dwell()
                self._human_scroll()

                # 바로구매 → 팝업/로그인 모달 처리 → 주문서 도달까지 일괄 수행
                self._log("  바로구매 흐름 시작")
                reached = self._navigate_to_order_page(
                    detail_url, order_url_pattern,
                    credential, cfg.get("login_config") or {},
                )
                self._log(f"  현재 URL: {self.page.url[:120]}")
                if not reached:
                    self._log("  주문서 도달 실패")
                    all_results.append({
                        "product_code": prd_no,
                        "product_name": "",
                        "payment_usd": "",
                        "payment_krw": "",
                        "discount_rate": "",
                        "detail_url": detail_url,
                        "order_url": self.page.url,
                        "error": "주문서 미도달",
                    })
                    continue

                # 결제정보 추출
                self._log("  결제정보 추출 중...")
                data = self.page.evaluate(_JS_EXTRACT_ORDER_PAYMENT)
                product_name = data.get("product_name", "")
                payment_usd = data.get("payment_usd", "")
                payment_krw = data.get("payment_krw", "")
                discount_rate = data.get("discount_rate", "")

                has_payment = bool(payment_usd or payment_krw)
                if has_payment:
                    self._log(f"    상품명     : {product_name or '(미수집)'}")
                    self._log(f"    결제금액(USD): {payment_usd or '-'}")
                    self._log(f"    결제금액(KRW): {payment_krw or '-'}")
                    self._log(f"    할인율      : {discount_rate or '-'}")
                else:
                    self._log("  결제금액을 찾지 못했습니다.")
                    for rt in data.get("raw_texts", [])[:2]:
                        self._log(f"    raw: {rt[:150]}")

                all_results.append({
                    "product_code": prd_no,
                    "product_name": product_name,
                    "payment_usd": payment_usd,
                    "payment_krw": payment_krw,
                    "discount_rate": discount_rate,
                    "detail_url": detail_url,
                    "order_url": self.page.url,
                })

                self._delay()

            # ── 5. 로그아웃 ───────────────────────────────────────
            self._log("\n로그아웃 진행")
            self._logout(site_url)

            # ── 6. 전체 결과 저장 ─────────────────────────────────
            success_count = sum(
                1 for r in all_results
                if r.get("payment_usd") or r.get("payment_krw")
            )
            self._log(f"\n{'='*50}")
            self._log(f"  수집 완료: {success_count}/{len(all_results)}건 성공")

            order_data = {
                "results": all_results,
                "total_items": len(product_codes),
                "success_count": success_count,
                "collected_at": datetime.now().isoformat(),
                "credential_used": credential["login_id"],
            }

            self._save_json(site_id, site_name, order_data)

            elapsed = time.time() - start_time
            self.db.update_result(
                result_id,
                status="success",
                products=all_results,
                product_count=len(all_results),
                store_info={
                    "total_items": len(product_codes),
                    "success_count": success_count,
                },
                elapsed_sec=elapsed,
            )
            self._log(f"총 소요시간: {elapsed:.1f}초")

        except Exception as e:
            self._log(f"오류 발생: {e}")
            import traceback
            self._log(traceback.format_exc())
            self._finish_result(result_id, "error", start_time, str(e))
        finally:
            try:
                self.browser_mgr.close()
            except Exception:
                pass

    # ═══════════════════════════════════════════════════════════════
    # 헬퍼 메서드
    # ═══════════════════════════════════════════════════════════════

    def _logout(self, site_url: str):
        """롯데면세점 홈으로 이동 후 javascript:logout() 호출."""
        try:
            # 홈 도메인이 아니면 메인 도메인 홈으로 이동
            if "kor.lottedfs.com" not in self.page.url:
                home_url = site_url if "kor.lottedfs.com" in (site_url or "") \
                    else "https://kor.lottedfs.com/kr/shopmain/home"
                self._safe_goto(home_url)
                self.page.wait_for_timeout(1500)
                try:
                    self.page.wait_for_load_state(
                        "domcontentloaded", timeout=5000,
                    )
                except Exception:
                    pass

            # window.logout() 호출 (페이지 글로벌 함수)
            self.page.evaluate(
                "() => { "
                "  if (typeof window.logout === 'function') { "
                "    try { window.logout(); return 'called'; } "
                "    catch(e) { return 'error:' + e.message; } "
                "  } "
                "  return 'no-logout-fn'; "
                "}"
            )
            self.page.wait_for_timeout(2000)
            try:
                self.page.wait_for_load_state(
                    "domcontentloaded", timeout=5000,
                )
            except Exception:
                pass
            self._log(f"로그아웃 완료 (→ {self.page.url[:80]})")
        except Exception as e:
            self._log(f"로그아웃 중 오류: {e}")

    def _finish_result(self, result_id, status, start_time, error_msg=None):
        """수집 결과 레코드를 종료 상태로 업데이트한다."""
        elapsed = time.time() - start_time
        self.db.update_result(
            result_id, status=status,
            error_msg=error_msg, elapsed_sec=elapsed,
        )

    def _save_json(self, site_id, site_name, order_data):
        """수집 결과를 JSON 파일로 저장한다."""
        safe_name = "".join(
            c if c.isalnum() or c in "._- " else "_" for c in site_name
        )
        out_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "output", f"{site_id}_{safe_name}",
        )
        os.makedirs(out_dir, exist_ok=True)

        order_path = os.path.join(out_dir, "order_payment.json")
        with open(order_path, "w", encoding="utf-8") as f:
            json.dump(order_data, f, ensure_ascii=False, indent=2)
        self._log(f"저장: {order_path}")

        meta = {
            "site_id": site_id,
            "site_name": site_name,
            "agent_type": "order",
            "collected_at": order_data.get("collected_at"),
            "total_items": order_data.get("total_items", 0),
            "success_count": order_data.get("success_count", 0),
        }
        meta_path = os.path.join(out_dir, "crawl_result.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

    def _log(self, msg):
        """UnicodeEncodeError 안전 로그 출력."""
        try:
            print(f"{_TAG} {msg}")
        except UnicodeEncodeError:
            print(f"{_TAG} {msg.encode('utf-8', errors='replace').decode('utf-8')}")
