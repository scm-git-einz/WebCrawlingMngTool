"""
에이전트 추상 베이스 클래스

모든 수집 에이전트(상품, 뉴스 등)가 구현해야 할 인터페이스를 정의한다.
공통 인프라(DB, 브라우저, 네트워크 인터셉터)를 제공하고,
각 에이전트는 도메인별 분석/수집 로직만 구현하면 된다.

봇 차단 대응:
  - 인간형 행동 시뮬레이션 (가변 딜레이, 자연스러운 스크롤)
  - 적응형 백오프 (429/503 감지 시 장시간 대기)
  - 도메인별 레이트 리밋 상태 추적
"""
import math
import random
import time
from abc import ABC, abstractmethod
from urllib.parse import urlparse

from core.db import CrawlDB
from core.browser import BrowserManager
from core.proxy_manager import get_proxy_manager, ProxyManager


# ─── 공통 수집 설정 기본값 ────────────────────────────────────────
DEFAULT_SETTINGS = {
    "delay_min": 1.0,
    "delay_max": 2.0,
    "page_wait_ms": 3000,
    "initial_wait_ms": 5000,
}

# ─── 적응형 백오프 설정 ──────────────────────────────────────────
ADAPTIVE_BACKOFF = {
    # 429/503 첫 발생 시 기본 대기 (초)
    "base_wait_secs": 120,
    # 최대 대기 (초) — 10분
    "max_wait_secs": 600,
    # 지수 백오프 배수
    "multiplier": 2.0,
    # 지터 범위 (대기 시간의 ±%)
    "jitter_pct": 0.3,
    # 최대 재시도 횟수
    "max_retries": 5,
}

# ─── 인간형 행동 설정 ────────────────────────────────────────────
HUMAN_BEHAVIOR = {
    # 페이지 이동 간 딜레이 (초): 정규분포 평균/표준편차
    "nav_delay_mean": 3.5,
    "nav_delay_std": 1.5,
    "nav_delay_min": 1.5,
    "nav_delay_max": 8.0,
    # 페이지 로드 후 체류 시간 (초)
    "dwell_time_min": 2.0,
    "dwell_time_max": 5.0,
    # 스크롤 동작
    "scroll_pause_min": 800,   # ms
    "scroll_pause_max": 2500,  # ms
    "scroll_steps": 3,         # 스크롤 단계 수
}

# ─── 도메인별 레이트 리밋 상태 (프로세스 수준 캐시) ────────────────
_rate_limit_state: dict[str, dict] = {}


