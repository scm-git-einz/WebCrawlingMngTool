# 봇 차단 대응 기술 문서

## 1. 개요

크롤링 대상 사이트들은 다양한 봇 차단 기술(Rate Limiting, Browser Fingerprinting, Behavior Analysis 등)을 사용한다. 본 플랫폼은 **5가지 계층**의 봇 차단 대응 기술을 적용하여 안정적인 수집을 보장한다.

```
┌──────────────────────────────────────────────────────────────┐
│                  봇 차단 대응 5계층 구조                       │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ Layer 1. Stealth 브라우저           (core/browser.py)  │  │
│  │  자동화 탐지 우회 + 실제 브라우저 위장                    │  │
│  └────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ Layer 2. HTTP 헤더 위장              (core/browser.py)  │  │
│  │  실제 Chrome 브라우저와 동일한 헤더 구성                  │  │
│  └────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ Layer 3. 인간형 행동 시뮬레이션    (core/base_agent.py)  │  │
│  │  정규분포 딜레이 + 자연스러운 스크롤 + 마우스 이동         │  │
│  └────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ Layer 4. 적응형 백오프              (core/base_agent.py)  │  │
│  │  429/503 감지 시 지수 백오프 + 도메인별 이력 추적         │  │
│  └────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ Layer 5. 쿠키 영속화 + 네트워크 최적화                   │  │
│  │  세션 유지 + 불필요 리소스 차단 + Referer 체인            │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

---

## 2. Layer 1: Stealth 브라우저 (자동화 탐지 우회)

### 2.1 적용 위치
- **파일**: `core/browser.py`
- **라이브러리**: `playwright_stealth`

### 2.2 대응하는 봇 차단 기술

| 차단 기술 | 탐지 방식 | 우회 방법 |
|----------|----------|----------|
| WebDriver 탐지 | `navigator.webdriver === true` 검사 | `playwright_stealth`가 해당 속성을 `undefined`로 패치 |
| Chrome DevTools Protocol | CDP 연결 흔적 탐지 | Stealth 라이브러리가 CDP 관련 속성 은닉 |
| Automation 플래그 | `--enable-automation` Blink 기능 감지 | `--disable-blink-features=AutomationControlled` 플래그로 비활성화 |
| Headless 탐지 | headless 모드 특유의 속성 차이 탐지 | Stealth가 headless 관련 차이를 패치 |

### 2.3 구현 코드

```python
# Stealth 인스턴스 (프로세스 수준 싱글톤)
_stealth = Stealth(
    navigator_languages_override=("ko-KR", "ko"),   # 한국어 브라우저 위장
    navigator_platform_override="Win32",              # Windows 플랫폼 위장
)

# 브라우저 런치 시 자동화 플래그 비활성화
self._browser = self._playwright.chromium.launch(
    headless=True,
    args=[
        "--disable-blink-features=AutomationControlled",  # 자동화 감지 비활성화
        "--no-sandbox",
        "--disable-dev-shm-usage",
    ],
)

