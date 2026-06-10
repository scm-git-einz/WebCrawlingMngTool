"""
롯데면세점 주문서 수집 — Headless Playwright 테스트

목적:
  기존 OrderAgent(headed 브라우저)를 수정하지 않고,
  Headless 모드에서 주문서 결제정보를 수집할 수 있는지 검증.

AWS 서버 배포 대비:
  - 화면 없는 환경에서 실행 가능 여부 확인
  - 서브도메인 간 쿠키 공유 문제 해결 방안 테스트

롯데면세점 도메인 구조:
  - kor.lottedfs.com      → 로그인 + 상품상세
  - kor.lps.lottedfs.com  → 주문서 (newOrder)

실행:
  python test_order_headless.py --login-id <ID> --login-pwd <PWD> --product-code <상품코드>
  python test_order_headless.py --login-id <ID> --login-pwd <PWD> --product-code 20000842408

단계별 테스트:
  --step login     → 로그인만 테스트
  --step cookie    → 로그인 + 서브도메인 쿠키 공유 확인
  --step detail    → 로그인 + 상품상세 접근
  --step order     → 전체 흐름 (로그인→상품상세→바로구매→주문서→결제정보 추출)
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime
from urllib.parse import urlparse

# Playwright
from playwright.sync_api import sync_playwright, Page, BrowserContext

# stealth 적용
try:
    from playwright_stealth import Stealth
    _stealth = Stealth(
        navigator_languages_override=("ko-KR", "ko"),
        navigator_platform_override="Win32",
    )
except ImportError:
    _stealth = None
    print("[WARN] playwright_stealth 미설치 — stealth 미적용")


# ═══════════════════════════════════════════════════════════════════
# 설정
# ═══════════════════════════════════════════════════════════════════

DOMAINS = {
    "login":  "kor.lottedfs.com",
    "detail": "kor.lottedfs.com",
    "order":  "kor.lps.lottedfs.com",
}

URLS = {
    "login": "https://kor.lottedfs.com/kr/login",
    "detail_template": (
        "https://kor.lottedfs.com/kr/product/productDetail"
        "?prdNo={prdNo}"
    ),
    "order": "https://kor.lps.lottedfs.com/kr/newOrder",
}

BROWSER_CONFIG = {
    "user_agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "viewport": {"width": 1920, "height": 1080},
}

COOKIE_FILE = os.path.join(
    os.path.dirname(__file__), "data", "cookies", "_test_lottedfs.json",
)


# ═══════════════════════════════════════════════════════════════════
# 유틸리티
# ═══════════════════════════════════════════════════════════════════

def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    try:
        sys.stdout.buffer.write((line + "\n").encode("utf-8", errors="replace"))
        sys.stdout.buffer.flush()
    except Exception:
        print(line.encode("ascii", errors="replace").decode("ascii"))


def save_cookies(context: BrowserContext, path: str):
    """브라우저 쿠키를 파일로 저장."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    cookies = context.cookies()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cookies, f, ensure_ascii=False, indent=2)
    log(f"쿠키 저장: {len(cookies)}개 → {path}")


def load_cookies(context: BrowserContext, path: str) -> int:
    """저장된 쿠키를 브라우저에 로드."""
    if not os.path.exists(path):
        return 0
    with open(path, "r", encoding="utf-8") as f:
        cookies = json.load(f)
    if cookies:
        context.add_cookies(cookies)
    log(f"쿠키 로드: {len(cookies)}개 ← {path}")
    return len(cookies)


def dump_cookies_by_domain(context: BrowserContext):
    """도메인별 쿠키 현황 출력 (디버그용)."""
    cookies = context.cookies()
    domain_map: dict[str, list] = {}
    for c in cookies:
        d = c.get("domain", "unknown")
        domain_map.setdefault(d, []).append(c["name"])
    log(f"─── 쿠키 현황 (총 {len(cookies)}개) ───")
    for domain in sorted(domain_map):
        names = domain_map[domain]
        log(f"  {domain}: {len(names)}개 — {', '.join(names[:8])}"
            + (" ..." if len(names) > 8 else ""))


def broaden_cookies(context: BrowserContext):
    """서브도메인 쿠키를 루트 도메인(.lottedfs.com)으로 복제하여 공유 범위 확대.

    롯데면세점은 로그인 시 쿠키가 특정 서브도메인(kor.lds.lottedfs.com)에만
    설정될 수 있음. 이 쿠키를 .lottedfs.com으로 복제하면 모든 서브도메인에서 사용 가능.
    """
    cookies = context.cookies()
    broadened = []
    seen = set()

    for c in cookies:
        domain = c.get("domain", "")
        # 이미 루트 도메인이면 건너뜀
        if domain == ".lottedfs.com":
            continue
        # lottedfs.com 서브도메인의 쿠키만 대상
        if "lottedfs.com" not in domain:
            continue

        key = (c["name"], c.get("path", "/"))
        if key in seen:
            continue
        seen.add(key)

        new_cookie = {
            "name": c["name"],
            "value": c["value"],
            "domain": ".lottedfs.com",
            "path": c.get("path", "/"),
            "httpOnly": c.get("httpOnly", False),
            "secure": c.get("secure", False),
            "sameSite": c.get("sameSite", "Lax"),
        }
        if c.get("expires", -1) > 0:
            new_cookie["expires"] = c["expires"]
        broadened.append(new_cookie)

    if broadened:
        context.add_cookies(broadened)
        log(f"쿠키 확장: {len(broadened)}개를 .lottedfs.com 도메인으로 복제")
    return len(broadened)