class BaseAgent(ABC):
    """
    수집 에이전트 추상 베이스.

    서브클래스는 다음을 구현해야 한다:
      - agent_type (property): 에이전트 유형 식별자 (예: "product", "news")
      - run_site(site_id): 단일 사이트 수집 실행
    """

    def __init__(self, db: CrawlDB | None = None):
        self.db = db or CrawlDB()
        self.browser_mgr = BrowserManager()
        self.page = None
        self._last_url: str | None = None
        self._proxy_mgr: ProxyManager | None = None
        self._use_proxy: bool = False
        self._current_proxy: dict | None = None
        self._proxy_fail_count: int = 0
        # 연속 프록시 실패 시 교체 임계값
        self._PROXY_ROTATE_THRESHOLD = 2
        # 소프트 차단 캐시 (중복 DOM 검사 방지)
        self._last_soft_block_url: str | None = None
        self._last_soft_block_result: bool = False

    # ─── 에이전트 식별 ────────────────────────────────────────────

    @property
    @abstractmethod
    def agent_type(self) -> str:
        """에이전트 유형 식별자 (예: 'product', 'news')"""
        ...

    # ─── 공개 메서드 ──────────────────────────────────────────────

    def run_all(self):
        """이 에이전트 타입에 해당하는 모든 활성 사이트를 수집한다."""
        sites = self.db.get_active_sites_by_agent(self.agent_type)
        if not sites:
            print(f"[{self.agent_type}] 활성 사이트가 없습니다")
            return

        print(f"[{self.agent_type}] {len(sites)}개 사이트 수집 시작")
        for i, site in enumerate(sites, 1):
            print(f"\n{'='*60}")
            print(f"  [{i}/{len(sites)}] {site['site_name']}")
            print(f"  URL: {site['site_url']}")
            print(f"{'='*60}")
            self.run_site(site["id"])

        print(f"\n[{self.agent_type}] 전체 수집 완료")

    @abstractmethod
    def run_site(self, site_id: int):
        """단일 사이트 수집을 실행한다."""
        ...

    # ─── crawl_config ────────────────────────────────────────────

    def get_crawl_config(self, site: dict) -> dict:
        """
        사이트의 crawl_config 를 파싱하여 반환한다.

        각 에이전트는 _normalize_config()를 통해
        UI 설정 필드를 Agent 내부 필드로 변환한다.

        UI → Agent 변환 예시 (ProductAgent):
          crawl_mode='single'              → 단일 매장 모드
          crawl_mode='domain'              → 도메인 전체 모드
          product_limit_type='all'         → collect_details=True, max_detail_pages=0
          product_limit_type='n', count=20 → collect_details=True, max_detail_pages=20
        """
        import json
        raw = site.get("crawl_config", "{}")
        try:
            return json.loads(raw) if isinstance(raw, str) else (raw or {})
        except (json.JSONDecodeError, TypeError):
            return {}

    # ═══════════════════════════════════════════════════════════════
    # 프록시 로테이션
    # ═══════════════════════════════════════════════════════════════

    def enable_proxy(self, proxy_mgr: ProxyManager | None = None):
        """프록시 로테이션을 활성화한다."""
        self._use_proxy = True
        self._proxy_mgr = proxy_mgr or get_proxy_manager()
        count = self._proxy_mgr.available_count
        print(f"[{self.agent_type}] 프록시 로테이션 활성화 (사용 가능: {count}개)")

    def _get_initial_proxy(self) -> dict | None:
        """브라우저 시작용 초기 프록시를 반환한다."""
        if not self._use_proxy or not self._proxy_mgr:
            return None
        proxy = self._proxy_mgr.get_next()
        if proxy:
            self._current_proxy = proxy
            print(f"[{self.agent_type}] 초기 프록시: {proxy['server']}")
        return proxy

    def _rotate_proxy(self) -> bool:
        """프록시를 교체하고 브라우저 컨텍스트를 재생성한다.

        Returns:
            True=교체 성공, False=사용 가능한 프록시 없음
        """
        if not self._use_proxy or not self._proxy_mgr:
            return False

        old_server = self._current_proxy.get("server") if self._current_proxy else None
        new_proxy = self._proxy_mgr.rotate_on_block(old_server)
        if not new_proxy:
            print(f"[{self.agent_type}] 사용 가능한 프록시가 없습니다")
            return False

        self._current_proxy = new_proxy
        self._proxy_fail_count = 0

        try:
            self.page = self.browser_mgr.recreate_context(proxy=new_proxy)
            print(f"[{self.agent_type}] 프록시 교체 완료: {new_proxy['server']}")
            return True
        except Exception as e:
            print(f"[{self.agent_type}] 프록시 교체 실패: {e}")
            return False

    def _create_page(self, cookie_domain: str | None = None, headless: bool = True, **kwargs) -> "Page":
        """프록시 설정을 포함하여 브라우저 페이지를 생성한다.

        에이전트에서 browser_mgr.create() 대신 이 메서드를 사용하면
        프록시가 자동으로 적용된다.
        """
        proxy = self._get_initial_proxy()
        page = self.browser_mgr.create(
            cookie_domain=cookie_domain,
            headless=headless,
            proxy=proxy,
            **kwargs,
        )
        self.page = page
        return page

    # ═══════════════════════════════════════════════════════════════
    # A. 적응형 백오프 — 안전한 페이지 이동
    # ═══════════════════════════════════════════════════════════════

    def _safe_goto(
        self, url: str,
        wait_until: str = "domcontentloaded",
        timeout: int = 60000,
        max_retries: int | None = None,
    ):
        """
        page.goto() 래퍼: 429/503 응답 시 적응형 지수 백오프 재시도.

        기존 로직 대비 변경 사항:
          - 429/503 시 2분~10분 대기 (기존 15~45초)
          - 지수 백오프 + 랜덤 지터로 패턴 회피
          - 도메인별 레이트 리밋 이력 추적
          - 성공 시 Referer 체인 갱신
        """
        if max_retries is None:
            max_retries = ADAPTIVE_BACKOFF["max_retries"]

        domain = _extract_domain(url)

        # 도메인이 최근에 429를 받은 적 있으면 선제적 대기
        self._preemptive_wait(domain)

        last_resp = None
        for attempt in range(max_retries):
            try:
                # Referer 헤더 설정 (자연스러운 내비게이션)
                if self._last_url:
                    try:
                        self.page.set_extra_http_headers({
                            "Referer": self._last_url,
                        })
                    except Exception:
                        pass

                resp = self.page.goto(
                    url, wait_until=wait_until, timeout=timeout,
                )
                last_resp = resp

                if resp and resp.status in (429, 503):
                    _record_rate_limit(domain)

                    # 프록시 모드: 백오프 대신 프록시 교체 우선
                    if self._use_proxy:
                        self._proxy_fail_count += 1
                        if self._proxy_fail_count >= self._PROXY_ROTATE_THRESHOLD:
                            print(
                                f"[{self.agent_type}] HTTP {resp.status} @ "
                                f"{domain} → 프록시 교체 시도"
                            )
                            if self._rotate_proxy():
                                self._proxy_fail_count = 0
                                continue

                    wait_secs = self._calc_backoff_wait(
                        domain, attempt,
                    )
                    print(
                        f"[{self.agent_type}] HTTP {resp.status} @ "
                        f"{domain} → {wait_secs:.0f}초 대기 "
                        f"({attempt + 1}/{max_retries})"
                    )
                    time.sleep(wait_secs)
                    continue

                # 403 차단 시 프록시 교체 시도
                if resp and resp.status == 403 and self._use_proxy:
                    print(
                        f"[{self.agent_type}] HTTP 403 @ "
                        f"{domain} → 프록시 교체 시도"
                    )
                    if self._rotate_proxy():
                        continue

                # HTTP 200이지만 소프트 차단 감지 (이미지만, 빈 페이지)
                if resp and resp.status == 200:
                    soft_blocked = self._is_soft_blocked()
                    # 캐시 저장 → _is_blocked()에서 중복 DOM 검사 방지
                    self._last_soft_block_url = url
                    self._last_soft_block_result = soft_blocked

                    if soft_blocked:
                        if self._use_proxy:
                            print(
                                f"[{self.agent_type}] HTTP 200 소프트 차단 @ "
                                f"{domain} → 프록시 교체 시도"
                            )
                            if self._rotate_proxy():
                                # 캐시 무효화 (새 프록시로 재시도)
                                self._last_soft_block_url = None
                                continue
                        # 프록시 없거나 교체 불가 → 그대로 반환
                        # (에이전트의 _is_blocked()에서 캐시로 재감지 → 스킵)
                        self._last_url = url
                        return resp

                # 성공 → 레이트 리밋 상태 리셋 & Referer 갱신
                if resp and resp.status == 200 and self._use_proxy:
                    self._proxy_fail_count = 0
                _record_success(domain)
                self._last_url = url
                return resp

            except Exception as e:
                if attempt < max_retries - 1:
                    wait_secs = (attempt + 1) * 15
                    print(
                        f"[{self.agent_type}] 페이지 로딩 오류: {e} → "
                        f"{wait_secs}초 대기 후 재시도"
                    )
                    try:
                        time.sleep(wait_secs)
                    except Exception:
                        pass
                else:
                    raise

        return last_resp

    def _calc_backoff_wait(self, domain: str, attempt: int) -> float:
        """
        적응형 백오프 대기 시간을 계산한다.

        기본 120초에서 시작, 지수적으로 증가 (최대 600초).
        랜덤 지터를 추가하여 요청 패턴을 무작위화한다.
        연속 429 이력이 있으면 기본 대기도 함께 증가.
        """
        base = ADAPTIVE_BACKOFF["base_wait_secs"]
        max_wait = ADAPTIVE_BACKOFF["max_wait_secs"]
        mult = ADAPTIVE_BACKOFF["multiplier"]
        jitter_pct = ADAPTIVE_BACKOFF["jitter_pct"]

        # 도메인의 연속 429 횟수 반영
        state = _rate_limit_state.get(domain, {})
        consecutive = state.get("consecutive_429", 0)
        history_factor = 1 + (consecutive * 0.5)

        # 지수 백오프: base * mult^attempt * history_factor
        wait = base * (mult ** attempt) * history_factor
        wait = min(wait, max_wait)

        # 랜덤 지터 ±30%
        jitter = wait * jitter_pct
        wait += random.uniform(-jitter, jitter)

        return max(60.0, wait)  # 최소 60초

    def _preemptive_wait(self, domain: str):
        """
        도메인이 최근 429를 받았으면 선제적으로 짧게 대기한다.
        연속 차단 시 점점 더 오래 대기.
        """
        state = _rate_limit_state.get(domain)
        if not state:
            return

        last_429 = state.get("last_429_time", 0)
        consecutive = state.get("consecutive_429", 0)
        elapsed = time.time() - last_429

        if consecutive > 0 and elapsed < 300:
            # 최근 5분 이내에 429를 받은 적 있음
            cooldown = min(30 + consecutive * 15, 120)
            print(
                f"[{self.agent_type}] {domain}: 최근 429 이력 → "
                f"{cooldown}초 쿨다운"
            )
            time.sleep(cooldown)

    def _is_blocked(self, resp, check_soft=True) -> bool:
        """응답이 차단인지 확인한다.

        2단계 차단 감지:
          1단계: HTTP 상태 코드 (429/403/503)
          2단계: 소프트 차단 (HTTP 200이지만 빈 페이지/이미지만)

        _safe_goto()에서 이미 소프트 차단을 검사한 경우 캐시를 재활용하여
        DOM 중복 검사를 방지한다.

        소프트 차단 감지 시:
          - 프록시 모드: _safe_goto에서 프록시 교체가 이미 시도됨
          - True 반환 → 에이전트가 해당 페이지를 스킵

        Args:
            resp: HTTP 응답 객체
            check_soft: 소프트 차단도 검사할지 여부 (기본 True)
        """
        if resp is None:
            return False

        # 1단계: HTTP 상태 코드 기반 차단
        if resp.status in (429, 403, 503):
            return True

        # 2단계: HTTP 200이지만 소프트 차단 (빈 페이지, 이미지만)
        if check_soft and resp.status == 200:
            # _safe_goto에서 이미 검사한 캐시가 있으면 재활용
            current_url = None
            try:
                current_url = self.page.url if self.page else None
            except Exception:
                pass

            if (self._last_soft_block_url
                    and current_url
                    and self._last_soft_block_url == current_url):
                # 캐시 히트 — DOM 재검사 생략
                return self._last_soft_block_result

            # 캐시 미스 — DOM 검사 실행 (직접 page.goto를 호출한 경우 등)
            if self._is_soft_blocked():
                if self._use_proxy:
                    self._rotate_proxy()
                return True

        return False

    @staticmethod
    def _is_http_blocked(resp) -> bool:
        """HTTP 상태 코드만으로 차단 여부를 확인한다 (소프트 차단 미검사).

        _safe_goto 내부 등 소프트 차단 검사가 별도로 이루어지는 곳에서 사용.
        """
        if resp is None:
            return False
        return resp.status in (429, 403, 503)

    def _is_soft_blocked(self, page=None) -> bool:
        """HTTP 200이지만 실제 콘텐츠가 없는 소프트 차단을 감지한다.

        소프트 차단 패턴:
          - 이미지만 있고 텍스트/form/input이 없는 페이지
          - body 텍스트가 극히 짧은 페이지 (빈 페이지, 차단 안내 이미지)
          - 의미 있는 HTML 구조 없이 img 태그만 존재

        Returns:
            True=소프트 차단 감지, False=정상 페이지
        """
        target = page or self.page
        if not target:
            return False

        try:
            result = target.evaluate("""() => {
                const body = document.body;
                if (!body) return { blocked: true, reason: 'no_body' };

                // 텍스트 콘텐츠 길이 (공백 제거)
                const textLen = (body.innerText || '').replace(/\\s+/g, '').length;

                // 주요 인터랙티브 요소 존재 여부
                const forms = document.querySelectorAll('form');
                const inputs = document.querySelectorAll(
                    'input:not([type="hidden"]), textarea, select'
                );
                const links = document.querySelectorAll('a[href]');
                const buttons = document.querySelectorAll('button, [role="button"]');

                // 이미지 수
                const images = document.querySelectorAll('img');

                // 의미 있는 구조적 요소
                const headings = document.querySelectorAll('h1,h2,h3,h4,h5,h6');
                const paragraphs = document.querySelectorAll('p');
                const lists = document.querySelectorAll('ul,ol,dl');
                const tables = document.querySelectorAll('table');
                const navs = document.querySelectorAll('nav, [role="navigation"]');

                const hasInteractive = forms.length > 0 || inputs.length > 0;
                const hasStructure = headings.length > 0 || paragraphs.length > 0 ||
                                     lists.length > 0 || tables.length > 0 ||
                                     navs.length > 0;
                const hasNavLinks = links.length >= 3;

                // Content-Type이 image인 경우 (페이지 자체가 이미지)
                const contentType = document.contentType || '';
                if (contentType.startsWith('image/')) {
                    return { blocked: true, reason: 'image_response' };
                }

                // 판정 로직:
                // 1) 텍스트 매우 적고(< 50자) + form/input 없고 + 이미지만 있음
                if (textLen < 50 && !hasInteractive && images.length > 0) {
                    return { blocked: true, reason: 'image_only',
                             textLen, images: images.length };
                }

                // 2) 텍스트 거의 없고(< 20자) + 구조 없음 (완전 빈 페이지)
                if (textLen < 20 && !hasInteractive && !hasStructure && !hasNavLinks) {
                    return { blocked: true, reason: 'empty_page', textLen };
                }

                // 3) body 전체가 단일 이미지 (차단 안내 이미지)
                const children = body.children;
                if (children.length <= 2 && images.length >= 1 &&
                    !hasInteractive && textLen < 100) {
                    return { blocked: true, reason: 'single_image_page',
                             textLen, images: images.length };
                }

                return {
                    blocked: false,
                    textLen,
                    forms: forms.length,
                    inputs: inputs.length,
                    images: images.length,
                    links: links.length,
                };
            }""")

            if result and result.get("blocked"):
                reason = result.get("reason", "unknown")
                print(
                    f"[{self.agent_type}] 소프트 차단 감지: {reason} "
                    f"(text={result.get('textLen', 0)}자, "
                    f"img={result.get('images', 0)}개)"
                )
                return True

            return False

        except Exception as e:
            # evaluate 실패 자체가 비정상 → 차단일 가능성
            print(f"[{self.agent_type}] 소프트 차단 검사 실패: {e}")
            return False

    # ═══════════════════════════════════════════════════════════════
    # B. 인간형 행동 시뮬레이션
    # ═══════════════════════════════════════════════════════════════

    def _human_delay(self):
        """
        정규분포 기반 가변 딜레이를 적용한다.

        기존 1~2초 균일 분포 대신, 평균 3.5초의 정규분포를 사용.
        사람의 실제 페이지 전환 간격에 가까운 분포.
        """
        mean = HUMAN_BEHAVIOR["nav_delay_mean"]
        std = HUMAN_BEHAVIOR["nav_delay_std"]
        delay = random.gauss(mean, std)
        delay = max(
            HUMAN_BEHAVIOR["nav_delay_min"],
            min(delay, HUMAN_BEHAVIOR["nav_delay_max"]),
        )
        time.sleep(delay)

    def _delay(self):
        """랜덤 딜레이를 적용한다. (인간형 행동 적용)"""
        self._human_delay()

    def _human_scroll(self, page=None):
        """
        사람처럼 자연스럽게 스크롤한다.

        일정 속도가 아닌 가변적인 스크롤 + 중간 정지 + 가끔 위로 스크롤.
        """
        target = page or self.page
        if not target:
            return

        try:
            steps = HUMAN_BEHAVIOR["scroll_steps"]
            pause_min = HUMAN_BEHAVIOR["scroll_pause_min"]
            pause_max = HUMAN_BEHAVIOR["scroll_pause_max"]

            for i in range(steps):
                # 가변적 스크롤 거리
                scroll_pct = random.uniform(0.3, 0.8)
                target.evaluate(
                    f"window.scrollBy(0, window.innerHeight * {scroll_pct})"
                )

                # 가변 대기 (사람은 스크롤 후 잠시 읽는다)
                pause = random.randint(pause_min, pause_max)
                target.wait_for_timeout(pause)

                # 가끔(20%) 살짝 위로 스크롤 (사람은 돌아가서 다시 본다)
                if random.random() < 0.2:
                    back_pct = random.uniform(0.1, 0.2)
                    target.evaluate(
                        f"window.scrollBy(0, -window.innerHeight * {back_pct})"
                    )
                    target.wait_for_timeout(random.randint(500, 1000))

        except Exception:
            pass

    def _human_dwell(self, page=None):
        """
        페이지 로드 후 사람처럼 잠시 체류한다.

        로드 → 약간의 대기 → 마우스 움직임 → 스크롤.
        """
        target = page or self.page
        if not target:
            return

        # 체류 시간 (로드 후 읽는 시간)
        dwell = random.uniform(
            HUMAN_BEHAVIOR["dwell_time_min"],
            HUMAN_BEHAVIOR["dwell_time_max"],
        )
        target.wait_for_timeout(int(dwell * 1000))

        # 마우스 이동 시뮬레이션 (자동화 탐지 우회)
        try:
            vw = target.viewport_size.get("width", 1920) if target.viewport_size else 1920
            vh = target.viewport_size.get("height", 1080) if target.viewport_size else 1080
            # 화면 중앙 근처에서 무작위 이동
            x = random.randint(int(vw * 0.2), int(vw * 0.8))
            y = random.randint(int(vh * 0.2), int(vh * 0.6))
            target.mouse.move(x, y)
            target.wait_for_timeout(random.randint(200, 500))
        except Exception:
            pass

    @staticmethod
    def _trigger_client_render(page):
        """SPA 클라이언트 렌더링을 트리거하기 위해 스크롤한다."""
        try:
            page.evaluate("""() => {
                window.scrollTo(0, document.body.scrollHeight / 3);
            }""")
            page.wait_for_timeout(2000)
            page.evaluate("""() => {
                window.scrollTo(0, 0);
            }""")
            page.wait_for_timeout(1000)
        except Exception:
            pass

    # ═══════════════════════════════════════════════════════════════
    # C. 쿠키 도메인 추출 헬퍼
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    def _get_cookie_domain(site_url: str) -> str:
        """사이트 URL에서 쿠키 영속화용 도메인을 추출한다."""
        try:
            parsed = urlparse(site_url)
            return parsed.hostname or ""
        except Exception:
            return ""

    # ═══════════════════════════════════════════════════════════════
    # D. 로그인 계정 로테이션
    # ═══════════════════════════════════════════════════════════════

    def _get_next_credential(self, site_id: int) -> dict | None:
        """사이트의 다음 사용할 로그인 계정을 반환한다.

        활성 계정 중 last_used_at이 가장 오래된(또는 NULL) 계정을 선택하고,
        사용 시각을 갱신하여 라운드로빈 로테이션한다.
        """
        creds = self.db.get_active_credentials(site_id)
        if not creds:
            return None
        chosen = creds[0]
        self.db.mark_credential_used(chosen["id"])
        return chosen

    def _do_login(
        self, page, credential: dict, login_config: dict | None = None,
        _retry_count: int = 0,
    ):
        """페이지에서 로그인을 수행한다.

        login_config 예시:
          {
            "login_url": "https://example.com/login",
            "id_selector": "#userId",
            "pwd_selector": "#password",
            "submit_selector": "#loginBtn",
            "success_indicator": ".my-page"
          }

        login_config가 없으면 범용 로그인 폼 탐지를 시도한다.

        소프트 차단 대응:
          로그인 페이지 접속 후 form/input이 없으면(이미지만 표시)
          프록시를 교체하고 재시도한다. (최대 3회)
        """
        _MAX_SOFT_BLOCK_RETRIES = 3

        cfg = login_config or {}
        login_url = cfg.get("login_url")

        if login_url:
            # _safe_goto 사용 → HTTP 차단 + 소프트 차단 + 프록시 교체 자동 처리
            resp = self._safe_goto(login_url)
            page = self.page  # 프록시 교체로 page가 변경될 수 있음
            page.wait_for_timeout(2000)

            # _safe_goto에서 프록시 교체 실패한 소프트 차단 잔여 확인
            if self._is_blocked(resp):
                if _retry_count < _MAX_SOFT_BLOCK_RETRIES and self._use_proxy:
                    print(
                        f"[{self.agent_type}] 로그인 페이지 차단 → "
                        f"프록시 교체 후 재시도 ({_retry_count + 1}/{_MAX_SOFT_BLOCK_RETRIES})"
                    )
                    if self._rotate_proxy():
                        page = self.page
                        return self._do_login(
                            page, credential, login_config,
                            _retry_count=_retry_count + 1,
                        )
                status = resp.status if resp else "N/A"
                print(f"[{self.agent_type}] 로그인 페이지 차단됨 (HTTP {status})")
                return False

        id_sel = cfg.get("id_selector", "")
        pwd_sel = cfg.get("pwd_selector", "")
        submit_sel = cfg.get("submit_selector", "")

        if not id_sel or not pwd_sel:
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
                    submitBtn = form.querySelector('button[type="submit"], input[type="submit"], button');
                }
                const sel = (el) => {
                    if (!el) return '';
                    if (el.id) return '#' + el.id;
                    if (el.name) return `[name="${el.name}"]`;
                    return '';
                };
                return {
                    id_selector: sel(idInput),
                    pwd_selector: sel(pwdInput),
                    submit_selector: sel(submitBtn)
                };
            }""")
            id_sel = id_sel or detected.get("id_selector", "")
            pwd_sel = pwd_sel or detected.get("pwd_selector", "")
            submit_sel = submit_sel or detected.get("submit_selector", "")

        if not id_sel or not pwd_sel:
            # 로그인 폼을 못 찾으면 소프트 차단일 가능성 → 프록시 교체 후 재시도
            if self._use_proxy and _retry_count < _MAX_SOFT_BLOCK_RETRIES:
                print(
                    f"[{self.agent_type}] 로그인 폼 미발견 (소프트 차단 추정) → "
                    f"프록시 교체 후 재시도 ({_retry_count + 1}/{_MAX_SOFT_BLOCK_RETRIES})"
                )
                if self._rotate_proxy():
                    page = self.page
                    return self._do_login(
                        page, credential, login_config,
                        _retry_count=_retry_count + 1,
                    )
            print(f"[{self.agent_type}] 로그인 폼을 찾을 수 없습니다")
            return False

        try:
            page.fill(id_sel, credential["login_id"])
            page.wait_for_timeout(random.randint(300, 700))
            page.fill(pwd_sel, credential["login_pwd"])
            page.wait_for_timeout(random.randint(300, 700))

            if submit_sel:
                page.click(submit_sel)
            else:
                page.press(pwd_sel, "Enter")

            page.wait_for_timeout(3000)

            success_sel = cfg.get("success_indicator", "")
            if success_sel:
                try:
                    page.wait_for_selector(success_sel, timeout=5000)
                    print(f"[{self.agent_type}] 로그인 성공: {credential['login_id']}")
                    return True
                except Exception:
                    print(f"[{self.agent_type}] 로그인 확인 실패: 성공 지표 미발견")
                    return False

            print(f"[{self.agent_type}] 로그인 시도 완료: {credential['login_id']}")
            return True
        except Exception as e:
            print(f"[{self.agent_type}] 로그인 실패: {e}")
            return False


# ═══════════════════════════════════════════════════════════════════
# 도메인별 레이트 리밋 상태 관리
# ═══════════════════════════════════════════════════════════════════

def _extract_domain(url: str) -> str:
    """URL에서 도메인을 추출한다."""
    try:
        return urlparse(url).hostname or "unknown"
    except Exception:
        return "unknown"


def _record_rate_limit(domain: str):
    """429/503 발생을 기록한다."""
    state = _rate_limit_state.setdefault(domain, {
        "consecutive_429": 0,
        "total_429": 0,
        "last_429_time": 0,
        "last_success_time": 0,
    })
    state["consecutive_429"] += 1
    state["total_429"] += 1
    state["last_429_time"] = time.time()


def _record_success(domain: str):
    """성공 요청을 기록하고 연속 429 카운터를 리셋한다."""
    state = _rate_limit_state.get(domain)
    if state:
        state["consecutive_429"] = 0
        state["last_success_time"] = time.time()
