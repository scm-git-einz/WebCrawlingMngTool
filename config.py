"""크롤링 에이전트 설정"""
import os

# ─── 대상 URL ─────────────────────────────────────────────────────
TARGET_URL = "https://kor.lottedfs.com/kr/shopmain/rankingTrending/main#none"
MOBILE_BASE_URL = "https://m.kor.lottedfs.com"
MOBILE_HOME_URL = f"{MOBILE_BASE_URL}/kr/shopmain/home"
MOBILE_RANKING_URL = f"{MOBILE_BASE_URL}/kr/shopmain/rankingTrending/main"
PRODUCT_DETAIL_URL = f"{MOBILE_BASE_URL}/kr/product/productDetail?prdNo={{product_id}}"

# ─── 수집 설정 ────────────────────────────────────────────────────
MAX_PRODUCTS_DETAIL = 20       # 상세 수집할 상품 수
REQUEST_DELAY_MIN = 1.5        # 요청 간 최소 대기(초)
REQUEST_DELAY_MAX = 3.0        # 요청 간 최대 대기(초)
PAGE_LOAD_TIMEOUT = 30000      # 페이지 로드 타임아웃(ms)
SCROLL_COUNT = 15              # 스크롤 횟수 (lazy-load 트리거)

# ─── 출력 디렉토리 ────────────────────────────────────────────────
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