# 모든 새 페이지에 Stealth 적용
page = self._context.new_page()
_stealth.apply_stealth_sync(page)
```

### 2.4 Stealth가 패치하는 항목

| 항목 | 원래 값 (자동화) | 패치 후 값 |
|------|-----------------|-----------|
| `navigator.webdriver` | `true` | `undefined` |
| `navigator.languages` | `["en-US"]` | `["ko-KR", "ko"]` |
| `navigator.platform` | 변동 | `"Win32"` |
| `window.chrome` | 없음 | 실제 Chrome 객체 구조 추가 |
| Chrome DevTools 속성 | 노출 | 은닉 |
| `navigator.plugins` | 비어있음 | 실제 플러그인 목록 시뮬레이션 |

---

## 3. Layer 2: HTTP 헤더 위장

### 3.1 적용 위치
- **파일**: `core/browser.py`
- **설정**: `DEFAULT_BROWSER_CONFIG`

### 3.2 대응하는 봇 차단 기술

| 차단 기술 | 탐지 방식 | 우회 방법 |
|----------|----------|----------|
| User-Agent 분석 | 봇 라이브러리 특유의 UA 감지 | 실제 Chrome 125 UA 문자열 사용 |
| Client Hints 검증 | `Sec-Ch-Ua` 헤더 불일치 감지 | 실제 Chrome과 동일한 Client Hints 세트 |
| Sec-Fetch 메타데이터 | 비정상적 Fetch 메타데이터 감지 | 실제 브라우저 내비게이션과 동일한 값 설정 |
| Accept-Language 검사 | 비표준 언어 헤더 감지 | 한국어 브라우저 표준 Accept-Language |

### 3.3 설정 상세

```python
DEFAULT_BROWSER_CONFIG = {
    # ── User-Agent: 실제 Chrome 125 (Windows 10) ──
    "user_agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),

    # ── 뷰포트: 일반적인 데스크톱 해상도 ──
    "viewport": {"width": 1920, "height": 1080},

    # ── HTTP 헤더: 실제 Chrome과 동일한 세트 ──
    "headers": {
        "Accept": "text/html,application/xhtml+xml,..."
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",

        # Client Hints (Chrome 125 실제 값)
        "Sec-Ch-Ua": '"Chromium";v="125", "Google Chrome";v="125", "Not=A?Brand";v="8"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',

        # Fetch Metadata (정상 내비게이션)
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",

        "Upgrade-Insecure-Requests": "1",
    },
}
```

### 3.4 로케일/시간대 설정

```python
self._context = self._browser.new_context(
    user_agent=merged["user_agent"],
    viewport=merged["viewport"],
    extra_http_headers=merged.get("headers", {}),
    locale="ko-KR",                  # 한국어 로케일
    timezone_id="Asia/Seoul",        # 서울 시간대
)
```

> **왜 중요한가**: JavaScript로 `Intl.DateTimeFormat().resolvedOptions().timeZone`을 검사하여 서버 환경(UTC 등)에서 실행되는 봇을 감지하는 사이트가 있다. 한국어 로케일 + 서울 시간대로 설정하면 실제 한국 사용자 환경과 동일하다.

---

## 4. Layer 3: 인간형 행동 시뮬레이션

### 4.1 적용 위치
- **파일**: `core/base_agent.py`
- **사용 에이전트**: ProductAgent, NewsAgent, CafeAgent (모든 에이전트)

### 4.2 대응하는 봇 차단 기술

| 차단 기술 | 탐지 방식 | 우회 방법 |
|----------|----------|----------|
| 요청 간격 분석 | 일정한 간격(1초 등)의 기계적 요청 패턴 | 정규분포 기반 가변 딜레이 (1.5~8초) |
| 스크롤 행동 분석 | 즉시 페이지 하단 이동 또는 스크롤 없음 | 단계적 스크롤 + 중간 정지 + 역스크롤 |
| 마우스 이동 분석 | 마우스 이벤트 없음 (봇 특유) | 랜덤 좌표로 마우스 이동 시뮬레이션 |
| 체류 시간 분석 | 페이지 로드 즉시 다음 페이지 이동 | 2~5초 체류 + 마우스 이동 + 스크롤 |

### 4.3 인간형 딜레이 (`_human_delay`)

```python
HUMAN_BEHAVIOR = {
    "nav_delay_mean": 3.5,    # 평균 3.5초
    "nav_delay_std": 1.5,     # 표준편차 1.5초
    "nav_delay_min": 1.5,     # 최소 1.5초
    "nav_delay_max": 8.0,     # 최대 8.0초
}

def _human_delay(self):
    """정규분포 기반 가변 딜레이"""
    delay = random.gauss(mean=3.5, std=1.5)
    delay = clamp(delay, 1.5, 8.0)
    time.sleep(delay)
```

**딜레이 분포 시각화**:
```
빈도
  │    ▃
  │   ▇█▇
  │  ▅███▅
  │ ▃█████▃
  │▂███████▂
  └──────────────→ 초
  1.5  3.5  5.5  8.0

  평균: 3.5초 (사람의 실제 페이지 전환 간격에 근사)
  대부분: 2~5초 범위
  가끔: 6~8초 (긴 체류를 시뮬레이션)
