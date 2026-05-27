"""Musinsa DNS/접속 진단"""
import sys
sys.path.insert(0, "D:\\crawling")
from core.browser import BrowserManager

bm = BrowserManager()
page = bm.create()

# 여러 URL 변형 시도
urls = [
    "https://musinsa.com",
    "https://www.musinsa.com",
    "https://www.musinsa.com/main/musinsa/ranking",
    "https://store.musinsa.com",
]

for url in urls:
    print(f"\n[diag] Trying: {url}")
    try:
        resp = page.goto(url, wait_until="domcontentloaded", timeout=15000)
        print(f"  Status: {resp.status if resp else 'None'}")
        print(f"  Final URL: {page.url}")
        title = page.title()
        try:
            print(f"  Title: {title}")
        except:
            print(f"  Title: (encoding issue)")
        break
    except Exception as e:
        err_msg = str(e)
        if len(err_msg) > 200:
            err_msg = err_msg[:200]
        print(f"  Error: {err_msg}")

bm.close()
print("\n[diag] Done")
