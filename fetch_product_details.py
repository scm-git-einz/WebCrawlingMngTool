"""
STEP 3: 상품 상세 페이지 수집

각 상품의 상세 페이지에서 커머스 공통 element를 수집합니다.
동일한 Stealth 브라우저 세션을 유지하며 순차 접근합니다.

봇 감지 우회:
  - 단일 브라우저 세션으로 자연스러운 탐색 패턴 유지
  - 요청 간 랜덤 딜레이 (1.5~3초)
  - 사람처럼 스크롤 동작
  - 외부 도메인 요청 차단
"""

import asyncio
import json
import os
import random
import re
from bs4 import BeautifulSoup

from browser import create_stealth_browser, human_delay, is_allowed_url
from config import (
    OUTPUT_DIR,
    MAX_PRODUCTS_DETAIL,
    REQUEST_DELAY_MIN,
    REQUEST_DELAY_MAX,
    PAGE_LOAD_TIMEOUT,
)


# ─── 상품 상세 HTML 파서 ─────────────────────────────────────────


def extract_detail_from_html(html: str, url: str) -> dict:
    """상품 상세 HTML에서 커머스 공통 element 추출"""
    soup = BeautifulSoup(html, "lxml")
    detail = {"product_url": url}

    # 에러 페이지 체크
    if soup.find("article", class_="error") or len(html) < 1000:
        detail["error"] = "에러 페이지 또는 존재하지 않는 상품"
        return detail

    # 상품 ID
    prd_match = re.search(r"prdNo=(\d+)", url)
    detail["product_id"] = prd_match.group(1) if prd_match else None

    # OG 메타
    og_title = soup.find("meta", {"property": "og:title"})
    og_image = soup.find("meta", {"property": "og:image"})
    detail["og_title"] = og_title["content"] if og_title and og_title.get("content") else None
    detail["og_image"] = og_image["content"] if og_image and og_image.get("content") else None

    # TMA 메타 (롯데면세점 커머스 메타)
    tma_prdNo = soup.find("meta", {"property": "tma:prdNo"})
    detail["tma_prdNo"] = tma_prdNo["content"] if tma_prdNo else None

    # 상품명
    name_div = soup.select_one("div.name")
    detail["product_name"] = name_div.get_text(strip=True) if name_div else detail.get("og_title")

    # 상품 코드
    code_p = soup.select_one("p.code")
    detail["product_code"] = code_p.get_text(strip=True) if code_p else None

    # 브랜드 (OG title에서 [브랜드명] 추출)
    if detail.get("og_title"):
        brand_match = re.match(r"\[(.+?)\]", detail["og_title"])
        detail["brand"] = brand_match.group(1) if brand_match else None
    else:
        detail["brand"] = None

    # 평점
    review_score = soup.select_one("#top_review_score, .score")
    review_count = soup.select_one("#prdasTotalScore_top, .counting")
    detail["rating"] = {
        "score": review_score.get_text(strip=True) if review_score else None,
        "count": review_count.get_text(strip=True) if review_count else None,
    }

    # 가격
    price = {}
    regular_price = soup.select_one("li.regular_price .currency")
    regular_won = soup.select_one("li.regular_price .won")
    benefit_rate = soup.select_one("li.benefit_price .rate")
    benefit_price = soup.select_one("li.benefit_price .price")
    benefit_sub = soup.select_one("li.benefit_price .sub_price")

    price["original_price_usd"] = regular_price.get_text(strip=True) if regular_price else None
    price["original_price_krw"] = regular_won.get_text(strip=True) if regular_won else None
    price["discount_rate"] = benefit_rate.get_text(strip=True) if benefit_rate else None
    price["selling_price_usd"] = benefit_price.get_text(strip=True) if benefit_price else None
    price["selling_price_krw"] = benefit_sub.get_text(strip=True) if benefit_sub else None

    # 최대혜택가
    max_benefit_price = soup.select_one("#prdMaxBenefitPriceArea .price")
    max_benefit_sub = soup.select_one("#prdMaxBenefitPriceArea .sub_price")
    price["max_benefit_price_usd"] = max_benefit_price.get_text(strip=True) if max_benefit_price else None
    price["max_benefit_price_krw"] = max_benefit_sub.get_text(strip=True) if max_benefit_sub else None
    detail["price"] = price

    # 이미지
    images = {}
    main_img = soup.select_one(".swiper-slide img[src*='prd-img']")
    if not main_img:
        main_img = soup.select_one("img[src*='prd-img']")
    images["main_image"] = main_img["src"] if main_img else detail.get("og_image")

    thumb_imgs = soup.select(".thumb_area img, .thumb_list img")
    if thumb_imgs:
        images["thumbnail_images"] = list(set(img.get("src", "") for img in thumb_imgs if img.get("src")))

    detail_imgs = soup.select(".prd_detail_img img, .product_detail img[src*='ckeditor']")
    if not detail_imgs:
        detail_imgs = soup.select("img[src*='ckeditor-img']")
    if detail_imgs:
        images["detail_images"] = list(set(img.get("src", "") for img in detail_imgs[:15] if img.get("src")))
    detail["images"] = images

    # 옵션
    options = []
    option_areas = soup.select(".optionArea select, select[name*='opt']")
    for sel_el in option_areas:
        opt_name = sel_el.get("title") or sel_el.get("name", "옵션")
        opt_values = [
            opt.get_text(strip=True)
            for opt in sel_el.find_all("option")
            if opt.get_text(strip=True)
            and "선택" not in opt.get_text(strip=True)
            and "옵션" not in opt.get_text(strip=True)
        ]
        if opt_values:
            options.append({"option_type": opt_name, "option_values": opt_values})
    detail["options"] = options if options else None

    # 상품 상세 설명
    detail_section = soup.select_one(".prd_detail, .product_detail_area, .detail_cont")
    detail["description"] = detail_section.get_text(strip=True)[:500] if detail_section else None

    # 쿠폰/혜택
    coupon_els = soup.select(".coupon_box li, .benefit_list li")
    if coupon_els:
        detail["coupons"] = [c.get_text(strip=True)[:100] for c in coupon_els[:5] if c.get_text(strip=True)]

    # 판매 상태
    soldout = soup.select_one(".btn_soldout, .soldout, .out_of_stock")
    buy_btn = soup.select_one(".btn_buy, .btn_cart, .btn_order, .bottomBtnArea .btn")
    if soldout:
        detail["stock_status"] = "품절"
    elif buy_btn:
        detail["stock_status"] = "판매중"
    else:
        detail["stock_status"] = None

    # 배송/인도 정보
    pickup = soup.select_one(".pickup_info, .delivery_area, .receive_info")
    detail["pickup_info"] = pickup.get_text(strip=True)[:200] if pickup else None

    return detail