```

### 4.4 인간형 스크롤 (`_human_scroll`)

```python
HUMAN_BEHAVIOR = {
    "scroll_pause_min": 800,    # 스크롤 후 최소 정지 (ms)
    "scroll_pause_max": 2500,   # 스크롤 후 최대 정지 (ms)
    "scroll_steps": 3,          # 스크롤 단계 수
}
```

**스크롤 동작 시퀀스**:
```
[1단계] 화면의 30~80%만큼 아래로 스크롤
         → 800~2500ms 정지 (읽는 시간 시뮬레이션)

[2단계] 다시 30~80%만큼 아래로 스크롤
         → 800~2500ms 정지
         → (20% 확률) 10~20%만큼 위로 역스크롤
            → 500~1000ms 정지 (다시 보기 시뮬레이션)

[3단계] 다시 30~80%만큼 아래로 스크롤
         → 800~2500ms 정지
```

**왜 역스크롤이 중요한가**:
- 실제 사용자는 스크롤하다가 이전 내용을 다시 확인하기 위해 위로 올라감
- 봇은 항상 아래로만 스크롤 → 행동 분석 시스템이 이 패턴을 감지
- 20% 확률의 역스크롤로 자연스러운 사용자 행동을 시뮬레이션

### 4.5 인간형 체류 (`_human_dwell`)

```python
HUMAN_BEHAVIOR = {
    "dwell_time_min": 2.0,    # 최소 체류 (초)
    "dwell_time_max": 5.0,    # 최대 체류 (초)
}
```

**체류 동작 시퀀스**:
```
페이지 로드 완료
  → [1] 2~5초 대기 (콘텐츠를 읽는 시간)
  → [2] 화면 중앙 근처(20~80% 영역)에서 랜덤 좌표로 마우스 이동
  → [3] 200~500ms 대기
```

**왜 마우스 이동이 중요한가**:
- 일부 사이트는 `mousemove` 이벤트 발생 여부를 추적
- 마우스 이벤트가 전혀 없으면 → 봇으로 판정
- 화면 중앙 근처에서 무작위 이동하여 자연스러운 마우스 활동을 시뮬레이션

### 4.6 에이전트별 적용 패턴

모든 에이전트가 동일한 패턴으로 봇 차단 대응 메서드를 사용한다:

```python
# 페이지 접속 (적응형 백오프 포함)
resp = self._safe_goto(url)

# 차단 여부 확인
if self._is_blocked(resp):
    print("차단됨, 건너뜀")
    return

# 인간형 행동 시뮬레이션
self._human_dwell()     # 체류 + 마우스 이동
self._human_scroll()    # 자연스러운 스크롤

# 데이터 수집 ...

# 다음 페이지로 이동 전 딜레이
self._delay()           # 정규분포 기반 가변 딜레이
```

---

## 5. Layer 4: 적응형 백오프 (Rate Limit 대응)

### 5.1 적용 위치
- **파일**: `core/base_agent.py`
- **메서드**: `_safe_goto()`, `_calc_backoff_wait()`, `_preemptive_wait()`

### 5.2 대응하는 봇 차단 기술

| 차단 기술 | 탐지 방식 | 우회 방법 |
|----------|----------|----------|
| Rate Limiting (429) | 단위 시간 내 과도한 요청 수 | 지수 백오프 대기 (120초 → 240초 → 480초) |
| 서비스 보호 (503) | 서버 과부하 시 임시 차단 | 동일한 백오프 로직 적용 |
| IP 차단 (403) | 차단 감지 후 차단 여부 확인 | `_is_blocked()` 판별 후 건너뜀 |
| 패턴 차단 | 일정한 재시도 간격 감지 | 랜덤 지터(±30%)로 재시도 패턴 무작위화 |

### 5.3 백오프 설정

```python
ADAPTIVE_BACKOFF = {
    "base_wait_secs": 120,     # 첫 429/503 시 기본 대기: 2분
    "max_wait_secs": 600,      # 최대 대기: 10분
    "multiplier": 2.0,         # 지수 배수: 2배씩 증가
    "jitter_pct": 0.3,         # 지터: ±30%
    "max_retries": 5,          # 최대 재시도: 5회
}
```

### 5.4 백오프 동작 흐름

```
요청 → 429/503 응답?
  │
  ├── No → 성공 → 연속 429 카운터 리셋, Referer 갱신
  │
  └── Yes → 적응형 백오프 계산
            │
            ├── 기본 대기: 120초
            ├── × 지수 배수: 2^attempt (1회차: ×1, 2회차: ×2, 3회차: ×4)
            ├── × 이력 가중: 1 + (연속429횟수 × 0.5)
            ├── 상한: min(계산값, 600초)
            ├── + 랜덤 지터: ±30%
            └── 하한: max(결과, 60초)

            → 대기 후 재시도 (최대 5회)
