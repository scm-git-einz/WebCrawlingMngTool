"""IWC 가격 수집 테스트"""
import sys

DEFAULT_URL = (
    "https://www.iwc.com/kr-ko/watches/pilot-watches"
    "/iw328301-pilots-watch-mark-xx-le-petit-prince"
)

def main():
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    print("=" * 60)
    print("IWC 가격 수집 테스트")
    print(f"URL: {url}")
    print("=" * 60)
    from agents.brand.iwc.engine import IWCAgent
    result = IWCAgent().fetch_product(url)
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
