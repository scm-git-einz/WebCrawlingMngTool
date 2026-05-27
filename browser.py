"""
브라우저 설정 모듈 - 봇 감지 우회 (Stealth + 실제 브라우저 핑거프린트)

LLM 판단: Playwright 사용
- 롯데면세점은 SPA(jQuery 기반 AJAX) 구조
- 데스크톱 도메인(kor.lottedfs.com)은 CloudFront가 점검 이미지 반환
- 모바일 도메인(m.kor.lottedfs.com)으로 접근 시 전체 기능 사용 가능
- Incapsula WAF가 적용되어 있어 stealth 모드 필수
"""

import asyncio
import random
from playwright.async_api import async_playwright, BrowserContext, Page
from playwright_stealth import Stealth

# ─── 봇 감지 우회 설정 ───────────────────────────────────────────────

# 실제 iPhone Safari 브라우저 핑거프린트
MOBILE_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5_1 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/17.5 Mobile/15E148 Safari/604.1"
)

# 실제 Chrome 데스크톱 브라우저 핑거프린트
DESKTOP_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

# 공통 HTTP 헤더
COMMON_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

# 허용 도메인 (롯데면세점만)
ALLOWED_DOMAINS = [
    "lottedfs.com",
    "m.lottedfs.com",
    "kor.lottedfs.com",
    "m.kor.lottedfs.com",
    "static.lottedfs.com",
]

# ─── 도메인 필터링 ───────────────────────────────────────────────────


def is_allowed_url(url: str) -> bool:
    """허용된 롯데면세점 도메인인지 확인"""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    hostname = parsed.hostname or ""
    return any(hostname.endswith(d) for d in ALLOWED_DOMAINS)


# ─── 브라우저 생성 ───────────────────────────────────────────────────


async def create_stealth_browser(
    headless: bool = True,
    mobile: bool = True,
) -> tuple:
    """
    Stealth 모드 브라우저 생성

    Returns:
        (playwright, browser, context, page) 튜플
    """
    pw = await async_playwright().start()

    # Chromium 실행 옵션
    launch_args = [
        "--disable-blink-features=AutomationControlled",
        "--disable-features=IsolateOrigins,site-per-process",
        "--disable-infobars",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-dev-shm-usage",
    ]

    browser = await pw.chromium.launch(
        headless=headless,
        args=launch_args,
    )

    # 브라우저 컨텍스트 설정
    context_opts = {
        "locale": "ko-KR",
        "timezone_id": "Asia/Seoul",
        "color_scheme": "light",
        "extra_http_headers": COMMON_HEADERS,
    }

    if mobile:
        context_opts.update({
            "user_agent": MOBILE_USER_AGENT,
            "viewport": {"width": 390, "height": 844},
            "device_scale_factor": 3,
            "is_mobile": True,
            "has_touch": True,
        })
    else:
        context_opts.update({
            "user_agent": DESKTOP_USER_AGENT,
            "viewport": {"width": 1920, "height": 1080},
            "device_scale_factor": 1,
            "is_mobile": False,
        })

    context = await browser.new_context(**context_opts)

    # 도메인 외부 요청 차단 (광고, 트래커 등)
    await context.route("**/*", _route_handler)

    # playwright-stealth 적용 (WebDriver 플래그 제거, navigator 속성 위장 등)
    stealth = Stealth(
        navigator_webdriver=True,
        navigator_plugins=True,
        navigator_languages=True,
        navigator_user_agent=True,
        navigator_vendor=True,
        chrome_runtime=True,
        navigator_languages_override=("ko-KR", "ko"),
    )
    await stealth.apply_stealth_async(context)

    page = await context.new_page()

    return pw, browser, context, page


async def _route_handler(route):
    """
    요청 라우팅 - 불필요한 리소스만 차단 (속도 향상)

    주의: Incapsula WAF 챌린지 스크립트는 차단하면 안 됨.
    외부 도메인 스크립트 중 보안 챌린지 관련은 허용해야 페이지가 정상 로드됨.
    """
    url = route.request.url
    resource_type = route.request.resource_type

    # 이미지, 폰트, 미디어만 차단 (속도 향상, 기능에 영향 없음)
    if resource_type in ("image", "font", "media"):
        await route.abort()
        return

    # 광고/분석 도메인만 선별 차단 (WAF 스크립트는 허용)
    blocked_domains = [
        "google-analytics.com",
        "googletagmanager.com",
        "doubleclick.net",
        "facebook.net",
        "fbcdn.net",
        "ad.lottedfs.com",
    ]
    from urllib.parse import urlparse
    hostname = urlparse(url).hostname or ""
    if any(hostname.endswith(d) for d in blocked_domains):
        await route.abort()
        return

    # 나머지 요청은 모두 허용 (Incapsula, jQuery CDN 등)
    await route.continue_()


# ─── 사람처럼 행동하는 유틸리티 ──────────────────────────────────────


async def human_delay(min_sec: float = 0.5, max_sec: float = 2.0):
    """사람처럼 랜덤 대기"""
    await asyncio.sleep(random.uniform(min_sec, max_sec))


async def human_scroll(page: Page, total_scrolls: int = 10, scroll_px: int = 400):
    """사람처럼 스크롤 - 랜덤 속도/간격"""
    for i in range(total_scrolls):
        px = scroll_px + random.randint(-100, 150)
        await page.evaluate(f"window.scrollBy(0, {px})")
        await asyncio.sleep(random.uniform(0.3, 1.2))

    # 맨 위로 다시 올라갔다가 내려오는 동작 (사람처럼)
    if random.random() > 0.7:
        await page.evaluate("window.scrollTo(0, 0)")
        await asyncio.sleep(random.uniform(0.5, 1.0))
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 3)")


async def wait_for_content(page: Page, selector: str, timeout: int = 15000):
    """특정 요소가 로드될 때까지 대기"""
    try:
        await page.wait_for_selector(selector, timeout=timeout)
        return True
    except Exception:
        return False