```

### 5.5 실제 백오프 대기 시간 예시

| 시도 | 연속 429 | 기본 대기 | 지수 배수 | 이력 가중 | 결과 범위 |
|------|---------|----------|----------|----------|----------|
| 1회차 | 0 | 120s | ×1 | ×1.0 | 84~156초 |
| 2회차 | 1 | 120s | ×2 | ×1.5 | 252~468초 |
| 3회차 | 2 | 120s | ×4 | ×2.0 | 600초 (상한) |
| 4회차 | 3 | 120s | ×8 | ×2.5 | 600초 (상한) |
| 5회차 | 4 | 120s | ×16 | ×3.0 | 600초 (상한) |

### 5.6 선제적 대기 (`_preemptive_wait`)

```
요청 전 도메인 이력 확인
  │
  ├── 연속 429 = 0 또는 마지막 429로부터 5분 경과 → 바로 요청
  │
  └── 연속 429 > 0 이고 5분 이내 → 선제적 쿨다운
       대기 시간 = min(30 + 연속429 × 15, 120)초

       예시:
         연속 1회 → 45초 쿨다운
         연속 2회 → 60초 쿨다운
         연속 3회 → 75초 쿨다운
         연속 6회+ → 120초 쿨다운 (상한)
```

**왜 선제적 대기가 필요한가**:
- 429를 받은 직후 바로 재요청하면 추가 패널티(IP 차단 등)를 받을 수 있음
- 연속으로 429를 받을수록 해당 도메인의 Rate Limit이 엄격해지고 있다는 신호
- 미리 대기함으로써 Rate Limit 카운터가 리셋될 시간을 확보

### 5.7 도메인별 레이트 리밋 상태 관리

```python
# 프로세스 수준 캐시 (에이전트 실행 중 유지)
_rate_limit_state: dict[str, dict] = {}

# 도메인별 추적 정보
{
    "smartstore.naver.com": {
        "consecutive_429": 2,       # 연속 429 횟수
        "total_429": 5,             # 누적 429 횟수
        "last_429_time": 1716...,   # 마지막 429 발생 시각
        "last_success_time": 1716..., # 마지막 성공 시각
    }
}
```

---

## 6. Layer 5: 쿠키 영속화 + 네트워크 최적화

### 6.1 쿠키 영속화

**적용 위치**: `core/browser.py` - `BrowserManager`

```
수집 시작 시:
  → 이전 세션의 쿠키 파일 로드 (data/cookies/{도메인}.json)
  → 브라우저 컨텍스트에 주입

수집 종료 시:
  → 현재 브라우저의 모든 쿠키를 파일에 저장
  → 다음 수집 시 동일한 세션으로 인식됨
```

**쿠키 저장 경로**: `data/cookies/` 디렉토리
```
data/cookies/
  ├── smartstore_naver_com.json
  ├── brand_naver_com.json
  ├── shopping_naver_com.json
  └── ...
