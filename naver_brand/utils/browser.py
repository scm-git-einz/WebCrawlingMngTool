"""
Playwright Stealth 브라우저 설정 모듈

- playwright-stealth 로 WebDriver 플래그 제거
- User-Agent, HTTP 헤더 설정
- 허용 도메인 외 요청 차단 (광고·트래커 제거, 속도 향상)
"""
import sys
import os
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright, Playwright, Browser, BrowserContext, Page
from playwright_stealth import Stealth

# 패키지 루트를 sys.path 에 추가하여 config 임포트 가능하게 함
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config.settings import (
    USER_AGENT, COMMON_HEADERS, VIEWPORT,
    ALLOWED_DOMAINS, BLOCKED_RESOURCE_TYPES, PAGE_LOAD_TIMEOUT,
)

# ─── Stealth 인스턴스 (한 번만 생성) ──────────────────────────────
_stealth = Stealth(
    navigator_languages_override=("ko-KR", "ko"),
    navigator_platform_override="Win32",
)

# ─── 모듈 레벨 상태 (단일 브라우저 세션 유지) ─────────────────────
_playwright: Playwright | None = None
_browser: Browser | None = None
_context: BrowserContext | None = None


def _should_block(url: str) -> bool:
    """허용 도메인 목록에 없는 URL 인지 판별"""
    try:
        host = urlparse(url).hostname or ""
        return not any(host == d or host.endswith(f".{d}") for d in ALLOWED_DOMAINS)
    except Exception:
        return True


def create_stealth_browser() -> tuple[BrowserContext, Page]:
    """
    Stealth 모드 Chromium 브라우저를 실행하고 (context, page) 를 반환한다.

    - 동일 세션 내에서 여러 번 호출해도 브라우저는 1개만 유지
    - 외부 도메인 요청 차단
    - stealth_sync 로 봇 감지 우회
    """
    global _playwright, _browser, _context

    if _context is not None:
        page = _context.new_page()
        _stealth.apply_stealth_sync(page)
        return _context, page

    print("[browser] Stealth Chromium 브라우저 시작...")

    _playwright = sync_playwright().start()
    _browser = _playwright.chromium.launch(
        headless=True,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
        ],
    )

    _context = _browser.new_context(
        user_agent=USER_AGENT,
        viewport=VIEWPORT,
        extra_http_headers=COMMON_HEADERS,
        locale="ko-KR",
        timezone_id="Asia/Seoul",
    )
    _context.set_default_timeout(PAGE_LOAD_TIMEOUT)

    # 외부 도메인 요청 차단 (광고, 트래커 등)
    def _route_handler(route):
        req = route.request
        if req.resource_type in BLOCKED_RESOURCE_TYPES:
            route.abort()
        elif _should_block(req.url):
            route.abort()
        else:
            route.continue_()

    _context.route("**/*", _route_handler)

    page = _context.new_page()
    _stealth.apply_stealth_sync(page)

    print("[browser] 브라우저 준비 완료")
    return _context, page


def close_browser():
    """브라우저 세션을 완전히 종료한다."""
    global _playwright, _browser, _context
    try:
        if _context:
            _context.close()
        if _browser:
            _browser.close()
        if _playwright:
            _playwright.stop()
    except Exception:
        pass
    finally:
        _context = None
        _browser = None
        _playwright = None
    print("[browser] 브라우저 종료")
