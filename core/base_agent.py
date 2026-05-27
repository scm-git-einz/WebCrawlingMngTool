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
        # 현재 세션의 마지막 방문 URL (Referer 체인용)
        self._last_url: str | None = None

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
                    wait_secs = self._calc_backoff_wait(
                        domain, attempt,
                    )
                    print(
                        f"[{self.agent_type}] HTTP {resp.status} @ "
                        f"{domain} → {wait_secs:.0f}초 대기 "
                        f"({attempt + 1}/{max_retries})"
                    )
                    _record_rate_limit(domain)
                    time.sleep(wait_secs)
                    continue

                # 성공 → 레이트 리밋 상태 리셋 & Referer 갱신
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

    @staticmethod
    def _is_blocked(resp) -> bool:
        """응답이 차단(429/403/503)인지 확인한다."""
        if resp is None:
            return False
        return resp.status in (429, 403, 503)

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