# ═══════════════════════════════════════════════════════════════════
# 브라우저 생성
# ═══════════════════════════════════════════════════════════════════

def create_browser(playwright, headless: bool = True):
    """Stealth Chromium 브라우저 + 컨텍스트 + 페이지 생성."""
    browser = playwright.chromium.launch(
        headless=headless,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--lang=ko-KR",
        ],
    )

    context = browser.new_context(
        user_agent=BROWSER_CONFIG["user_agent"],
        viewport=BROWSER_CONFIG["viewport"],
        locale="ko-KR",
        timezone_id="Asia/Seoul",
        extra_http_headers={
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Sec-Ch-Ua": '"Chromium";v="125", "Google Chrome";v="125", "Not=A?Brand";v="8"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
        },
    )

    # 불필요 리소스 차단 (가벼운 로딩)
    def _block_resources(route, request):
        if request.resource_type in ("font", "media"):
            route.abort()
        else:
            route.continue_()
    context.route("**/*", _block_resources)

    # 저장된 쿠키 로드
    load_cookies(context, COOKIE_FILE)

    page = context.new_page()

    # stealth 적용 (페이지 레벨)
    if _stealth:
        _stealth.apply_stealth_sync(page)

    return browser, context, page


# ═══════════════════════════════════════════════════════════════════
# 로그인
# ═══════════════════════════════════════════════════════════════════

