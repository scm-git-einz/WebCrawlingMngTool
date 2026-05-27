"""에이전트 아키텍처 호환성 테스트 (크롤링 없이 구조 검증)"""
import sys
import json
sys.path.insert(0, "D:\\crawling")

from core.db import CrawlDB
from core.base_agent import BaseAgent
from agents import AGENT_REGISTRY, get_agent
from agents.product.engine import ProductAgent
from agents.news.engine import NewsAgent

print("=== 에이전트 아키텍처 테스트 ===\n")

# 1. 레지스트리 확인
print("1. AGENT_REGISTRY:", list(AGENT_REGISTRY.keys()))
assert "product" in AGENT_REGISTRY
assert "news" in AGENT_REGISTRY

# 2. BaseAgent ABC 검증
print("2. BaseAgent ABC 검증:", end=" ")
assert issubclass(ProductAgent, BaseAgent)
assert issubclass(NewsAgent, BaseAgent)
print("OK")

# 3. get_agent 팩토리 검증
print("3. get_agent 팩토리:", end=" ")
db = CrawlDB()
pa = get_agent("product", db=db)
na = get_agent("news", db=db)
assert isinstance(pa, ProductAgent)
assert isinstance(na, NewsAgent)
assert pa.agent_type == "product"
assert na.agent_type == "news"
print("OK")

# 4. DB 스키마 검증
print("4. DB 스키마 검증:", end=" ")
sites = db.get_all_sites()
for site in sites:
    assert "agent_type" in site, f"site {site['id']}: agent_type 없음"
    assert "crawl_config" in site, f"site {site['id']}: crawl_config 없음"
print(f"OK ({len(sites)}개 사이트)")

# 5. crawl_config CRUD 검증
print("5. crawl_config CRUD:", end=" ")
test_config = {"collect_details": False, "max_products": 50}
db.update_crawl_config(sites[0]["id"], test_config)
loaded = db.get_crawl_config(sites[0]["id"])
assert loaded == test_config, f"Expected {test_config}, got {loaded}"
db.update_crawl_config(sites[0]["id"], {})  # 리셋
loaded = db.get_crawl_config(sites[0]["id"])
assert loaded == {}, f"Expected empty, got {loaded}"
print("OK")

# 6. agent_type별 사이트 조회
print("6. agent_type별 사이트 조회:", end=" ")
product_sites = db.get_active_sites_by_agent("product")
news_sites = db.get_active_sites_by_agent("news")
print(f"product={len(product_sites)}, news={len(news_sites)}")

# 7. 기존 CrawlEngine 하위 호환
print("7. CrawlEngine 하위 호환:", end=" ")
from core.engine import CrawlEngine
engine = CrawlEngine(db=db)
assert engine.db is db
print("OK")

# 8. ProductAgent crawl_config 해석 검증
print("8. ProductAgent crawl_config 해석:", end=" ")
pa2 = ProductAgent(db=db)
test_site = {
    "crawl_config": json.dumps({"collect_details": False, "max_products": 30})
}
cfg = pa2.get_crawl_config(test_site)
assert cfg["collect_details"] is False
assert cfg["max_products"] == 30
test_site2 = {"crawl_config": "{}"}
cfg2 = pa2.get_crawl_config(test_site2)
assert cfg2 == {}
print("OK")

db.close()
print("\n=== 모든 테스트 통과! ===")
