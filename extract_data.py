"""
STEP 2: 매장 정보 + 상품 목록 추출

수집된 HTML에서 BeautifulSoup으로 매장 정보와 상품 목록을 추출합니다.
노출 순서(display_order)를 보존하며, 중복 상품 ID를 제거합니다.

LLM 판단: BeautifulSoup 사용
- HTML이 이미 렌더링된 상태이므로 정적 파싱으로 충분
- CSS 선택자 기반으로 구조화된 데이터 추출
"""

import json
import os
import re
from bs4 import BeautifulSoup

from config import OUTPUT_DIR


# ─── CSS 선택자 정의 ──────────────────────────────────────────────

SELECTORS = {
    "categories": "li.bestPrd_cate_li > a",
    "product_list": "div.goods_list ul.unit_LSTE",
    "product_card": "div.goods_list ul.unit_LSTE li",
    "rank": "span.unit_no",
    "image": "div.unit_img img",
    "brand_kor": "span.brand > i.kor",
    "brand_eng": "span.brand > i.eng",
    "product_name": "span.name",
    "original_price": "span.price01",
    "selling_price": "strong.price02",
    "discount_rate": "i.sale",
    "krw_price": "span.price03",
}


# ─── 매장 정보 추출 ──────────────────────────────────────────────


def extract_shop_info(soup: BeautifulSoup) -> dict:
    """매장(랭킹 페이지) 기본 정보 추출"""
    title = soup.find("title")
    og_desc = soup.find("meta", {"property": "og:description"})
    og_url = soup.find("meta", {"property": "og:url"})

    categories = []
    for a_tag in soup.select(SELECTORS["categories"]):
        cat_name = a_tag.get_text(strip=True)
        cat_cd = a_tag.get("data-catcd") or a_tag.get("data-dispshopno") or ""
        onclick = a_tag.get("onclick", "")
        if not cat_cd:
            match = re.search(r"(\d{8,})", onclick)
            if match:
                cat_cd = match.group(1)
        categories.append({"name": cat_name, "code": cat_cd})

    return {
        "shop_name": "롯데면세점 랭킹/트렌딩",
        "shop_url": og_url["content"] if og_url else "https://m.kor.lottedfs.com/kr/shopmain/rankingTrending/main",
        "shop_description": og_desc["content"] if og_desc else "",
        "page_title": title.get_text(strip=True) if title else "",
        "categories": categories,
        "source": "mobile (m.kor.lottedfs.com)",
    }


# ─── 상품 데이터 추출 ────────────────────────────────────────────


def extract_product_from_li(li, section_name: str = "베스트셀러") -> dict | None:
    """개별 상품 li 요소에서 데이터 추출"""
    a_tag = li.find("a", class_="unit_link")
    if not a_tag:
        return None

    product = {}

    # 상품 ID (href에서 추출)
    href = a_tag.get("href", "")
    prd_match = re.search(r"(\d{10,})", href)
    product["product_id"] = prd_match.group(1) if prd_match else None

    # GA 이벤트 정보
    product["ga_category"] = a_tag.get("data-gaevtcategory", "")
    product["ga_action"] = a_tag.get("data-gaevtaction", "")

    # 순위
    rank_span = li.find("span", class_="unit_no")
    product["rank"] = int(rank_span.get_text(strip=True)) if rank_span else None

    # 이미지
    img = li.find("img")
    if img:
        product["image_url"] = img.get("src", "") or img.get("data-src", "")
        if not product.get("product_name"):
            product["product_name"] = img.get("alt", "")

    # 브랜드
    brand_span = li.find("span", class_="brand")
    if brand_span:
        kor = brand_span.find("i", class_="kor")
        eng = brand_span.find("i", class_="eng")
        product["brand"] = kor.get_text(strip=True) if kor else ""
        product["brand_en"] = eng.get_text(strip=True) if eng else ""

    # 상품명
    name_span = li.find("span", class_="name")
    if name_span:
        product["product_name"] = name_span.get_text(strip=True)

    # 가격 추출
    price01 = li.find("span", class_="price01")
    price02 = li.find("strong", class_="price02")
    price03 = li.find("span", class_="price03")
    sale = li.find("i", class_="sale")

    product["original_price"] = price01.get_text(strip=True) if price01 else None

    # 판매가: sale 태그 제거 후 추출 (할인율 텍스트가 섞이는 문제 방지)
    if price02:
        for child_sale in price02.find_all("i", class_="sale"):
            child_sale.extract()
        product["selling_price"] = price02.get_text(strip=True)
    else:
        product["selling_price"] = None

    product["krw_price"] = price03.get_text(strip=True) if price03 else None
    product["discount_rate"] = sale.get_text(strip=True) if sale else None

    # 뱃지
    badges = []
    for badge in li.select(".badge, .icon, .label, .tag"):
        text = badge.get_text(strip=True)
        if text:
            badges.append(text)
    if "hit" in li.get("class", []):
        badges.append("HIT")
    product["badges"] = badges if badges else None

    # 상품 상세 URL
    if product.get("product_id"):
        product["product_url"] = (
            f"https://m.kor.lottedfs.com/kr/product/productDetail?prdNo={product['product_id']}"
        )

    product["section"] = section_name
    return product