def do_login(page: Page, login_id: str, login_pwd: str) -> bool:
    """롯데면세점 로그인 페이지에서 로그인 수행.

    BaseAgent._do_login()의 폼 탐지 로직을 재활용.
    """
    log(f"로그인 페이지 이동: {URLS['login']}")
    resp = page.goto(URLS["login"], wait_until="domcontentloaded", timeout=30000)

    if resp and resp.status != 200:
        log(f"로그인 페이지 HTTP {resp.status}")
        return False

    page.wait_for_timeout(3000)

    # 이미 로그인된 상태인지 확인
    has_pwd = page.evaluate(
        "() => !!document.querySelector('input[type=\"password\"]')"
    )
    if not has_pwd:
        log(f"이미 로그인 상태 (비밀번호 입력란 없음) - URL: {page.url[:80]}")
        return True

    log(f"로그인 시도: {login_id}")
    try:
        # BaseAgent._do_login()과 동일한 폼 탐지 JS
        detected = page.evaluate("""() => {
            const inputs = [...document.querySelectorAll('input:not([type="hidden"])')];
            let idInput = null, pwdInput = null, submitBtn = null;
            for (const inp of inputs) {
                const t = (inp.type || '').toLowerCase();
                const n = (inp.name || '').toLowerCase();
                const id = (inp.id || '').toLowerCase();
                const ph = (inp.placeholder || '').toLowerCase();
                if (t === 'password' && !pwdInput) {
                    pwdInput = inp;
                } else if ((t === 'text' || t === 'email' || t === 'tel') && !idInput) {
                    if (n.match(/id|user|email|login|member|account/) ||
                        id.match(/id|user|email|login|member|account/) ||
                        ph.match(/아이디|id|이메일|email/i)) {
                        idInput = inp;
                    }
                }
            }
            if (pwdInput && !idInput) {
                const prev = inputs[inputs.indexOf(pwdInput) - 1];
                if (prev && prev.type !== 'hidden') idInput = prev;
            }
            const form = (pwdInput || idInput)?.closest('form');
            if (form) {
                submitBtn = form.querySelector(
                    'button[type="submit"], input[type="submit"], button'
                );
            }
            const sel = (el) => {
                if (!el) return '';
                if (el.id) return '#' + el.id;
                if (el.name) return '[name="' + el.name + '"]';
                return '';
            };
            return {
                id_selector: sel(idInput),
                pwd_selector: sel(pwdInput),
                submit_selector: sel(submitBtn),
                debug: {
                    id_tag: idInput ? idInput.tagName + '#' + (idInput.id || '') + '.' + (idInput.className || '') : 'null',
                    pwd_tag: pwdInput ? pwdInput.tagName + '#' + (pwdInput.id || '') + '.' + (pwdInput.className || '') : 'null',
                    submit_tag: submitBtn ? submitBtn.tagName + '#' + (submitBtn.id || '') + ' text=' + (submitBtn.textContent || '').trim().substring(0, 30) : 'null',
                    total_inputs: inputs.length,
                }
            };
        }""")

        id_sel = detected.get("id_selector", "")
        pwd_sel = detected.get("pwd_selector", "")
        submit_sel = detected.get("submit_selector", "")
        debug = detected.get("debug", {})

        log(f"  폼 탐지 결과:")
        log(f"    ID 셀렉터: {id_sel or '(미발견)'} [{debug.get('id_tag', '')}]")
        log(f"    PWD 셀렉터: {pwd_sel or '(미발견)'} [{debug.get('pwd_tag', '')}]")
        log(f"    Submit 셀렉터: {submit_sel or '(미발견)'} [{debug.get('submit_tag', '')}]")
        log(f"    총 input 수: {debug.get('total_inputs', 0)}")

        if not id_sel or not pwd_sel:
            log("로그인 폼을 찾을 수 없습니다")
            # 디버그: 페이지에 있는 모든 input 출력
            all_inputs = page.evaluate("""() => {
                return [...document.querySelectorAll('input')].map(inp => ({
                    type: inp.type, name: inp.name, id: inp.id,
                    placeholder: inp.placeholder,
                    visible: inp.offsetParent !== null,
                }));
            }""")
            log(f"  페이지 내 모든 input: {json.dumps(all_inputs, ensure_ascii=False)[:500]}")
            return False

        # page.fill() 방식으로 입력 (BaseAgent와 동일)
        import random
        page.fill(id_sel, login_id)
        page.wait_for_timeout(random.randint(300, 700))
        page.fill(pwd_sel, login_pwd)
        page.wait_for_timeout(random.randint(300, 700))

        # 입력값 확인 (디버그)
        filled_id = page.evaluate(f"() => document.querySelector('{id_sel}')?.value || ''")
        filled_pwd = page.evaluate(f"() => document.querySelector('{pwd_sel}')?.value || ''")
        log(f"  입력 확인: ID='{filled_id}', PWD길이={len(filled_pwd)}, PWD일치={filled_pwd == login_pwd}")

        if submit_sel:
            log(f"  로그인 버튼 클릭: {submit_sel}")
            page.click(submit_sel)
        else:
            log("  로그인 버튼 미발견 - Enter 키로 제출")
            page.press(pwd_sel, "Enter")

        # 로그인 결과 대기
        page.wait_for_timeout(3000)
        try:
            page.wait_for_load_state("domcontentloaded", timeout=10000)
        except Exception:
            pass

        # 로그인 성공 확인: 비밀번호 입력란이 사라졌는지
        still_login = page.evaluate(
            "() => !!document.querySelector('input[type=\"password\"]')"
        )
        if still_login:
            err_msg = page.evaluate("""() => {
                const errs = document.querySelectorAll(
                    '.error, .err, [class*="error"], [class*="alert"]'
                );
                for (const el of errs) {
                    const t = el.textContent.trim();
                    if (t.length > 5 && t.length < 200) return t;
                }
                return '';
            }""")
            log(f"로그인 실패: {err_msg or '(에러 메시지 없음)'}")
            log(f"  현재 URL: {page.url[:120]}")
            return False

        log(f"로그인 성공 -> {page.url[:80]}")
        return True

    except Exception as e:
        log(f"로그인 중 오류: {e}")
        return False


