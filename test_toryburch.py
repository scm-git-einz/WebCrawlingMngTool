"""
토리버치 상품 가격 수집 테스트

사용법:
  python test_toryburch.py                       # 기본 URL 테스트
  python test_toryburch.py TB63D3LYBA            # SKU로 검색
  python test_toryburch.py https://www...        # URL 직접 지정
"""
import sys

DEFAULT_SKU = "TB63D3LYBA"
DEFAULT_URL = (
    "https://www.toryburch.co.kr/public/goods/goodsDetail"
    "?godNo=GM0026021974708&cate=TRYA23A05"
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
    from agents.brand.toryburch.engine import ToryBurchAgent
    agent = ToryBurchAgent()

    arg = sys.argv[1] if len(sys.argv) > 1 else None

    if arg and arg.startswith("http"):
        print("=" * 60)
        print(f"토리버치 URL 수집 테스트")
        print(f"URL: {arg}")
        print("=" * 60)
        result = agent.fetch_product(arg)
    else:
        sku = arg or DEFAULT_SKU
        print("=" * 60)
        print(f"토리버치 SKU 수집 테스트")
        print(f"SKU: {sku}")
        print("=" * 60)
        result = agent.fetch_by_sku(sku)

    print_result(result)


if __name__ == "__main__":
    main()