def extract_all_products(soup: BeautifulSoup) -> list[dict]:
    """전체 상품을 노출 순서대로 추출 (중복 제거)"""
    products = []
    seen_ids = set()
    display_order = 0

    for li in soup.select(SELECTORS["product_card"]):
        product = extract_product_from_li(li)
        if not product or not product.get("product_name"):
            continue

        pid = product.get("product_id")
        if pid and pid in seen_ids:
            continue
        if pid:
            seen_ids.add(pid)

        display_order += 1
        product["display_order"] = display_order
        products.append(product)

    return products, seen_ids


def extract_product_from_ajax_li(li, category: str = "") -> dict | None:
    """
    AJAX HTML(getCategoryPrdasRanking) 전용 상품 파서

    AJAX HTML 구조:
      <li>
        <a class="gaEvtTg" href="javascript:ga_adltCheckPrdDtlMove(20000845220,...)">
          <div class="display_unit">
            <div class="number">1</div>
            <div class="thumb"><img data-src="..." alt="..."/></div>
            <div class="info">
              <div class="name">브랜드명</div>
              <div class="title">상품명</div>
            </div>
          </div>
        </a>
      </li>
    """
    a_tag = li.find("a", class_="gaEvtTg")
    if not a_tag:
        return None

    unit = li.find("div", class_="display_unit")
    if not unit:
        return None

    product = {}

    # 상품 ID (JavaScript href에서 추출)
    href = a_tag.get("href", "")
    pid_match = re.search(r"(\d{10,})", href)
    product["product_id"] = pid_match.group(1) if pid_match else None

    if not product["product_id"]:
        return None

    # 순위
    number_div = unit.find("div", class_="number")
    product["rank"] = int(number_div.get_text(strip=True)) if number_div else None

    # 브랜드 (div.name)
    info_div = unit.find("div", class_="info")
    if info_div:
        name_div = info_div.find("div", class_="name")
        title_div = info_div.find("div", class_="title")
        product["brand"] = name_div.get_text(strip=True) if name_div else ""
        product["product_name"] = title_div.get_text(strip=True) if title_div else ""
    else:
        product["brand"] = ""
        product["product_name"] = ""

    # 이미지 (data-src 또는 src)
    img = unit.find("img")
    if img:
        product["image_url"] = img.get("data-src", "") or img.get("src", "")

    # GA 이벤트 정보
    product["ga_category"] = a_tag.get("data-gaevtcategory", "")
    product["ga_action"] = a_tag.get("data-gaevtaction", "")

    # 상품 상세 URL
    product["product_url"] = (
        f"https://m.kor.lottedfs.com/kr/product/productDetail?prdNo={product['product_id']}"
    )

    product["section"] = category
    return product


