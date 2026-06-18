"""
루이비통 상품 상세 페이지 가격 수집 테스트

사용법:
  python test_lv.py
  python test_lv.py M81455
  python test_lv.py https://kr.louisvuitton.com/kor-kr/products/.../M81455
"""
import sys
import re

BASE_URL = "https://kr.louisvuitton.com/kor-kr/products"

# 테스트 기본값
DEFAULT_URL = (
    "https://kr.louisvuitton.com/kor-kr/products/"
    "side-trunk-mm-h27-nvprod5280038v/M25160"
)


def resolve_url(arg: str) -> str:
    if arg.startswith("http"):
        return arg
    # SKU만 넘기면 URL로 조합 (slug는 모르니까 sku만 경로에 추가)
    # LV URL 패턴: /products/{slug}/{sku} — slug 없이는 접근 불가
    # 일단 기본 URL 유지하고 SKU만 교체
    sku_match = re.match(r"^[A-Z0-9]{5,}$", arg.strip())
    if sku_match:
        print(f"[info] SKU만 전달됨: {arg}")
        print(f"[info] LV URL은 /products/{{slug}}/{{sku}} 형식이 필요합니다.")
        print(f"[info] 전체 상품 URL을 전달해주세요.")
        sys.exit(1)
    return arg


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    url = resolve_url(arg)

    print("=" * 60)
    print("루이비통 가격 수집 테스트")
    print(f"URL: {url}")
    print("=" * 60)

    from agents.brand.louisvuitton.engine import LouisVuittonAgent
    agent = LouisVuittonAgent()
    result = agent.fetch_product(url)

    print()
    print("=" * 60)
    print("수집 결과")
    print("=" * 60)
    print(f"  상품명  : {result.get('name') or '(없음)'}")
    print(f"  SKU     : {result.get('sku') or '(없음)'}")
    print(f"  가격    : {result.get('price') or '(없음)'} {result.get('currency', '')}")
    print(f"  수집방법: {result.get('source')}")
    if result.get("raw_api_url"):
        print(f"  API URL : {result['raw_api_url'][:100]}")
    if result.get("error"):
        print(f"  오류    : {result['error']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
