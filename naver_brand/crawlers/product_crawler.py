"""
상품 정보 수집 모듈 (ProductCrawler)

네이버 브랜드스토어에서 상품 목록과 상세 정보를 수집한다.
JS 속성 키, URL 패턴, DOM 셀렉터는 모두 config/settings.py 에 정의되어 있으며
이 파일에는 사이트 종속적인 하드코딩이 없다.
"""
import time
import random
import re

from playwright.sync_api import Page

import config.settings as settings
from config.settings import (
    MAX_PRODUCTS_DETAIL, REQUEST_DELAY_MIN, REQUEST_DELAY_MAX, PAGE_SIZE,
)
from utils.browser import create_stealth_browser
from utils.file_handler import save_json, get_timestamp
from utils.js_builder import (
    build_category_extract_js,
    build_products_extract_js,
    build_detail_extract_js,
    build_category_url,
    build_product_url,
)


class ProductCrawler:
    """네이버 브랜드스토어 상품 크롤러"""

    def __init__(self):
        self.page: Page | None = None
        self.products: list[dict] = []
        self.categories: list[dict] = []

    # ─── 공개 메서드 ──────────────────────────────────────────────

    def crawl_list(self) -> list[dict]:
        """전체 카테고리를 순회하며 상품 목록을 수집한다."""
        print("\n[product] ── 상품 목록 수집 시작 ──")

        ctx, self.page = create_stealth_browser()

        # 메인 페이지에서 카테고리 목록 확보
        print(f"[product] 메인 페이지 접속: {settings.TARGET_URL}")
        self.page.goto(settings.TARGET_URL, wait_until="domcontentloaded")
        self.page.wait_for_timeout(5000)

        self.categories = self._get_categories()

        if not self.categories:
            print("[product] 카테고리를 찾지 못함 → 메인 페이지 상품만 수집")
            self.products = self._extract_products_from_current_page()
            save_json(self.products, "product_list.json")
            return self.products

        print(f"[product] {len(self.categories)}개 카테고리 발견")

        # 각 카테고리 페이지 순회
        seen_ids = set()
        display_order = 0

        for cat_idx, cat in enumerate(self.categories, 1):
            cat_id = cat["id"]
            cat_name = cat["name"]
            safe_name = cat_name.encode("cp949", errors="replace").decode("cp949")
            print(f"\n[product] [{cat_idx}/{len(self.categories)}] 카테고리: {safe_name}")

            page_num = 1
            while True:
                url = build_category_url(cat_id, page_num)
                self.page.goto(url, wait_until="domcontentloaded")
                self.page.wait_for_timeout(3000)

                page_products, total_count = self._extract_products()

                if not page_products:
                    break

                new_count = 0
                for p in page_products:
                    pid = p.get("product_id", "")
                    if pid not in seen_ids:
                        seen_ids.add(pid)
                        display_order += 1
                        p["display_order"] = display_order
                        p["category"] = cat_name
                        self.products.append(p)
                        new_count += 1

                print(f"[product]   page {page_num}: {len(page_products)}개 (신규 {new_count}개, 총 {len(self.products)}개)")

                # 종료 조건
                if new_count == 0 or len(page_products) < PAGE_SIZE:
                    break

                page_num += 1
                delay = random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX)
                time.sleep(delay)

            # 카테고리 간 딜레이
            if cat_idx < len(self.categories):
                delay = random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX)
                time.sleep(delay)

        print(f"\n[product] 총 {len(self.products)}개 상품 수집 완료 (중복 제거 후)")
        save_json(self.products, "product_list.json")
        return self.products

    def crawl_details(self, products: list[dict] | None = None) -> list[dict]:
        """상품 상세 페이지를 방문하여 설명 텍스트를 보강한다."""
        print("\n[product] ── 상품 상세 수집 시작 ──")

        target_products = products or self.products
        if not target_products:
            print("[product] 수집할 상품이 없습니다")
            return []

        ctx, self.page = create_stealth_browser()

        targets = target_products[:MAX_PRODUCTS_DETAIL]
        print(f"[product] 상세 수집 대상: {len(targets)}개")

        details = []
        for i, prod in enumerate(targets, 1):
            product_name = prod.get("product_name", "N/A")[:30]

            # 이미 상세 텍스트가 있으면 스킵
            if prod.get("description") and prod["description"] != "N/A" and len(prod["description"]) > 20:
                print(f"[product] [{i}/{len(targets)}] {product_name}... (기존 상세 사용)")
                details.append(prod)
                continue

            detail_url = prod.get("product_url", "")
            if not detail_url:
                print(f"[product] [{i}/{len(targets)}] URL 없음 → 스킵")
                details.append(prod)
                continue

            print(f"[product] [{i}/{len(targets)}] {product_name}...")
            detail = self._fetch_product_detail(detail_url)
            merged = {**prod, **detail}
            details.append(merged)

            if i < len(targets):
                delay = random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX)
                time.sleep(delay)

        print(f"[product] 상세 수집 완료: {len(details)}개")
        save_json(details, "product_details.json")
        return details

    # ─── 매핑 기반 추출 ───────────────────────────────────────────

    def _get_categories(self) -> list[dict]:
        """매핑 기반 JS 로 카테고리 목록을 추출한다."""
        try:
            js_code = build_category_extract_js()
            cats = self.page.evaluate(js_code)
            return cats if cats else []
        except Exception as e:
            print(f"[product] 카테고리 추출 실패: {e}")
            return []

    def _extract_products(self) -> tuple[list[dict], int]:
        """매핑 기반 JS 로 현재 페이지의 상품을 추출한다."""
        try:
            js_code = build_products_extract_js()
            raw = self.page.evaluate(js_code)

            if not raw or not raw.get("products"):
                return [], 0

            products = [self._normalize(item) for item in raw["products"]]
            return products, raw.get("totalCount", 0)

        except Exception as e:
            print(f"[product] 상품 추출 실패: {e}")
            return [], 0

    def _extract_products_from_current_page(self) -> list[dict]:
        """현재 페이지에서 상품 추출 (카테고리 없이 메인 페이지용)"""
        products, _ = self._extract_products()
        return products

    def _fetch_product_detail(self, url: str) -> dict:
        """매핑 기반 JS 로 상품 상세 정보를 추출한다."""
        detail = {"description": "N/A", "detail_images": []}

        try:
            self.page.goto(url, wait_until="domcontentloaded")
            self.page.wait_for_timeout(3000)

            js_code = build_detail_extract_js()
            data = self.page.evaluate(js_code)

            if data:
                desc = data.get("description", "")
                detail["description"] = self._clean_html(desc)[:2000] if desc else "N/A"
                detail["detail_images"] = data.get("images", [])

        except Exception as e:
            print(f"[product]   상세 수집 오류: {e}")

        return detail

    # ─── 데이터 정규화 ────────────────────────────────────────────

    def _normalize(self, item: dict) -> dict:
        """추출된 상품 데이터를 표준 형태로 변환한다."""
        product_id = str(item.get("productNo") or item.get("id") or "N/A")

        original_price = item.get("salePrice", 0)
        selling_price = item.get("discountedPrice", 0) or original_price
        discount_rate = item.get("discountRate", 0)

        detail_text = item.get("detailText", "")
        description = self._clean_html(detail_text)[:2000] if detail_text else "N/A"

        return {
            "display_order": 0,
            "product_id": product_id,
            "product_name": item.get("name", "N/A"),
            "brand": item.get("brandName", "N/A"),
            "original_price": f"{original_price:,}원" if original_price else "N/A",
            "selling_price": f"{selling_price:,}원" if selling_price else "N/A",
            "discount_rate": f"{discount_rate}%" if discount_rate else "N/A",
            "image_url": item.get("imageUrl", "N/A"),
            "product_url": build_product_url(product_id),
            "review_count": item.get("reviewCount", 0),
            "average_score": item.get("averageScore", 0),
            "category": item.get("categoryName", "N/A"),
            "description": description,
        }

    @staticmethod
    def _clean_html(html_text: str) -> str:
        """HTML 태그를 제거하고 순수 텍스트를 반환한다."""
        if not html_text:
            return "N/A"
        cleaned = re.sub(r"<[^>]+>", " ", str(html_text))
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned if cleaned else "N/A"
