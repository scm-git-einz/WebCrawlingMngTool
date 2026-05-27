"""Test Olive Young DOM product scan"""
import sys
import os
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.browser import BrowserManager
from core.rule_analyzer import RuleAnalyzer, _JS_DOM_PRODUCT_SCAN
from core.network_interceptor import NetworkInterceptor

url = "https://www.oliveyoung.co.kr/store/main/getBestList.do"

bm = BrowserManager()
page = bm.create()

interceptor = NetworkInterceptor()
interceptor.start(page)

print("[test] navigating to olive young...")
page.goto(url, wait_until="domcontentloaded")
page.wait_for_timeout(5000)

# scroll trigger
page.evaluate("window.scrollTo(0, document.body.scrollHeight / 3)")
page.wait_for_timeout(2000)
page.evaluate("window.scrollTo(0, 0)")
page.wait_for_timeout(1000)

interceptor.stop(page)
captured = list(interceptor.captured)
print(f"[test] captured {len(captured)} requests")

# Test DOM product scan
print("[test] running DOM product scan...")
try:
    candidates = page.evaluate(_JS_DOM_PRODUCT_SCAN)
    if candidates:
        print(f"[test] {len(candidates)} candidates found:")
        for i, c in enumerate(candidates):
            print(f"  #{i+1} .{c['className']}: "
                  f"els={c.get('totalElements','?')}, "
                  f"price={c.get('count','?')}, "
                  f"ratio={c.get('ratio','?')}, "
                  f"score={c.get('score','?')}, "
                  f"img={c.get('sample',{}).get('hasImg','?')}, "
                  f"link={c.get('sample',{}).get('hasLink','?')}")
    else:
        print("[test] no candidates found!")
except Exception as e:
    print(f"[test] ERROR: {e}")

# Full analysis
print("\n[test] running full analysis...")
analyzer = RuleAnalyzer()
result = analyzer.analyze(page, url, captured)

if result:
    templates = result.get("templates", [])
    print(f"[test] {len(templates)} templates generated")
    for t in templates:
        cfg = t['config']
        if t['target'] == 'product_list':
            print(f"\n  product_list template:")
            print(f"    strategy: {t['strategy']}")
            print(f"    item_selector: {cfg.get('item_selector', 'N/A')}")
            print(f"    fields: {list(cfg.get('fields', {}).keys())}")
else:
    print("[test] analysis returned None")

bm.close()
print("\n[test] done")