```

**왜 중요한가**:
- 쿠키 없이 매번 새 세션으로 접속하면 봇으로 의심받기 쉬움
- 로그인 세션, 사용자 설정, 동의 상태 등을 유지하여 재방문 사용자로 인식
- 일부 사이트는 첫 방문 시 CAPTCHA/검증을 요구하지만 쿠키가 있으면 생략

### 6.2 불필요 리소스 차단

```python
DEFAULT_BROWSER_CONFIG = {
    "blocked_resource_types": ["font", "media"],
}
```

**차단 리소스**:
| 리소스 타입 | 차단 이유 |
|-----------|----------|
| `font` | 폰트 다운로드 불필요, 트래픽 절약 |
| `media` | 동영상/오디오 불필요, 대역폭 절약 |

**차단하지 않는 리소스** (봇 탐지 우회를 위해 유지):
| 리소스 타입 | 유지 이유 |
|-----------|----------|
| `image` | 일부 사이트가 이미지 로드 여부를 봇 판별에 사용 |
| `stylesheet` | CSS 로드 실패 시 렌더링 차이로 봇 감지 가능 |
| `script` | JavaScript 실행이 필수 (SPA 렌더링, 봇 감지 스크립트) |

### 6.3 Referer 체인

```python
# _safe_goto() 내부
if self._last_url:
    self.page.set_extra_http_headers({
        "Referer": self._last_url,
    })

# 성공 시 갱신
self._last_url = url
```

**동작 방식**:
```
1. 매장 목록 페이지 접속 (Referer 없음 - 직접 접속)
2. 매장 상세 페이지 접속 (Referer: 매장 목록 URL)
3. 상품 상세 페이지 접속 (Referer: 매장 상세 URL)
```

**왜 중요한가**:
- 실제 사용자는 이전 페이지에서 링크를 클릭하여 이동 → Referer 헤더 자동 설정
- 봇은 직접 URL을 입력하여 접속 → Referer 없음
- Referer 체인을 유지하면 자연스러운 내비게이션 경로를 시뮬레이션

### 6.4 도메인 허용 목록

```python
"allowed_domains": []  # 기본값: 비어있음 (모든 도메인 허용)
```

- 플랫폼별 브라우저 설정(`platforms.browser`)에서 허용 도메인을 지정할 수 있음
- 설정 시 해당 도메인 이외의 요청은 차단 → 불필요한 외부 호출 방지
- 트래킹/광고 서버로의 요청 차단으로 수집 속도 향상

---

## 7. 차단 감지 및 대응 결정

### 7.1 차단 판별 (`_is_blocked`)

```python
@staticmethod
def _is_blocked(resp) -> bool:
    """응답이 차단(429/403/503)인지 확인"""
    if resp is None:
        return False
    return resp.status in (429, 403, 503)
