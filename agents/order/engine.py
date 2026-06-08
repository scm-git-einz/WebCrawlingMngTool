"""
주문서 결제정보 수집 에이전트

장바구니 상품을 한 건씩 선택 → 주문서 이동 → 결제정보 수집 → 장바구니 복귀
를 반복하여 상품별 최종결제금액을 수집한다.

파이프라인:
  1. 브라우저 시작 (Stealth + 쿠키 로드)
  2. 로그인 페이지 접속 → 로그인 (계정 로테이션)
  3. 장바구니 페이지 접속 → 상품 목록 파악
  4. 상품별 반복:
     a. 전체 해제 → 해당 상품만 선택
     b. 주문하기 클릭 → 주문서 페이지 이동
     c. 결제정보 추출 (할인율/결제금액($)/결제금액(원))
     d. 장바구니 페이지 복귀
  5. 전체 결과 JSON 저장

봇 차단 대응:
  - BaseAgent 상속 (Stealth 브라우저, 적응형 백오프, 인간형 행동)
  - _safe_goto → _is_blocked → _human_dwell → _human_scroll 패턴 준수
  - 페이지 이동 간 _delay() 적용

대상: 롯데면세점, 신라면세점, 현대면세점 등 로그인 기반 주문 페이지
"""
import json
import os
import random
import time
from datetime import datetime

from core.base_agent import BaseAgent, DEFAULT_SETTINGS
from core.network_interceptor import NetworkInterceptor


_TAG = "[order]"

# ─── 장바구니 상품 목록 추출 ────────────────────────────────────
_JS_GET_CART_ITEMS = """() => {
    const items = [];
    const itemSelectors = [
        '.cart_prd_list > li', '.cart-product-list > li',
        '.order_prd_list > li', '.order-product-list > li',
        '[class*="cartItem"]', '[class*="cart_item"]',
        '[class*="cart"] [class*="prd_item"]',
        '[class*="cart"] [class*="goods_item"]',
        'table[class*="cart"] tbody tr',
        '.cart_cont li', '.cart_list li',
    ];

    let container = null;
    let els = [];
    for (const sel of itemSelectors) {
        els = [...document.querySelectorAll(sel)];
        if (els.length > 0) { container = sel; break; }
    }
    if (els.length === 0) return { items: [], selector: '', error: 'cart items not found' };

    for (let idx = 0; idx < els.length; idx++) {
        const el = els[idx];
        const text = (el.textContent || '').trim();
        if (text.length < 5) continue;

        // 체크박스
        const checkbox = el.querySelector(
            'input[type="checkbox"], [class*="check"] input, [role="checkbox"]'
        );

        // 상품명
        let name = '';
        const nameEl = el.querySelector(
            '[class*="prd_name"], [class*="prdName"], [class*="goods_name"], ' +
            '[class*="goodsNm"], [class*="product_name"], [class*="productName"], ' +
            '[class*="item_name"], [class*="itemName"], .name, .tit, .title'
        );
        if (nameEl) {
            name = nameEl.textContent.trim();
        } else {
            const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
            let longest = '';
            while (walker.nextNode()) {
                const t = walker.currentNode.textContent.trim();
                if (t.length > longest.length && t.length > 5) longest = t;
            }
            name = longest;
        }
        if (!name) continue;

        // 수량
        let qty = '1';
        const qtyEl = el.querySelector(
            'input[name*="qty"], input[name*="count"], input[class*="qty"], ' +
            '[class*="qty"] input, [class*="count"]'
        );
        if (qtyEl) qty = qtyEl.value || qtyEl.textContent.trim() || '1';
        const qtyMatch = text.match(/(\\d+)\\s*개/);
        if (qtyMatch && qty === '1') qty = qtyMatch[1];

        // 가격
        const prices = [];
        const priceRegex = /\\$[\\d,.]+|[\\d,]+원/g;
        let m;
        while ((m = priceRegex.exec(text)) !== null) prices.push(m[0]);

        // 브랜드
        let brand = '';
        const brandEl = el.querySelector('[class*="brand"], [class*="cate"]');
        if (brandEl) brand = brandEl.textContent.trim();

        // 이미지
        const img = el.querySelector('img');
        const imageUrl = img ? (img.src || img.getAttribute('data-src') || '') : '';

        items.push({
            index: idx,
            name: name.substring(0, 200),
            brand,
            qty,
            prices,
            image_url: imageUrl,
            has_checkbox: !!checkbox,
            checkbox_checked: checkbox ? checkbox.checked : false,
        });
    }

    return { items, selector: container };
}"""