def extract_products_from_ajax(ajax_data: list[dict], seen_ids: set, start_order: int) -> list[dict]:
    """AJAX HTML 조각에서 추가 상품 추출

    AJAX HTML은 DOM과 구조가 다름:
      - ul#categoryPrdasRanking_ul > li (direct children만 상품, 내부 li는 리뷰)
      - a.gaEvtTg (NOT a.unit_link)
      - div.display_unit > div.number, div.info > div.name(브랜드), div.title(상품명)
    """
    products = []
    display_order = start_order

    for item in ajax_data:
        html = item.get("html", "") if isinstance(item, dict) else item
        category = item.get("category", "AJAX") if isinstance(item, dict) else "AJAX"

        frag_soup = BeautifulSoup(html, "lxml")

        # categoryPrdasRanking_ul의 직접 자식 li만 (리뷰 li 제외)
        ul = frag_soup.find("ul", id="categoryPrdasRanking_ul")
        if ul:
            lis = ul.find_all("li", recursive=False)
        else:
            # 트렌딩/추천 등 다른 형식
            lis = frag_soup.find_all("li", recursive=False)

        for li in lis:
            product = extract_product_from_ajax_li(li, category=category)
            if not product or not product.get("product_name"):
                continue

            pid = product.get("product_id")
            if pid and pid in seen_ids:
                continue
            if pid:
                seen_ids.add(pid)

            display_order += 1
            product["display_order"] = display_order
            products.append(product)

    return products


# ─── 메인 ────────────────────────────────────────────────────────


def main():
    ranking_path = os.path.join(OUTPUT_DIR, "mobile_ranking.html")
    if not os.path.exists(ranking_path):
        print("mobile_ranking.html이 없습니다. 먼저 fetch_ranking.py를 실행하세요.")
        return None

    print("[1] DOM HTML 파싱 중...")
    with open(ranking_path, "r", encoding="utf-8") as f:
        html = f.read()
    soup = BeautifulSoup(html, "lxml")
    print(f"  HTML 길이: {len(html):,} chars")

    # 매장 정보
    print("\n[2] 매장 정보 추출...")
    shop_info = extract_shop_info(soup)
    print(f"  매장: {shop_info['shop_name']}")
    print(f"  카테고리: {len(shop_info['categories'])}개")
    for cat in shop_info["categories"]:
        print(f"    - {cat['name']} ({cat['code']})")

    # 상품 목록 - DOM HTML
    print("\n[3] 상품 목록 추출 (DOM)...")
    dom_products, seen_ids = extract_all_products(soup)
    print(f"  DOM 상품: {len(dom_products)}개")

    # AJAX HTML 조각에서 추가 상품 추출
    ajax_products = []
    ajax_path = os.path.join(OUTPUT_DIR, "ajax_fragments.json")
    if os.path.exists(ajax_path):
        print("\n[4] AJAX HTML 조각에서 추가 상품 추출...")
        with open(ajax_path, "r", encoding="utf-8") as f:
            ajax_fragments = json.load(f)
        ajax_products = extract_products_from_ajax(
            ajax_fragments, seen_ids, start_order=len(dom_products)
        )
        print(f"  AJAX 추가 상품: {len(ajax_products)}개")

    # 통합
    products = dom_products + ajax_products
    print(f"\n  총 상품: {len(products)}개 (DOM: {len(dom_products)} + AJAX: {len(ajax_products)})")

    for p in products[:5]:
        print(
            f"  [{p.get('display_order'):>3}] {p.get('brand', ''):12} | "
            f"{p.get('product_name', '')[:30]:30} | "
            f"{p.get('selling_price', 'N/A'):>10} ({p.get('discount_rate', '')})"
        )
    if len(products) > 5:
        print(f"  ... 외 {len(products) - 5}개")

    # 저장
    result = {
        "shop_info": shop_info,
        "products": products,
        "total_products": len(products),
    }

    output_path = os.path.join(OUTPUT_DIR, "02_shop_products.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"\n결과 저장: {output_path}")
    return result


if __name__ == "__main__":
    main()
