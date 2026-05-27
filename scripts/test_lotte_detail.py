"""롯데면세점 상세 수집 개선 테스트 — 단일 상품 상세 페이지 추출 검증"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from urllib.parse import urlparse
from core.browser import BrowserManager

DETAIL_URLS = [
    "https://kor.lottedfs.com/kr/product/productDetail?prdNo=20000388497&adltPrdYn=N",
    "https://kor.lottedfs.com/kr/product/productDetail?prdNo=20000729162&adltPrdYn=N",
]

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from agents.product.engine import _JS_EXTRACT_DETAIL

def main():
    bm = BrowserManager()
    domain = urlparse(DETAIL_URLS[0]).hostname
    try:
        page = bm.create(cookie_domain=domain)

        for url in DETAIL_URLS:
            print(f"\n{'='*60}")
            print(f"URL: {url}")
            page.goto(url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(5000)
            print(f"Title: {page.title()}")

            detail = page.evaluate(_JS_EXTRACT_DETAIL)

            desc = detail.get("description", "")
            print(f"\n[description] ({len(desc)}자)")
            print(f"  {desc[:200]}{'...' if len(desc) > 200 else ''}")

            spec = detail.get("spec", {})
            print(f"\n[spec] ({len(spec)}항목)")
            for k, v in list(spec.items())[:10]:
                print(f"  {k}: {v[:60]}")

            imgs = detail.get("detail_images", [])
            print(f"\n[detail_images] ({len(imgs)}개)")
            for img in imgs[:5]:
                print(f"  {img[:100]}")

    finally:
        bm.close()

if __name__ == "__main__":
    main()