def do_login_on_current_page(page: Page, login_id: str, login_pwd: str) -> bool:
    """이미 로그인 페이지에 있을 때 해당 페이지에서 로그인 수행."""
    import random

    has_pwd = page.evaluate(
        "() => !!document.querySelector('input[type=\"password\"]')"
    )
    if not has_pwd:
        log("  이미 로그인 상태 (비밀번호 입력란 없음)")
        return True

    detected = page.evaluate("""() => {
        const inputs = [...document.querySelectorAll('input:not([type="hidden"])')];
        let idInput = null, pwdInput = null, submitBtn = null;
        for (const inp of inputs) {
            const t = (inp.type || '').toLowerCase();
            const n = (inp.name || '').toLowerCase();
            const id = (inp.id || '').toLowerCase();
            const ph = (inp.placeholder || '').toLowerCase();
            if (t === 'password' && !pwdInput) {
                pwdInput = inp;
            } else if ((t === 'text' || t === 'email' || t === 'tel') && !idInput) {
                if (n.match(/id|user|email|login|member|account/) ||
                    id.match(/id|user|email|login|member|account/) ||
                    ph.match(/아이디|id|이메일|email/i)) {
                    idInput = inp;
                }
            }
        }
        if (pwdInput && !idInput) {
            const prev = inputs[inputs.indexOf(pwdInput) - 1];
            if (prev && prev.type !== 'hidden') idInput = prev;
        }
        const form = (pwdInput || idInput)?.closest('form');
        if (form) {
            submitBtn = form.querySelector(
                'button[type="submit"], input[type="submit"], button'
            );
        }
        const sel = (el) => {
            if (!el) return '';
            if (el.id) return '#' + el.id;
            if (el.name) return '[name="' + el.name + '"]';
            return '';
        };
        return {
            id_selector: sel(idInput),
            pwd_selector: sel(pwdInput),
            submit_selector: sel(submitBtn),
        };
    }""")

    id_sel = detected.get("id_selector", "")
    pwd_sel = detected.get("pwd_selector", "")
    submit_sel = detected.get("submit_selector", "")

    log(f"  lps 폼 탐지: ID={id_sel or '없음'}, PWD={pwd_sel or '없음'}, Submit={submit_sel or '없음'}")

    if not id_sel or not pwd_sel:
        log("  lps 로그인 폼을 찾을 수 없습니다")
        return False

    try:
        page.fill(id_sel, login_id)
        page.wait_for_timeout(random.randint(300, 700))
        page.fill(pwd_sel, login_pwd)
        page.wait_for_timeout(random.randint(300, 700))

        if submit_sel:
            page.click(submit_sel)
        else:
            page.press(pwd_sel, "Enter")

        page.wait_for_timeout(3000)
        try:
            page.wait_for_load_state("domcontentloaded", timeout=10000)
        except Exception:
            pass

        still_login = page.evaluate(
            "() => !!document.querySelector('input[type=\"password\"]')"
        )
        if still_login:
            # 에러 메시지 확인
            err_msg = page.evaluate("""() => {
                const candidates = document.querySelectorAll(
                    '.error, .err, [class*="error"], [class*="alert"], '
                    + '[class*="msg"], [class*="notice"], [class*="warn"]'
                );
                for (const el of candidates) {
                    const t = el.textContent.trim();
                    if (t.length > 5 && t.length < 300) return t;
                }
                return '';
            }""")
            # 입력값 확인
            filled_id = page.evaluate(f"() => document.querySelector('{id_sel}')?.value || ''")
            filled_pwd_len = page.evaluate(f"() => (document.querySelector('{pwd_sel}')?.value || '').length")
            log(f"  lps 로그인 실패 - URL: {page.url[:120]}")
            log(f"    입력확인: ID='{filled_id}', PWD길이={filled_pwd_len}")
            log(f"    에러: {err_msg[:200] if err_msg else '(없음)'}")
            return False

        log(f"  lps 로그인 성공 -> {page.url[:80]}")
        return True
    except Exception as e:
        log(f"  lps 로그인 중 오류: {e}")
        return False


def random_delay() -> int:
    """인간형 타이핑 딜레이 (ms)."""
    import random
    return random.randint(50, 150)


# ═══════════════════════════════════════════════════════════════════
# 주문 버튼 클릭 (기존 OrderAgent JS 재활용)
# ═══════════════════════════════════════════════════════════════════

JS_CLICK_ORDER_BUTTON = """() => {
    function isVisible(el) {
        if (!el) return false;
        if (el.offsetParent === null) return false;
        const r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0;
    }

    // 1) GA 데이터 속성 우선
    const gaSelectors = [
        'a[data-gaevtaction="바로구매"]',
        'a[data-gaevtlabel="바로구매"]',
    ];
    for (const sel of gaSelectors) {
        const el = document.querySelector(sel);
        if (isVisible(el)) {
            el.click();
            return { ok: true, method: 'ga-attr', text: el.textContent.trim() };
        }
    }

    // 2) cartPopup(..., '2') href
    const popupBtns = [...document.querySelectorAll('a[href*="cartPopup"]')];
    const buyNow = popupBtns.find(a => {
        const h = a.getAttribute('href') || '';
        return /cartPopup\\([^)]*,\\s*['"]2['"]/.test(h) && isVisible(a);
    });
    if (buyNow) {
        buyNow.click();
        return { ok: true, method: 'cartPopup', text: buyNow.textContent.trim() };
    }

    // 3) 이미지 alt 매칭 (img 기반 바로구매 버튼)
    const buyImgs = [...document.querySelectorAll('a > img[alt], button > img[alt]')];
    const imgBtn = buyImgs.find(img => {
        const alt = (img.alt || '').replace(/\\s+/g, '').trim();
        if (!/바로구매|주문하기|구매하기|ORDER/i.test(alt)) return false;
        const parent = img.closest('a, button');
        return parent && isVisible(parent);
    });
    if (imgBtn) {
        const parent = imgBtn.closest('a, button');
        parent.click();
        return { ok: true, method: 'img-alt', text: imgBtn.alt };
    }

    // 4) 텍스트 매칭
    const allBtns = [...document.querySelectorAll('button, a, a[role="button"]')];
    const textBtn = allBtns.find(b => {
        if (!isVisible(b)) return false;
        const t = (b.textContent || '').replace(/\\s+/g, '').trim();
        return /^(바로구매|주문하기|구매하기)$/i.test(t);
    });
    if (textBtn) {
        textBtn.click();
        return { ok: true, method: 'text', text: textBtn.textContent.trim() };
    }
    return { ok: false, error: 'order button not found' };
}"""

