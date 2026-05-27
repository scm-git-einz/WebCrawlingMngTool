"""기존 사이트 호환성 테스트 - 분석만 수행 (크롤링 없이)"""
import sys
import json
sys.path.insert(0, "D:\\crawling")
from core.db import CrawlDB
from core.browser import BrowserManager
from core.rule_analyzer import RuleAnalyzer
from core.network_interceptor import NetworkInterceptor

db = CrawlDB()

# 테스트할 사이트 ID들 (이미 잘 동작하던 사이트)
test_sites = [3, 5, 6, 7]  # 올리브영, 29CM, W컨셉, KREAM

for site_id in test_sites:
    site = db.get_site(site_id)
    print(f"\n{'='*60}")
    print(f"Site {site_id}: {site['site_name']} ({site['site_url'][:50]})")
    print(f"{'='*60}")

    # 기존 플랫폼 정보 확인
    old_pid = site.get("platform_id")
    if old_pid:
        old_templates = db.get_templates_for_platform(old_pid)
        old_prod_tmpl = None
        for t in old_templates:
            if t["target"] == "product_list":
                old_prod_tmpl = t["config"]
                break

        if old_prod_tmpl:
            print(f"  [기존] product_list:")
            print(f"    item_selector: {old_prod_tmpl.get('item_selector')}")
            fields = old_prod_tmpl.get("fields", {})
            for fname, fspec in fields.items():
                sel = fspec.get("selector", "N/A")
                print(f"    {fname}: {sel}")

    # 재분석 (실제로 페이지 로드)
    bm = BrowserManager()
    try:
        # 브라우저 설정
        platform = db.get_platform(old_pid) if old_pid else None
        browser_config = platform.get("browser", {}) if platform else {}
        page = bm.create(browser_config)

        # 네트워크 인터셉터
        interceptor = NetworkInterceptor()
        interceptor.start(page)

        # 페이지 로드
        page.goto(site["site_url"], wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)

        # 스크롤
        for _ in range(3):
            page.evaluate("window.scrollBy(0, window.innerHeight)")
            page.wait_for_timeout(1000)

        captured = interceptor.stop(page)

        # 분석
        analyzer = RuleAnalyzer()
        result = analyzer.analyze(page, site["site_url"], captured)

        if result:
            templates = result.get("templates", [])
            for tmpl in templates:
                if tmpl["target"] == "product_list":
                    config = tmpl["config"]
                    print(f"\n  [새로] product_list (strategy={tmpl['strategy']}):")
                    if "item_selector" in config:
                        print(f"    item_selector: {config.get('item_selector')}")
                        fields = config.get("fields", {})
                        for fname, fspec in fields.items():
                            sel = fspec.get("selector", "N/A")
                            print(f"    {fname}: {sel}")
                    else:
                        keys = list(config.keys())[:5]
                        print(f"    config keys: {keys}")
        else:
            print("  분석 실패!")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"  오류: {e}")
    finally:
        bm.close()

db.close()
print("\n완료!")
