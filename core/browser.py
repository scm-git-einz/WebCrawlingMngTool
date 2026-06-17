"""
Playwright Stealth 브라우저 관리 모듈

설정 주입 방식: 브라우저 설정을 파라미터로 받는다.
특정 사이트에 의존하지 않는 범용 모듈.

쿠키 영속화:
  create() 호출 시 cookie_domain 을 지정하면
  해당 도메인의 쿠키를 자동으로 로드/저장한다.
"""
import json
import os
from urllib.parse import urlparse

from playwright.sync_api import (
    sync_playwright, Playwright, Browser, BrowserContext, Page,
)
from playwright_stealth import Stealth


# ─── Stealth 인스턴스 (한 번만 생성) ──────────────────────────────
_stealth = Stealth(
    navigator_languages_override=("ko-KR", "ko"),
    navigator_platform_override="Win32",
)

# ─── 쿠키 저장 경로 ─────────────────────────────────────────────
_COOKIE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "cookies",
)

# ─── 기본 브라우저 설정 ───────────────────────────────────────────
DEFAULT_BROWSER_CONFIG = {
    "user_agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "viewport": {"width": 1920, "height": 1080},
    "headers": {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Sec-Ch-Ua": '"Chromium";v="125", "Google Chrome";v="125", "Not=A?Brand";v="8"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    },
    "allowed_domains": [],
    "blocked_resource_types": ["font", "media"],
    "timeout": 30000,
}


class BrowserManager:
    """Stealth 브라우저 세션 관리"""

    def __init__(self):
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._config: dict = {}
        self._cookie_domain: str | None = None
        self._current_proxy: dict | None = None

    def create(
        self,
        config: dict | None = None,
        cookie_domain: str | None = None,
        headless: bool = True,
        proxy: dict | None = None,
    ) -> Page:
        """
        Stealth 브라우저를 시작하고 새 Page 를 반환한다.

        이미 열려있으면 기존 브라우저에서 새 페이지만 생성한다.
        config 는 DB 의 platforms.browser JSON 이다.

        Args:
            config:        브라우저 설정 딕셔너리
            cookie_domain: 쿠키 영속화 도메인 (예: "brand.naver.com")
                           지정 시 이전 세션의 쿠키를 자동 로드한다.
            headless:      True=화면 없음 (기본), False=화면 표시
                           봇 차단이 강한 사이트는 False 필요
            proxy:         프록시 설정 딕셔너리 (예: {"server": "http://ip:port"})
                           지정 시 해당 프록시를 통해 접속한다.
        """
        merged = {**DEFAULT_BROWSER_CONFIG, **(config or {})}
        # headers 는 deep merge (플랫폼별 헤더가 기본 헤더를 덮어쓰지 않도록)
        if config and "headers" in config:
            merged["headers"] = {
                **DEFAULT_BROWSER_CONFIG.get("headers", {}),
                **config["headers"],
            }
        self._config = merged
        self._cookie_domain = cookie_domain
        self._current_proxy = proxy

        if self._context is not None:
            page = self._context.new_page()
            _stealth.apply_stealth_sync(page)
            return page

        mode = "Headless" if headless else "Headed"
        proxy_info = f" via {proxy['server']}" if proxy else ""
        print(f"[browser] Stealth Chromium 브라우저 시작 ({mode}{proxy_info})...")

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )

        context_kwargs = dict(
            user_agent=merged["user_agent"],
            viewport=merged["viewport"],
            extra_http_headers=merged.get("headers", {}),
            locale="ko-KR",
            timezone_id="Asia/Seoul",
        )
        if proxy:
            context_kwargs["proxy"] = proxy
            context_kwargs["ignore_https_errors"] = True

        self._context = self._browser.new_context(**context_kwargs)
        self._context.set_default_timeout(merged.get("timeout", 30000))

        # 도메인 필터링
        allowed = merged.get("allowed_domains", [])
        blocked_types = merged.get("blocked_resource_types", [])

        if allowed or blocked_types:
            def _route_handler(route):
                req = route.request
                if req.resource_type in blocked_types:
                    route.abort()
                    return
                if allowed and not _is_allowed(req.url, allowed):
                    route.abort()
                    return
                route.continue_()

            self._context.route("**/*", _route_handler)

        # 쿠키 로드 (이전 세션)
        if cookie_domain:
            self._load_cookies(cookie_domain)

        page = self._context.new_page()
        _stealth.apply_stealth_sync(page)

        print("[browser] 브라우저 준비 완료")
        return page

    def recreate_context(self, proxy: dict | None = None) -> Page:
        """프록시를 교체하여 새 컨텍스트를 생성한다. 기존 컨텍스트는 종료."""
        if self._cookie_domain:
            self.save_cookies(self._cookie_domain)

        if self._context:
            try:
                self._context.close()
            except Exception:
                pass
            self._context = None

        self._current_proxy = proxy
        proxy_info = f" via {proxy['server']}" if proxy else " (직접 연결)"
        print(f"[browser] 프록시 교체{proxy_info}")

        context_kwargs = dict(
            user_agent=self._config["user_agent"],
            viewport=self._config["viewport"],
            extra_http_headers=self._config.get("headers", {}),
            locale="ko-KR",
            timezone_id="Asia/Seoul",
        )
        if proxy:
            context_kwargs["proxy"] = proxy
            context_kwargs["ignore_https_errors"] = True

        self._context = self._browser.new_context(**context_kwargs)
        self._context.set_default_timeout(self._config.get("timeout", 30000))

        merged = self._config
        allowed = merged.get("allowed_domains", [])
        blocked_types = merged.get("blocked_resource_types", [])
        if allowed or blocked_types:
            def _route_handler(route):
                req = route.request
                if req.resource_type in blocked_types:
                    route.abort()
                    return
                if allowed and not _is_allowed(req.url, allowed):
                    route.abort()
                    return
                route.continue_()
            self._context.route("**/*", _route_handler)

        if self._cookie_domain:
            self._load_cookies(self._cookie_domain)

        page = self._context.new_page()
        _stealth.apply_stealth_sync(page)
        print("[browser] 새 컨텍스트 준비 완료")
        return page

    def save_cookies(self, domain: str | None = None):
        """현재 브라우저 컨텍스트의 쿠키를 파일에 저장한다."""
        domain = domain or self._cookie_domain
        if not domain or not self._context:
            return

        try:
            cookies = self._context.cookies()
            if not cookies:
                return

            os.makedirs(_COOKIE_DIR, exist_ok=True)
            cookie_path = _cookie_file_path(domain)

            with open(cookie_path, "w", encoding="utf-8") as f:
                json.dump(cookies, f, ensure_ascii=False, indent=2)

            print(f"[browser] 쿠키 저장 ({len(cookies)}개): {domain}")
        except Exception as e:
            print(f"[browser] 쿠키 저장 실패: {e}")

    def _load_cookies(self, domain: str):
        """저장된 쿠키 파일을 브라우저 컨텍스트에 로드한다."""
        cookie_path = _cookie_file_path(domain)
        if not os.path.exists(cookie_path):
            return

        try:
            with open(cookie_path, "r", encoding="utf-8") as f:
                cookies = json.load(f)

            if cookies and self._context:
                self._context.add_cookies(cookies)
                print(f"[browser] 쿠키 로드 ({len(cookies)}개): {domain}")
        except Exception as e:
            print(f"[browser] 쿠키 로드 실패: {e}")

    def close(self):
        """브라우저 세션을 완전히 종료한다. 쿠키를 자동 저장."""
        # 종료 전 쿠키 저장
        if self._cookie_domain:
            self.save_cookies(self._cookie_domain)

        try:
            if self._context:
                self._context.close()
            if self._browser:
                self._browser.close()
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass
        finally:
            self._context = None
            self._browser = None
            self._playwright = None
        print("[browser] 브라우저 종료")


# ─── 유틸 ────────────────────────────────────────────────────────

def _is_allowed(url: str, allowed_domains: list[str]) -> bool:
    """URL 의 호스트가 허용 도메인 목록에 포함되는지 판별한다."""
    try:
        host = urlparse(url).hostname or ""
        return any(
            host == d or host.endswith(f".{d}")
            for d in allowed_domains
        )
    except Exception:
        return False


def _cookie_file_path(domain: str) -> str:
    """도메인으로 쿠키 파일 경로를 반환한다."""
    safe_name = domain.replace(".", "_").replace("/", "_")
    return os.path.join(_COOKIE_DIR, f"{safe_name}.json")
