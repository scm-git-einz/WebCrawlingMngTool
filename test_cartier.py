"""
까르띠에 상품 가격 수집 테스트

사용법:
  python test_cartier.py                    # 기본 URL 테스트
  python test_cartier.py HPI01500           # SKU로 검색
  python test_cartier.py https://www...     # URL 직접 지정
"""
import sys

DEFAULT_SKU = "HPI01500"
DEFAULT_URL = (
    "https://www.cartier.com/ko-kr/%EB%B0%B1-%EB%B0%8F-%EC%95%A1%EC%84%B8%EC%84%9C%EB%A6%AC"
    "/%EC%BB%AC%EB%A0%89%EC%85%98/%EB%A7%88%EC%9D%B4%ED%81%AC%EB%A1%9C%28micro%29"
    "-%EB%B0%B1-%ED%8C%AC%EB%8D%94-c-CRL3002220.html"
)


def print_result(result: dict):
    print()
    print("=" * 60)
    print("수집 결과")
    print("=" * 60)
    print(f"  상품명  : {result.get('name') or '(없음)'}")
    print(f"  SKU     : {result.get('sku') or '(없음)'}")
    print(f"  가격    : {result.get('price') or '(없음)'} {result.get('currency', '')}")
    print(f"  수집방법: {result.get('source')}")
    if result.get("url"):
        print(f"  URL     : {result['url'][:100]}")
    if result.get("raw_api_url"):
        print(f"  API URL : {result['raw_api_url'][:100]}")
    if result.get("error"):
        print(f"  오류    : {result['error']}")
    print("=" * 60)


def main():
    from agents.brand.cartier.engine import CartierAgent
    agent = CartierAgent()

    arg = sys.argv[1] if len(sys.argv) > 1 else None

    if arg and arg.startswith("http"):
        print("=" * 60)
        print(f"까르띠에 URL 수집 테스트")
        print(f"URL: {arg}")
        print("=" * 60)
        result = agent.fetch_product(arg)
    else:
        sku = arg or DEFAULT_SKU
        print("=" * 60)
        print(f"까르띠에 SKU 수집 테스트")
        print(f"SKU: {sku}")
        print("=" * 60)
        result = agent.fetch_by_sku(sku)

    print_result(result)


if __name__ == "__main__":
    main()