# ─── 상품 상세 크롤링 ────────────────────────────────────────────


async def crawl_product_details(product_urls: list[str], max_count: int = MAX_PRODUCTS_DETAIL):
    """Stealth 브라우저로 상품 상세 페이지 순차 수집"""
    urls = product_urls[:max_count]
    print(f"[상세 크롤링] {len(urls)}개 상품 상세 페이지 수집 시작\n")

    results = []
    pw, browser, context, page = await create_stealth_browser(
        headless=True, mobile=True
    )

    try:
        for i, url in enumerate(urls, 1):
            # 도메인 확인 및 모바일 URL 변환
            if "m.kor.lottedfs.com" in url or "m.lottedfs.com" in url:
                mobile_url = url
            else:
                mobile_url = url.replace("kor.lottedfs.com", "m.kor.lottedfs.com")

            # 롯데면세점 도메인인지 확인
            if not is_allowed_url(mobile_url):
                print(f"  [{i}/{len(urls)}] 외부 도메인 스킵: {mobile_url}")
                continue

            print(f"  [{i}/{len(urls)}] {mobile_url}")
            try:
                await page.goto(mobile_url, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT)
                await human_delay(1.0, 2.0)

                html = await page.content()
                detail = extract_detail_from_html(html, mobile_url)
                results.append(detail)

                if detail.get("error"):
                    print(f"    -> [실패] {detail['error']}")
                else:
                    name = detail.get("product_name", "N/A")
                    brand = detail.get("brand", "")
                    status = detail.get("stock_status", "")
                    print(f"    -> {brand} | {name} [{status}]")

                # 처음 3개는 디버그용 HTML 저장
                if i <= 3 and not detail.get("error"):
                    with open(os.path.join(OUTPUT_DIR, f"detail_page_{i}.html"), "w", encoding="utf-8") as f:
                        f.write(html)

            except Exception as e:
                results.append({"product_url": mobile_url, "error": str(e)[:200]})
                print(f"    -> 오류: {e}")

            # 요청 간 랜덤 딜레이
            if i < len(urls):
                delay = random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX)
                await asyncio.sleep(delay)

    finally:
        await browser.close()
        await pw.stop()

    success = len([r for r in results if not r.get("error")])
    print(f"\n[상세 크롤링] 완료: 성공 {success}/{len(results)}개")
    return results


# ─── 메인 ────────────────────────────────────────────────────────


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    shop_path = os.path.join(OUTPUT_DIR, "02_shop_products.json")
    if not os.path.exists(shop_path):
        print("02_shop_products.json이 없습니다. 먼저 extract_data.py를 실행하세요.")
        return

    with open(shop_path, "r", encoding="utf-8") as f:
        shop_data = json.load(f)

    urls = [p["product_url"] for p in shop_data.get("products", []) if p.get("product_url")]
    print(f"총 상품 URL: {len(urls)}개, 상세 수집: {MAX_PRODUCTS_DETAIL}개\n")

    results = asyncio.run(crawl_product_details(urls, MAX_PRODUCTS_DETAIL))

    output_path = os.path.join(OUTPUT_DIR, "03_product_details.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\n결과 저장: {output_path}")


if __name__ == "__main__":
    main()
