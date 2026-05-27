"""
네이버 브랜드스토어 크롤링 설정

사용법:
  python main.py --store kerastase
  python main.py --store esteelauderkorea
  STORE_SLUG=kerastase python main.py

사이트 구조 변경 시 아래 매핑만 수정하면 크롤러 코드는 수정 불필요.
"""
import os

# ═══════════════════════════════════════════════════════════════════
# 1. 대상 스토어 (CLI 인자 → 환경변수 → 기본값)
# ═══════════════════════════════════════════════════════════════════
STORE_SLUG = os.environ.get("STORE_SLUG", "esteelauderkorea")
BASE_URL = "https://brand.naver.com"
TARGET_URL = f"{BASE_URL}/{STORE_SLUG}"

# ═══════════════════════════════════════════════════════════════════
# 2. 브라우저 전역 변수명
# ═══════════════════════════════════════════════════════════════════
STATE_VAR = "__PRELOADED_STATE__"

# ═══════════════════════════════════════════════════════════════════
# 3. 매장 정보 필드 매핑 (JS 경로)
#    - root_key: STATE_VAR 하위의 매장 정보 루트 키
#    - 나머지: root_key 내부의 dot 경로 (예: "a.b.c" → obj.a.b.c)
#    - 리스트: 폴백 체인 (첫 번째가 없으면 두 번째 시도)
# ═══════════════════════════════════════════════════════════════════
STORE_FIELD_MAP = {
    "root_key":       "channel",
    "store_name":     "channelName",
    "store_id":       ["id", "channelId"],
    "description":    "description",
    "representative": "representName",
    "sale_count":     "saleCount",
    "logo_url":       "representativeImageUrl",
    "address":        ["businessAddressInfo.fullAddressInfo", "businessAddressInfo.basicAddress"],
    "phone":          "contactInfo.telNo.formattedNumber",
}

# ═══════════════════════════════════════════════════════════════════
# 4. 상품 목록 필드 매핑 (JS 경로)
# ═══════════════════════════════════════════════════════════════════
PRODUCT_FIELD_MAP = {
    # ── 카테고리 구조 ──
    "category_root":    "categoryMenu",
    "category_list":    "firstCategories",
    "category_id":      ["categoryId", "id"],
    "category_name":    ["categoryName", "name"],

    # ── 상품 리스트 구조 ──
    "products_root":    "categoryProducts",
    "products_list":    "simpleProducts",
    "total_count":      "totalCount",

    # ── 개별 상품 필드 ──
    "product_id":       ["productNo", "id"],
    "product_name":     ["name", "dispName"],
    "sale_price":       "salePrice",
    "discounted_price": "benefitsView.discountedSalePrice",
    "discount_rate":    "benefitsView.discountedRatio",
    "image_url":        "representativeImageUrl",
    "review_count":     "reviewAmount.totalReviewCount",
    "average_score":    "reviewAmount.averageReviewScore",
    "brand_name":       "naverShoppingSearchInfo.brandName",
    "detail_text":      "detailContents.detailContentText",
}

# ═══════════════════════════════════════════════════════════════════
# 5. 상품 상세 페이지 필드 매핑
# ═══════════════════════════════════════════════════════════════════
DETAIL_FIELD_MAP = {
    # STATE_VAR 하위에서 상세 데이터를 찾을 키 (순서대로 시도)
    "detail_roots":     ["product", "simpleProductForDetailPage"],
    "description":      "detailContents.detailContentText",
    "detail_images":    "optionalImageUrls",
}

# ═══════════════════════════════════════════════════════════════════
# 6. URL 패턴 ({slug}, {cat_id}, {page}, {product_id} 치환)
# ═══════════════════════════════════════════════════════════════════
URL_PATTERNS = {
    "category_page":  "/{slug}/category/{cat_id}?cp={page}",
    "product_page":   "/{slug}/products/{product_id}",
}

# ═══════════════════════════════════════════════════════════════════
# 7. DOM 폴백 셀렉터 (상세 설명 영역)
# ═══════════════════════════════════════════════════════════════════
DETAIL_DOM_SELECTORS = [
    '[class*="se-viewer"]',
    '[class*="detail_content"]',
    '#INTRODUCE',
]

# ═══════════════════════════════════════════════════════════════════
# 8. 네트워크 / 수집 설정
# ═══════════════════════════════════════════════════════════════════
ALLOWED_DOMAINS = [
    "brand.naver.com",
    "smartstore.naver.com",
    "shop-phinf.pstatic.net",
    "shopping-phinf.pstatic.net",
    "ssl.pstatic.net",
]
BLOCKED_RESOURCE_TYPES = ["font", "media"]

MAX_PRODUCTS_DETAIL = 20
REQUEST_DELAY_MIN = 1.0
REQUEST_DELAY_MAX = 2.0
PAGE_LOAD_TIMEOUT = 30000
PAGE_SIZE = 40                  # 네이버 한 페이지당 상품 수

# ═══════════════════════════════════════════════════════════════════
# 9. 브라우저 설정
# ═══════════════════════════════════════════════════════════════════
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)
COMMON_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}
VIEWPORT = {"width": 1920, "height": 1080}

# ═══════════════════════════════════════════════════════════════════
# 10. 출력 디렉토리 (브랜드별 분리)
# ═══════════════════════════════════════════════════════════════════
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output", STORE_SLUG)


def reload_for_store(slug: str):
    """런타임에 스토어 슬러그를 변경하고 관련 상수를 재설정한다."""
    global STORE_SLUG, TARGET_URL, OUTPUT_DIR
    STORE_SLUG = slug
    TARGET_URL = f"{BASE_URL}/{STORE_SLUG}"
    OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output", STORE_SLUG)
