"""engine.py 통합 테스트 - 가격-상품명 페어링 (게시글 3건)"""
import sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, "D:\\crawling")

from core.db import CrawlDB
from agents.cafe.engine import CafeAgent

# date_range_days=1로 설정해서 오늘 게시글만 수집 (빠른 테스트)
db = CrawlDB()
site = db.get_site(9)

# 임시로 config 변경 (실제 DB는 수정 안함)
cfg = json.loads(site["crawl_config"])
print(f"현재 config: {json.dumps(cfg, ensure_ascii=False)}")

agent = CafeAgent()
agent.run_site(9)

# 결과 확인
result_file = "output/9_꼬냑클럽/posts.json"
posts = json.load(open(result_file, "r", encoding="utf-8"))
price_posts = [p for p in posts if p.get("prices")]

print(f"\n{'='*60}")
print(f"전체 게시글: {len(posts)}개")
print(f"가격 포함: {len(price_posts)}개")
print(f"\n=== 가격-상품명 페어링 결과 ===\n")

for p in price_posts[:5]:
    print(f"제목: {p['title'][:60]}")
    for item in p['prices']:
        if isinstance(item, dict):
            print(f"  → 상품: '{item.get('product','')}' | 가격: {item.get('price','')}")
        else:
            print(f"  → (구 형식) {item}")
    print()