# ─── 장바구니: 전체 해제 → N번째만 선택 ─────────────────────────
_JS_SELECT_SINGLE_ITEM = """(containerSel, targetIdx) => {
    const els = [...document.querySelectorAll(containerSel)];
    if (els.length === 0) return { ok: false, error: 'no items' };

    // 1) 전체선택 체크박스 해제
    const selectAllCb = document.querySelector(
        '[class*="all"] input[type="checkbox"], ' +
        'input[id*="checkAll"], input[name*="checkAll"], ' +
        '[class*="selectAll"] input, [class*="allCheck"] input'
    );
    if (selectAllCb && selectAllCb.checked) selectAllCb.click();

    // 2) 개별 해제
    const allCheckboxes = [];
    els.forEach(el => {
        const cb = el.querySelector('input[type="checkbox"], [role="checkbox"]');
        if (cb) allCheckboxes.push(cb);
    });
    allCheckboxes.forEach(cb => { if (cb.checked) cb.click(); });

    // 3) 대상 항목만 선택
    if (targetIdx >= els.length) return { ok: false, error: 'index out of range' };
    const targetEl = els[targetIdx];
    const targetCb = targetEl.querySelector('input[type="checkbox"], [role="checkbox"]');
    if (!targetCb) return { ok: false, error: 'no checkbox at target' };
    if (!targetCb.checked) targetCb.click();

    return {
        ok: true,
        checked_count: allCheckboxes.filter(cb => cb.checked).length,
        target_checked: targetCb.checked,
    };
}"""

# ─── 주문하기 버튼 클릭 ──────────────────────────────────────
_JS_CLICK_ORDER_BUTTON = """() => {
    // 텍스트 기반 탐색
    const allBtns = [...document.querySelectorAll('button, a[role="button"], input[type="button"], a.btn')];
    const textBtn = allBtns.find(b => {
        const t = b.textContent.trim();
        return /^(주문하기|주문|구매하기|결제하기|바로구매|ORDER)$/i.test(t);
    });
    if (textBtn) { textBtn.click(); return { ok: true, method: 'text', text: textBtn.textContent.trim() }; }

    // 셀렉터 기반 탐색
    const candidates = [
        'button[class*="order"], a[class*="order"]',
        'button[class*="buy"], a[class*="buy"]',
        '[class*="btn_order"], [class*="btnOrder"]',
        '[class*="btn_buy"], [class*="btnBuy"]',
    ];
    for (const sel of candidates) {
        const el = document.querySelector(sel);
        if (el && el.offsetParent !== null) {
            const t = el.textContent.trim();
            if (t && !/삭제|취소|닫기/i.test(t)) {
                el.click();
                return { ok: true, method: 'selector', selector: sel, text: t };
            }
        }
    }
    return { ok: false, error: 'order button not found' };
}"""

