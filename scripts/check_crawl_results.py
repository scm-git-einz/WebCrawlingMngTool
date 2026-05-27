"""크롤링 결과 확인 스크립트"""
import sys, json, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, "D:\\crawling")
from core.db import CrawlDB

db = CrawlDB()
result = db.get_latest_result(9)

print(f"Status: {result['status']}")
print(f"Product count: {result['product_count']}")
print(f"Elapsed: {result.get('elapsed_sec', 0):.1f}s")

products = result.get("products", [])
if isinstance(products, str):
    products = json.loads(products)

# 가격 정보가 있는 게시글
price_posts = [p for p in products if p.get("prices")]
print(f"\nTotal posts: {len(products)}")
print(f"Posts with prices: {len(price_posts)}")

print("\n" + "=" * 80)
print("가격 정보가 있는 게시글:")
print("=" * 80)

for p in price_posts:
    title = p.get("title", "N/A")[:60]
    prices = p.get("prices", [])
    post_id = p.get("post_id", "?")
    print(f"\n  [{post_id}] {title}")
    for pr in prices:
        src = pr.get("source", "text")
        product = pr.get("product", "")[:35]
        price = pr.get("price", "")
        print(f"      {product:35s} | {price:15s} | src={src}")

# OCR로 추출된 가격만 따로 집계
ocr_count = 0
text_count = 0
for p in price_posts:
    for pr in p.get("prices", []):
        if pr.get("source") == "ocr":
            ocr_count += 1
        else:
            text_count += 1

print(f"\n{'=' * 80}")
print(f"총 가격 항목: {ocr_count + text_count}개")
print(f"  - 본문 텍스트: {text_count}개")
print(f"  - 이미지 OCR: {ocr_count}개")

db.close()