```

### 7.2 HTTP 상태 코드별 대응

| 상태 코드 | 의미 | 대응 |
|----------|------|------|
| **429** | Too Many Requests (Rate Limit 초과) | 적응형 백오프 대기 후 재시도 |
| **503** | Service Unavailable (서버 과부하) | 적응형 백오프 대기 후 재시도 |
| **403** | Forbidden (접근 차단) | 재시도 없이 해당 페이지 건너뜀 |
| **200** | 성공 | 정상 수집 진행, 레이트 리밋 카운터 리셋 |

### 7.3 에이전트별 차단 대응 호출 현황

| 메서드 | ProductAgent | NewsAgent | CafeAgent |
|--------|-------------|-----------|-----------|
| `_safe_goto()` | 8회 호출 | 5회 호출 | 3회 호출 |
| `_is_blocked()` | 8회 호출 | 5회 호출 | 3회 호출 |
| `_human_dwell()` | 4회 호출 | 4회 호출 | 3회 호출 |
| `_human_scroll()` | 2회 호출 | 2회 호출 | 2회 호출 |
| `_delay()` | 3회 호출 | 3회 호출 | 1회 호출 |

---

## 8. 네트워크 인터셉터의 봇 차단 회피

### 8.1 적용 위치
- **파일**: `core/network_interceptor.py`

### 8.2 트래킹/분석 요청 필터링

```python
_EXCLUDE_PATTERNS = [
    # 분석/추적 서비스 (봇 탐지에 활용될 수 있음)
    "analytics", "tracking", "beacon", "pixel",
    "doubleclick", "google-analytics", "facebook.com",
    "hotjar", "sentry", "datadog", "amplitude",
    "tiktok", "kakao", "criteo", "braze",
    "cloudflare", "cdn-cgi", "rum?", "gtag",
    "ads", "adservice", "adsense",

    # 불필요 정적 리소스
    "fonts.googleapis", "fonts.gstatic",
    ".css", ".js", ".png", ".jpg", ".gif", ".svg", ".woff",
    ".ico", ".webp", ".avif",
]
```

**왜 중요한가**:
- 트래킹/분석 서비스는 브라우저 핑거프린팅 데이터를 수집하여 봇 여부를 판별
- 이 서비스들의 응답을 캡처할 필요가 없으므로 인터셉터에서 제외
- 인터셉터의 부하를 줄이고 필요한 API 요청만 분석

---

## 9. 설정 요약

### 9.1 전체 타이밍 설정

| 설정 | 값 | 용도 |
|------|---|------|
| 페이지 이동 딜레이 | 1.5~8초 (평균 3.5초) | 페이지 간 이동 대기 |
| 페이지 체류 시간 | 2~5초 | 페이지 로드 후 읽기 시뮬레이션 |
| 스크롤 정지 시간 | 0.8~2.5초 | 스크롤 후 읽기 시뮬레이션 |
| 스크롤 단계 | 3단계 | 점진적 스크롤 |
| 역스크롤 확률 | 20% | 사용자의 되돌아보기 행동 |
| 429 기본 대기 | 120초 | Rate Limit 초과 시 기본 대기 |
| 429 최대 대기 | 600초 | Rate Limit 최대 대기 |
| 백오프 배수 | 2배 | 지수 백오프 증가율 |
| 지터 범위 | ±30% | 대기 시간 무작위화 |
| 최대 재시도 | 5회 | 포기 전 최대 시도 |
| 선제 쿨다운 | 30~120초 | 429 이력 도메인 접속 전 대기 |

### 9.2 기술 적용 매트릭스

| 기술 | 파일 | 메서드/설정 | 적용 시점 |
|------|------|-----------|----------|
| Stealth 패치 | `browser.py` | `_stealth.apply_stealth_sync()` | 페이지 생성 시 |
| 자동화 비활성화 | `browser.py` | `--disable-blink-features` | 브라우저 런치 시 |
| UA 위장 | `browser.py` | `DEFAULT_BROWSER_CONFIG` | 컨텍스트 생성 시 |
| Client Hints | `browser.py` | `Sec-Ch-Ua` 헤더 | 모든 요청 |
| Fetch Metadata | `browser.py` | `Sec-Fetch-*` 헤더 | 모든 요청 |
| 로케일/시간대 | `browser.py` | `locale`, `timezone_id` | 컨텍스트 생성 시 |
| 정규분포 딜레이 | `base_agent.py` | `_human_delay()` | 페이지 이동 전 |
| 자연 스크롤 | `base_agent.py` | `_human_scroll()` | 페이지 로드 후 |
| 마우스 이동 | `base_agent.py` | `_human_dwell()` | 페이지 로드 후 |
| 적응형 백오프 | `base_agent.py` | `_safe_goto()` | 모든 페이지 이동 |
| 선제적 대기 | `base_agent.py` | `_preemptive_wait()` | 429 이력 도메인 접속 전 |
| 차단 감지 | `base_agent.py` | `_is_blocked()` | 모든 응답 확인 |
| Referer 체인 | `base_agent.py` | `_safe_goto()` 내부 | 모든 페이지 이동 |
| 쿠키 영속화 | `browser.py` | `save_cookies()` / `_load_cookies()` | 수집 시작/종료 시 |
| 리소스 차단 | `browser.py` | `blocked_resource_types` | 모든 요청 |
| 트래킹 필터 | `network_interceptor.py` | `_EXCLUDE_PATTERNS` | 네트워크 캡처 시 |