# ─── 주문서 결제정보 추출 ──────────────────────────────────────
_JS_EXTRACT_ORDER_PAYMENT = """() => {
    const summary = {};
    const raw_texts = [];

    // ═══════════════════════════════════════════════════════
    // 1단계: 면세점 특화 — dl.expected_payment
    //   <dl class="expected_payment">
    //     <dt>결제금액</dt>
    //     <dd class="price">
    //       <p><span>50%</span><strong>$251.49</strong></p>
    //       (380,076원)
    //     </dd>
    //   </dl>
    // ═══════════════════════════════════════════════════════
    const expectedDl = document.querySelector(
        'dl.expected_payment, dl[class*="expected"], dl[class*="payment_total"]'
    );
    if (expectedDl) {
        const dd = expectedDl.querySelector('dd, dd.price');
        if (dd) {
            const rateEl = dd.querySelector('p > span, span[class*="rate"], span[class*="percent"]');
            if (rateEl) {
                const rateMatch = rateEl.textContent.trim().match(/(\\d+)%/);
                if (rateMatch) summary.discount_rate = rateMatch[0];
            }
            const usdEl = dd.querySelector('strong, p > strong');
            if (usdEl) {
                const usdMatch = usdEl.textContent.trim().match(/\\$[\\d,.]+/);
                if (usdMatch) summary.payment_usd = usdMatch[0];
            }
            const ddText = dd.textContent || '';
            const krwMatch = ddText.match(/\\(?([\\d,]+)원\\)?/);
            if (krwMatch) summary.payment_krw = krwMatch[1] + '원';
        }
    }

    // ═══════════════════════════════════════════════════════
    // 2단계: 결제정보 전체 dl/dt-dd 라벨-값 탐색
    // ═══════════════════════════════════════════════════════
    const LABEL_MAP = {
        '정상가': 'regular_price', '상품금액': 'regular_price', '총 상품금액': 'regular_price',
        '회원할인': 'member_discount', '회원 할인': 'member_discount',
        '즉시할인': 'instant_discount',
        '혜택': 'benefits', '할인혜택': 'benefits',
        '쿠폰할인': 'coupon_discount',
        '결제금액': 'payment_amount', '결제 금액': 'payment_amount',
        '최종결제금액': 'final_payment', '총 결제금액': 'final_payment',
        '면세한도적용금액': 'duty_free_limit', '면세한도 적용금액': 'duty_free_limit',
        '과세 포인트': 'tax_point', '과세포인트': 'tax_point',
        '적립': 'reward_points', '적립 L.POINT': 'reward_points', 'L.POINT': 'reward_points',
        '배송비': 'shipping_fee',
    };

    function extractPriceText(el) {
        if (!el) return '';
        return el.textContent.trim().replace(/\\s+/g, ' ').substring(0, 100);
    }
    function matchLabel(text) {
        const clean = text.replace(/\\s+/g, ' ').trim();
        for (const [kor, eng] of Object.entries(LABEL_MAP)) {
            if (clean.includes(kor)) return eng;
        }
        return null;
    }

    document.querySelectorAll('dl').forEach(dl => {
        const dts = dl.querySelectorAll('dt');
        const dds = dl.querySelectorAll('dd');
        dts.forEach((dt, i) => {
            const key = matchLabel(dt.textContent);
            if (key && dds[i] && !summary[key]) {
                const ddText = extractPriceText(dds[i]);
                summary[key] = ddText;
                const usdMatch = ddText.match(/\\$[\\d,.]+/);
                const krwMatch = ddText.match(/([\\d,]+)원/);
                if (key === 'regular_price') {
                    if (usdMatch) summary.regular_price_usd = usdMatch[0];
                    if (krwMatch) summary.regular_price_krw = krwMatch[1] + '원';
                } else if (key === 'member_discount') {
                    if (usdMatch) summary.member_discount_usd = usdMatch[0];
                    if (krwMatch) summary.member_discount_krw = krwMatch[1] + '원';
                } else if (key === 'benefits') {
                    if (usdMatch) summary.benefits_usd = usdMatch[0];
                    if (krwMatch) summary.benefits_krw = krwMatch[1] + '원';
                }
            }
        });
    });

    // table th-td
    document.querySelectorAll('table tr').forEach(tr => {
        const th = tr.querySelector('th, .tit, .label');
        const td = tr.querySelector('td, .data, .value');
        if (th && td) {
            const key = matchLabel(th.textContent);
            if (key && !summary[key]) summary[key] = extractPriceText(td);
        }
    });

    // ═══════════════════════════════════════════════════════
    // 3단계: 주문서 상품 정보 (1건)
    // ═══════════════════════════════════════════════════════
    let orderItem = {};
    const nameEl = document.querySelector(
        '[class*="prd_name"], [class*="prdName"], [class*="goods_name"], ' +
        '[class*="productName"], [class*="item_name"], ' +
        '.order_prd_list .name, .order_prd_list .tit'
    );
    if (nameEl) orderItem.name = nameEl.textContent.trim().substring(0, 200);
    const brandEl = document.querySelector('[class*="brand"], [class*="cate"]');
    if (brandEl) orderItem.brand = brandEl.textContent.trim();
    const img = document.querySelector('.order_prd_list img, [class*="order"] [class*="prd"] img');
    if (img) orderItem.image_url = img.src || '';

    // raw text (디버깅용)
    const payAreas = document.querySelectorAll(
        '[class*="pay"], [class*="settle"], [class*="expected"], ' +
        '[class*="order_info"], [class*="total"], [class*="summary"]'
    );
    payAreas.forEach(area => {
        const text = area.textContent.replace(/\\s+/g, ' ').trim().substring(0, 500);
        if (text.length > 10) raw_texts.push(text);
    });

    return { payment_summary: summary, order_item: orderItem, raw_texts };
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
        """UI crawl_config → Agent 내부 config 변환."""
        cfg = dict(crawl_cfg)
        cfg.setdefault("login_url", "")
        cfg.setdefault("cart_url", "")
        cfg.setdefault("collect_items", True)
        cfg.setdefault("collect_payment", True)
        cfg.setdefault("login_config", {})
        return cfg

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

        self._log(f"{'='*50}")
        self._log(f"  주문서 수집: {site_name}")
        self._log(f"  장바구니: {cfg.get('cart_url') or site_url}")
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
            # lps 도메인은 headless 브라우저를 감지하여 image/png 반환
            # → headless=False (화면 있는 브라우저)로 봇 차단 우회
            self._log(f"브라우저 시작 (cookie: {cookie_domain}, headed)...")
            self.page = self._create_page(
                cookie_domain=cookie_domain, headless=False,
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

            # ── 3. 장바구니 페이지 이동 ───────────────────────────
            cart_url = cfg.get("cart_url") or site_url
            self._log(f"장바구니 이동: {cart_url}")
            resp = self._safe_goto(cart_url)
            if self._is_blocked(resp):
                self._log("장바구니 페이지 차단됨")
                self._finish_result(result_id, "blocked", start_time, "장바구니 차단")
                return

            self.page.wait_for_timeout(DEFAULT_SETTINGS["initial_wait_ms"])
            self._human_dwell()
            self._human_scroll()

            # ── 4. 장바구니 상품 목록 파악 ────────────────────────
            cart_data = self.page.evaluate(_JS_GET_CART_ITEMS)
            cart_items = cart_data.get("items", [])
            cart_selector = cart_data.get("selector", "")

            if not cart_items:
                self._log("장바구니에 상품이 없습니다.")
                self._log(f"  디버그: {cart_data.get('error', '')}")
                self._finish_result(result_id, "success", start_time)
                return

            self._log(f"장바구니 상품 {len(cart_items)}건 발견")
            for i, item in enumerate(cart_items):
                self._log(f"  [{i+1}] {item['name'][:50]} (수량:{item['qty']})")

            # ── 5. 상품별 반복: 선택 → 주문서 → 수집 → 복귀 ────
            for i, cart_item in enumerate(cart_items):
                self._log(f"\n--- [{i+1}/{len(cart_items)}] {cart_item['name'][:50]} ---")

                # 5-a. 해당 상품만 선택
                self._log("  전체 해제 → 해당 상품만 선택")
                select_result = self.page.evaluate(
                    _JS_SELECT_SINGLE_ITEM, cart_selector, cart_item["index"],
                )
                if not select_result.get("ok"):
                    self._log(f"  선택 실패: {select_result.get('error')}")
                    all_results.append({
                        "cart_item": self._cart_item_summary(cart_item),
                        "payment_summary": {},
                        "error": f"선택 실패: {select_result.get('error')}",
                    })
                    continue

                self.page.wait_for_timeout(random.randint(500, 1000))

                # 5-b. 주문하기 버튼 클릭
                self._log("  주문하기 클릭")
                before_url = self.page.url
                click_result = self.page.evaluate(_JS_CLICK_ORDER_BUTTON)

                if not click_result.get("ok"):
                    self._log(f"  주문 버튼 못 찾음: {click_result.get('error')}")
                    all_results.append({
                        "cart_item": self._cart_item_summary(cart_item),
                        "payment_summary": {},
                        "error": "주문 버튼 미발견",
                    })
                    continue

                self._log(f"  주문 버튼: {click_result.get('text')} ({click_result.get('method')})")

                # 5-c. 주문서 페이지 로드 대기
                try:
                    self.page.wait_for_load_state("domcontentloaded", timeout=15000)
                except Exception:
                    pass
                self.page.wait_for_timeout(DEFAULT_SETTINGS["initial_wait_ms"])
                self._human_dwell()

                # 5-d. 결제정보 추출
                self._log("  결제정보 추출 중...")
                data = self.page.evaluate(_JS_EXTRACT_ORDER_PAYMENT)
                payment = data.get("payment_summary", {})
                order_item_info = data.get("order_item", {})

                if payment:
                    self._log(f"  결제정보 {len(payment)}개 필드:")
                    for key, val in payment.items():
                        self._log(f"    {key}: {val}")
                else:
                    self._log("  결제정보를 찾지 못했습니다.")
                    for rt in data.get("raw_texts", [])[:2]:
                        self._log(f"    raw: {rt[:150]}")

                all_results.append({
                    "cart_item": self._cart_item_summary(cart_item),
                    "order_item": order_item_info,
                    "payment_summary": payment,
                })

                # 5-e. 장바구니 복귀
                self._log(f"  장바구니 복귀")
                self._safe_goto(cart_url)
                self.page.wait_for_timeout(3000)
                self._human_dwell()
                self._delay()

            # ── 6. 전체 결과 저장 ─────────────────────────────────
            success_count = sum(1 for r in all_results if r.get("payment_summary"))
            self._log(f"\n{'='*50}")
            self._log(f"  수집 완료: {success_count}/{len(all_results)}건 성공")

            order_data = {
                "results": all_results,
                "total_items": len(cart_items),
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
                    "total_items": len(cart_items),
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

    @staticmethod
    def _cart_item_summary(cart_item: dict) -> dict:
        """장바구니 항목에서 저장용 필드만 추출한다."""
        return {
            "name": cart_item.get("name", ""),
            "brand": cart_item.get("brand", ""),
            "qty": cart_item.get("qty", "1"),
            "image_url": cart_item.get("image_url", ""),
        }

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
