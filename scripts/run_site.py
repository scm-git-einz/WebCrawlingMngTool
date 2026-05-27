"""특정 사이트 수집 실행"""
import sys
sys.path.insert(0, "D:\\crawling")
from core.engine import CrawlEngine

site_id = int(sys.argv[1]) if len(sys.argv) > 1 else 6
print(f"=== Site ID {site_id} 수집 시작 ===\n")
engine = CrawlEngine()
engine.run_site(site_id)