JS_CLICK_POPUP_CONFIRM = """() => {
    function isVisible(el) {
        if (!el) return false;
        if (el.offsetParent === null) return false;
        const r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0;
    }

    const popupSelectors = [
        '.popup_wrap', '.layer_popup', '.modal', '[role="dialog"]',
        '[class*="popup"]', '[class*="modal"]', '[class*="layer"]',
    ];
    let popup = null;
    for (const sel of popupSelectors) {
        const cands = [...document.querySelectorAll(sel)];
        const v = cands.find(isVisible);
        if (v) { popup = v; break; }
    }
    if (!popup) return { ok: false, error: 'popup not visible' };

    const btns = [...popup.querySelectorAll('button, a, input[type="button"]')];
    const confirm = btns.find(b => {
        if (!isVisible(b)) return false;
        const t = (b.textContent || b.value || '').replace(/\\s+/g, '').trim();
        if (/취소|닫기|장바구니|계속쇼핑/i.test(t)) return false;
        return /^(주문하기|주문|구매하기|구매|결제하기|바로구매|확인|OK)$/i.test(t);
    });
    if (!confirm) {
        const labels = btns.filter(isVisible)
            .map(b => (b.textContent || b.value || '').trim())
            .filter(t => t.length > 0 && t.length < 30);
        return { ok: false, error: 'popup confirm not found', labels };
    }
    confirm.click();
    return { ok: true, text: (confirm.textContent || confirm.value || '').trim() };
}"""

JS_EXTRACT_ORDER_PAYMENT = """() => {
    const result = {
        product_name: '',
        payment_usd: '',
        payment_krw: '',
        discount_rate: '',
    };

    const FINAL_LABELS = [
        '최종결제금액', '총 결제금액', '결제금액', '결제 금액',
        '총합계', '합계금액', '합계 금액', '총 합계',
    ];
    function matchFinal(text) {
        return FINAL_LABELS.some(l => (text || '').replace(/\\s+/g, ' ').trim().includes(l));
    }
    function pickUsd(t) { const m = (t||'').match(/-?\\$[\\d,.]+/); return m ? m[0] : ''; }
    function pickKrw(t) { const m = (t||'').match(/\\(?(-?[\\d,]+)원\\)?/); return m ? m[1]+'원' : ''; }
    function pickRate(t) { const m = (t||'').match(/(\\d+)\\s*%/); return m ? m[0].replace(/\\s/g,'') : ''; }
    function set(k,v) { if (v && !result[k]) result[k] = v; }

    // 1) dl.expected_payment
    const dl1 = document.querySelector('dl.expected_payment, dl[class*="expected"]');
    if (dl1) {
        const dd = dl1.querySelector('dd');
        if (dd) {
            const rateEl = dd.querySelector('p > span, span[class*="rate"]');
            if (rateEl) set('discount_rate', pickRate(rateEl.textContent));
            const usdEl = dd.querySelector('strong, p > strong');
            if (usdEl) set('payment_usd', pickUsd(usdEl.textContent));
            set('payment_krw', pickKrw(dd.textContent));
        }
    }

    // 2) dl/dt-dd 라벨 매칭
    document.querySelectorAll('dl').forEach(dl => {
        const dts = dl.querySelectorAll('dt');
        const dds = dl.querySelectorAll('dd');
        dts.forEach((dt, i) => {
            if (!matchFinal(dt.textContent) || !dds[i]) return;
            const t = dds[i].textContent;
            set('payment_usd', pickUsd(t));
            set('payment_krw', pickKrw(t));
            set('discount_rate', pickRate(t));
        });
    });

    // 3) .tit + .price 페어
    const payScope = document.querySelector('.totalPayment, [class*="totalPayment"]') || document;
    payScope.querySelectorAll('.tit').forEach(titEl => {
        const c = titEl.cloneNode(true);
        c.querySelectorAll('.tooltipWrap, .ux_arrow, .btnTip, .contTip, .btnClose, i, em, script').forEach(n => n.remove());
        if (!matchFinal(c.textContent.trim())) return;
        let priceEl = titEl.nextElementSibling;
        if (!priceEl || !priceEl.classList.contains('price')) {
            const p = titEl.parentElement;
            if (p) priceEl = p.querySelector(':scope > .price');
        }
        if (!priceEl) return;
        const t = priceEl.textContent;
        set('payment_usd', pickUsd(t));
        set('payment_krw', pickKrw(t));
        set('discount_rate', pickRate(t));
    });

    // 4) 상품명
    const nameSelectors = [
        '.info > a > .product', '.info .product',
        '[class*="prd_name"]', '[class*="prdName"]',
        '[class*="goods_name"]', '[class*="productName"]',
    ];
    for (const sel of nameSelectors) {
        const el = document.querySelector(sel);
        if (!el) continue;
        const txt = el.textContent.replace(/\\s+/g, ' ').trim();
        if (txt) { result.product_name = txt.substring(0, 200); break; }
    }

    // 디버그: 결제정보 못 찾은 경우
    const raw_texts = [];
    if (!result.payment_usd && !result.payment_krw) {
        document.querySelectorAll('[class*="pay"], [class*="total"], [class*="expected"]')
            .forEach(el => {
                const t = el.textContent.replace(/\\s+/g, ' ').trim().substring(0, 300);
                if (t.length > 10) raw_texts.push(t);
            });
    }
    return { ...result, raw_texts };
}"""


