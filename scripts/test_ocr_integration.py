"""OCR 통합 테스트 - 이미지에서 가격 추출 (게시글 1건)

좌표 기반 매칭과 텍스트 기반 매칭 결과를 비교한다.
"""
import sys, io, os, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, "D:\\crawling")

from dotenv import load_dotenv
load_dotenv(os.path.join("D:\\crawling", ".env"))

from core.browser import BrowserManager
from core.ocr import UpstageOCR
from agents.cafe.engine import (
    _JS_CAFE_ARTICLE_EXTRACT,
    _extract_prices_from_text,
    _extract_prices_from_elements,
)

# 1. 브라우저로 게시글 접속
bm = BrowserManager()
page = bm.create()

url = "https://cafe.naver.com/ca-fe/cafes/14538121/articles/885130?fromPopular=true"
print(f"테스트 URL: {url}")
page.goto(url, wait_until="domcontentloaded", timeout=60000)
page.wait_for_timeout(5000)

# 2. JS로 본문 + 이미지 추출
detail = page.evaluate(_JS_CAFE_ARTICLE_EXTRACT)
print(f"\n제목: {detail['title']}")
print(f"본문 가격 (JS): {len(detail['prices'])}건")
for p in detail['prices']:
    print(f"  → {p}")

images = detail.get("images", [])
print(f"이미지: {len(images)}개")

# 3. 이미지 OCR (구조화 + 좌표)
ocr = UpstageOCR()
print(f"\n{'='*60}")
print("=== OCR 실행 (좌표 기반 매칭) ===")
print(f"{'='*60}")

for i, img in enumerate(images, 1):
    src = img.get("src", "")
    if not src.startswith("http"):
        continue
    print(f"\n[이미지 {i}] {src[:80]}...")

    # 구조화 결과 (elements + text)
    parsed = ocr.extract_with_elements(src)
    ocr_text = parsed.get("text", "")
    elements = parsed.get("elements", [])

    if ocr_text:
        print(f"OCR 텍스트 ({len(ocr_text)}자):")
        print(ocr_text[:500])

    # ── 좌표 기반 매칭 결과 ──
    print(f"\n--- 좌표 기반 매칭 (elements: {len(elements)}개) ---")
    if elements:
        # 상품명/가격 관련 요소 표시
        print("주요 요소:")
        for ei, elem in enumerate(elements):
            et = elem.get("text", "").replace("\n", " | ")
            cat = elem.get("category", "?")
            x, y = elem.get("x", 0), elem.get("y", 0)
            if len(et) > 2 and cat != "figure":
                print(f"  [{ei}] cat={cat} x={x:.3f} y={y:.3f} | {et[:80]}")

        prices_elem = _extract_prices_from_elements(
            elements, detail['title'],
        )
        print(f"\n추출된 가격-상품명 ({len(prices_elem)}건):")
        for p in prices_elem:
            print(f"  → 상품: '{p['product']}' | 가격: {p['price']}")
            print(f"     컨텍스트: {p['context'][:100]}")
    else:
        print("  elements 없음 → 텍스트 기반 fallback")

    # ── 텍스트 기반 매칭 결과 (비교용) ──
    print(f"\n--- 텍스트 기반 매칭 (비교용) ---")
    prices_text = _extract_prices_from_text(ocr_text, detail['title'])
    print(f"추출된 가격-상품명 ({len(prices_text)}건):")
    for p in prices_text:
        print(f"  → 상품: '{p['product']}' | 가격: {p['price']}")
        print(f"     컨텍스트: {p['context'][:100]}")

bm.close()
print("\nDone!")