# ═══════════════════════════════════════════════════════════════════
# 테스트 단계
# ═══════════════════════════════════════════════════════════════════

def test_login(page: Page, context: BrowserContext, login_id: str, login_pwd: str) -> bool:
    """Step 1: 로그인 테스트 (두 서브도메인 모두 로그인)."""
    log("=" * 60)
    log("STEP 1: 로그인 테스트")
    log("=" * 60)

    # 1-1. kor.lottedfs.com 로그인
    log("--- 1-1. kor.lottedfs.com 로그인 ---")
    ok = do_login(page, login_id, login_pwd)
    if not ok:
        return False

    broaden_cookies(context)
    save_cookies(context, COOKIE_FILE)

    # 1-2. kor.lps.lottedfs.com 로그인 (주문서/성인인증 도메인)
    log("--- 1-2. kor.lps.lottedfs.com 로그인 ---")
    lps_login_url = "https://kor.lps.lottedfs.com/kr/member/login"
    log(f"  lps 로그인 페이지 이동: {lps_login_url}")
    resp = page.goto(lps_login_url, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(3000)

    lps_ok = do_login_on_current_page(page, login_id, login_pwd)
    if lps_ok:
        broaden_cookies(context)
        save_cookies(context, COOKIE_FILE)
        log("  양쪽 도메인 로그인 완료")
    else:
        log("  [WARN] lps 서브도메인 로그인 실패 - 주문서 접근 시 문제 가능")

    dump_cookies_by_domain(context)
    return ok


def test_cookie_sharing(page: Page, context: BrowserContext) -> bool:
    """Step 2: 서브도메인 간 쿠키 공유 확인."""
    log("=" * 60)
    log("STEP 2: 서브도메인 쿠키 공유 테스트")
    log("=" * 60)

    results = {}
    for name, domain in DOMAINS.items():
        url = f"https://{domain}"
        log(f"  [{name}] {url} 접속 중...")
        try:
            resp = page.goto(url, wait_until="domcontentloaded", timeout=30000)
            status = resp.status if resp else "N/A"
            current = page.url[:100]

            # 로그인 상태 확인: 비밀번호 입력란이 있으면 미로그인
            has_pwd = page.evaluate(
                "() => !!document.querySelector('input[type=\"password\"]')"
            )
            # 페이지 내용 타입 확인 (image/png 소프트 차단 감지)
            content_type = ""
            if resp:
                content_type = resp.headers.get("content-type", "")

            logged_in = not has_pwd
            is_image = content_type.startswith("image/")

            status_str = "로그인됨" if logged_in else "미로그인"
            if is_image:
                status_str = f"소프트 차단 (content-type: {content_type})"

            log(f"    HTTP {status} | {status_str} | → {current}")
            results[name] = {
                "status": status,
                "logged_in": logged_in,
                "is_image": is_image,
                "url": current,
            }
            page.wait_for_timeout(2000)
        except Exception as e:
            log(f"    오류: {e}")
            results[name] = {"status": "error", "error": str(e)}

    # 결과 요약
    log("\n─── 쿠키 공유 결과 ───")
    all_ok = True
    for name, r in results.items():
        ok = r.get("logged_in", False) and not r.get("is_image", False)
        mark = "OK" if ok else "FAIL"
        log(f"  [{mark}] {name}: {r}")
        if not ok:
            all_ok = False

    if not all_ok:
        log("\n[!] 일부 도메인에서 쿠키 공유 실패 또는 소프트 차단 감지")
        log("    → 각 서브도메인별 개별 로그인이 필요할 수 있습니다")

    return all_ok


def test_detail(page: Page, context: BrowserContext, product_code: str) -> bool:
    """Step 3: 상품상세 페이지 접근 테스트."""
    log("=" * 60)
    log(f"STEP 3: 상품상세 접근 테스트 (코드: {product_code})")
    log("=" * 60)

    url = URLS["detail_template"].format(prdNo=product_code)
    log(f"  상품상세 URL: {url}")

    resp = page.goto(url, wait_until="domcontentloaded", timeout=30000)
    status = resp.status if resp else "N/A"
    log(f"  HTTP {status} → {page.url[:100]}")

    if resp and resp.headers.get("content-type", "").startswith("image/"):
        log("  [FAIL] 소프트 차단: 응답이 이미지입니다 (headless 감지)")
        return False

    page.wait_for_timeout(3000)

    # 성인인증 리다이렉트 감지 → lps 서브도메인 로그인 후 재시도
    if "member/login" in page.url and "adultYn=Y" in page.url:
        log("  성인인증 로그인 필요 - lps 서브도메인 로그인 시도")
        # 현재 페이지가 lps 로그인 페이지이므로 여기서 로그인
        # (login_id/pwd는 test_detail 시그니처에 없으므로 아래 test_full_order에서 처리)
        return False

    # 상품명 확인
    product_name = page.evaluate("""() => {
        const og = document.querySelector('meta[property="og:title"]');
        if (og) return og.getAttribute('content') || '';
        return document.title || '';
    }""")
    log(f"  상품명: {product_name}")

    # 바로구매 버튼 존재 확인
    has_buy_btn = page.evaluate("""() => {
        const btns = [...document.querySelectorAll('a, button')];
        return btns.some(b => {
            const t = (b.textContent || '').replace(/\\s+/g, '').trim();
            return /바로구매|주문하기|구매하기/.test(t);
        });
    }""")
    log(f"  바로구매 버튼: {'있음' if has_buy_btn else '없음'}")

    if not product_name or not has_buy_btn:
        # 디버그: 페이지 본문 앞부분 + content-type + title 출력
        debug_info = page.evaluate("""() => {
            return {
                title: document.title,
                url: location.href,
                bodyLen: (document.body?.innerText || '').length,
                bodyHead: (document.body?.innerText || '').substring(0, 300),
            };
        }""")
        log(f"  [DEBUG] title: {debug_info.get('title', '')}")
        log(f"  [DEBUG] bodyLen: {debug_info.get('bodyLen', 0)}")
        log(f"  [DEBUG] bodyHead: {debug_info.get('bodyHead', '')[:200]}")

    return bool(product_name and has_buy_btn)


def test_full_order(
    page: Page, context: BrowserContext,
    login_id: str, login_pwd: str, product_code: str,
) -> dict:
    """Step 4: 전체 주문서 수집 흐름."""
    log("=" * 60)
    log(f"STEP 4: 전체 주문서 흐름 (코드: {product_code})")
    log("=" * 60)

    detail_url = URLS["detail_template"].format(prdNo=product_code)

    # 4-1. 상품상세 이동
    log(f"  상품상세 이동: {detail_url[:100]}")
    resp = page.goto(detail_url, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(3000)

    # headless 감지 체크
    if resp and resp.headers.get("content-type", "").startswith("image/"):
        log("  [FAIL] 소프트 차단 감지")
        return {"error": "soft_blocked"}

    # 성인인증 상품 감지 → lps 서브도메인 로그인 후 재시도
    if "member/login" in page.url and "adultYn=Y" in page.url:
        log("  성인인증 리다이렉트 감지 - lps 서브도메인 로그인 시도")
        lps_login_ok = do_login_on_current_page(page, login_id, login_pwd)
        if not lps_login_ok:
            log("  [FAIL] lps 서브도메인 로그인 실패")
            return {"error": "lps_login_failed"}
        broaden_cookies(context)
        save_cookies(context, COOKIE_FILE)
        # 로그인 성공 후 상품상세 재접근
        log(f"  상품상세 재접근: {detail_url[:100]}")
        resp = page.goto(detail_url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)
        if "member/login" in page.url:
            log("  [FAIL] 로그인 후에도 상품상세 접근 불가")
            return {"error": "adult_login_redirect_loop"}

    # 인간형 행동
    page.wait_for_timeout(2000)
    page.evaluate("window.scrollTo(0, 300)")
    page.wait_for_timeout(1000)

    # 4-2. 바로구매 클릭
    log("  바로구매 버튼 클릭...")

    # 신규 창(팝업) 리스너 등록
    popup_holder = {"page": None}
    def on_page(p):
        if popup_holder["page"] is None:
            popup_holder["page"] = p
    context.on("page", on_page)

    try:
        click_result = page.evaluate(JS_CLICK_ORDER_BUTTON)
        log(f"  클릭 결과: {click_result}")

        if not click_result.get("ok"):
            log("  [FAIL] 주문 버튼을 찾을 수 없습니다")
            return {"error": "no_order_button"}

        # 팝업 또는 URL 변경 대기
        deadline = time.time() + 8
        while time.time() < deadline:
            if popup_holder["page"] is not None:
                break
            if "newOrder" in page.url:
                break
            page.wait_for_timeout(300)

        # 4-3. 로그인 팝업 처리
        popup = popup_holder["page"]
        if popup and not popup.is_closed():
            log(f"  로그인 팝업 감지: {popup.url[:100]}")

            # 팝업에도 stealth 적용
            if _stealth:
                _stealth.apply_stealth_sync(popup)

            try:
                popup.wait_for_load_state("domcontentloaded", timeout=10000)
            except Exception:
                pass
            popup.wait_for_timeout(2000)

            has_pwd = popup.evaluate(
                "() => !!document.querySelector('input[type=\"password\"]')"
            )
            if has_pwd:
                log("  팝업에서 로그인 수행 (do_login_on_current_page)...")
                popup_login_ok = do_login_on_current_page(
                    popup, login_id, login_pwd,
                )
                if popup_login_ok:
                    log("  팝업 로그인 성공")
                else:
                    log("  팝업 로그인 실패")

                # 팝업 닫힘 대기
                if not popup.is_closed():
                    try:
                        popup.wait_for_event("close", timeout=15000)
                        log("  팝업 자동 종료 확인")
                    except Exception:
                        log("  팝업 미종료 (계속 진행)")

            # 팝업 종료 후 쿠키 확장
            broaden_cookies(context)

        # 4-4. 주문서 도달 확인
        page.wait_for_timeout(3000)

        # cartPopup 모달 처리
        if "newOrder" not in page.url:
            log("  cartPopup 모달 확인...")
            page.wait_for_timeout(1500)
            modal_result = page.evaluate(JS_CLICK_POPUP_CONFIRM)
            log(f"  모달 결과: {modal_result}")
            if modal_result.get("ok"):
                try:
                    page.wait_for_url("**newOrder**", timeout=15000)
                except Exception:
                    pass

        log(f"  현재 URL: {page.url[:120]}")

        if "newOrder" not in page.url:
            log("  [FAIL] 주문서 페이지에 도달하지 못했습니다")
            # 현재 페이지 스냅샷
            body_text = page.evaluate(
                "() => document.body ? document.body.innerText.substring(0, 500) : ''"
            )
            log(f"  페이지 내용: {body_text[:200]}")
            return {"error": "order_page_not_reached", "url": page.url}

        # 4-5. 결제정보 추출
        log("  결제정보 추출 중...")
        page.wait_for_timeout(2000)
        try:
            page.wait_for_load_state("domcontentloaded", timeout=10000)
        except Exception:
            pass

        data = page.evaluate(JS_EXTRACT_ORDER_PAYMENT)
        log(f"  추출 결과:")
        log(f"    상품명     : {data.get('product_name', '(없음)')}")
        log(f"    결제금액(USD): {data.get('payment_usd', '(없음)')}")
        log(f"    결제금액(KRW): {data.get('payment_krw', '(없음)')}")
        log(f"    할인율      : {data.get('discount_rate', '(없음)')}")

        if data.get("raw_texts"):
            log("  [DEBUG] 결제정보 미추출 — raw_texts:")
            for rt in data["raw_texts"][:3]:
                log(f"    {rt[:150]}")

        return {
            "product_code": product_code,
            **data,
            "order_url": page.url,
        }

    finally:
        try:
            context.remove_listener("page", on_page)
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════
# 메인
# ═══════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="롯데면세점 주문서 Headless 테스트",
    )
    parser.add_argument("--login-id", required=True, help="로그인 ID")
    parser.add_argument("--login-pwd", required=True, help="로그인 비밀번호")
    parser.add_argument(
        "--product-code", default="20000842408",
        help="테스트 상품 코드 (기본: 20000842408)",
    )
    parser.add_argument(
        "--step", default="order",
        choices=["login", "cookie", "detail", "order"],
        help="테스트 단계 (기본: order = 전체)",
    )
    parser.add_argument(
        "--headed", action="store_true",
        help="Headed 모드 (디버깅용, 브라우저 화면 표시)",
    )
    args = parser.parse_args()

    headless = not args.headed
    mode_str = "Headless" if headless else "Headed"

    log(f"{'=' * 60}")
    log(f"롯데면세점 주문서 수집 테스트 ({mode_str})")
    log(f"  단계: {args.step}")
    log(f"  상품코드: {args.product_code}")
    log(f"{'=' * 60}")

    with sync_playwright() as pw:
        browser, context, page = create_browser(pw, headless=headless)

        try:
            # Step 1: 로그인
            login_ok = test_login(page, context, args.login_id, args.login_pwd)
            if not login_ok:
                log("[FAIL] 로그인 실패 — 테스트 중단")
                return

            if args.step == "login":
                log("\n[DONE] 로그인 테스트 완료")
                return

            # Step 2: 쿠키 공유 (cookie/detail step에서만 실행, order에서는 건너뜀)
            if args.step in ("cookie", "detail"):
                cookie_ok = test_cookie_sharing(page, context)
                if args.step == "cookie":
                    log(f"\n[DONE] 쿠키 공유 테스트 완료 - {'성공' if cookie_ok else '실패'}")
                    return

            # Step 3: 상품상세 (detail step에서만 실행)
            if args.step == "detail":
                detail_ok = test_detail(page, context, args.product_code)
                log(f"\n[DONE] 상품상세 테스트 완료 - {'성공' if detail_ok else '실패'}")
                return

            # Step 4: 전체 주문서 흐름
            if args.step == "order":
                result = test_full_order(
                    page, context,
                    args.login_id, args.login_pwd, args.product_code,
                )

                # 결과 저장
                out_dir = os.path.join(os.path.dirname(__file__), "output", "_test_order")
                os.makedirs(out_dir, exist_ok=True)
                out_path = os.path.join(out_dir, "test_result.json")
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
                log(f"\n결과 저장: {out_path}")

                has_payment = bool(
                    result.get("payment_usd") or result.get("payment_krw")
                )
                log(f"\n[{'DONE' if has_payment else 'FAIL'}] "
                    f"주문서 수집 {'성공' if has_payment else '실패'}")

        finally:
            save_cookies(context, COOKIE_FILE)
            browser.close()
            log("브라우저 종료")


if __name__ == "__main__":
    main()
