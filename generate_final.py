"""
STEP 4: 통합 결과 생성

상품 목록에 상세 데이터를 병합하여 최종 JSON을 생성합니다.
"""

import json
import os
from datetime import datetime

from config import OUTPUT_DIR, TARGET_URL, MOBILE_RANKING_URL


def main():
    # 매장/상품 목록 로드
    with open(os.path.join(OUTPUT_DIR, "02_shop_products.json"), "r", encoding="utf-8") as f:
        shop_data = json.load(f)

    # 상품 상세 로드
    details_path = os.path.join(OUTPUT_DIR, "03_product_details.json")
    if os.path.exists(details_path):
        with open(details_path, "r", encoding="utf-8") as f:
            details = json.load(f)
    else:
        details = []

    # 상세 데이터를 product_id로 매핑
    detail_map = {}
    for d in details:
        pid = d.get("product_id") or d.get("tma_prdNo")
        if pid:
            detail_map[pid] = d

    # 상품 목록에 상세 데이터 병합
    products = shop_data.get("products", [])
    for p in products:
        pid = p.get("product_id")
        if pid and pid in detail_map:
            p["detail"] = detail_map[pid]

    detail_count = len([p for p in products if p.get("detail") and not p["detail"].get("error")])

    # 사이트 분석 결과
    site_analysis = {
        "is_dynamic": True,
        "recommended_tool": "playwright",
        "reason": (
            "롯데면세점은 SPA 구조이며, kor.lottedfs.com 데스크톱은 CloudFront 점검 이미지를 반환. "
            "모바일(m.kor.lottedfs.com)을 통한 Playwright Stealth 접근이 유효함."
        ),
        "access_method": "Playwright Stealth 모바일 (m.kor.lottedfs.com)",
        "bot_bypass": {
            "playwright_stealth": "WebDriver 플래그 제거, navigator 속성 위장",
            "user_agent": "iPhone Safari 17.5 (모바일)",
            "headers": "Accept, Accept-Language, Sec-Fetch-* 등 실제 브라우저 헤더",
            "behavior": "랜덤 딜레이, 사람처럼 스크롤, 세션 유지",
            "domain_filter": "롯데면세점 도메인만 허용, 외부 요청 차단",
        },
        "blocked_methods": [
            "requests → kor.lottedfs.com (CloudFront가 PNG 점검 이미지 반환)",
            "Playwright headless → kor.lottedfs.com (동일하게 차단)",
        ],
        "working_methods": [
            "Playwright Stealth mobile → m.kor.lottedfs.com (모바일 전체 페이지 접근 가능)",
        ],
        "api_endpoints_discovered": [
            "POST /kr/shopmain/home/homeConerInfo?conrId=homeBestSeller",
            "GET /kr/shopmain/rankingTrending/getCategoryPrdasRanking",
            "GET /kr/shopmain/rankingTrending/getTrendingPrdListAjax",
            "GET /kr/shopmain/rankingTrending/getRecomBestListAjax",
        ],
        "product_detail_url_pattern": "https://m.kor.lottedfs.com/kr/product/productDetail?prdNo={product_id}",
    }

    now = datetime.now()
    final_result = {
        "crawl_meta": {
            "target_url": TARGET_URL,
            "actual_url": MOBILE_RANKING_URL,
            "crawl_date": now.strftime("%Y-%m-%d %H:%M:%S"),
            "crawl_method": "Playwright Stealth (mobile) + BeautifulSoup",
        },
        "site_analysis": site_analysis,
        "shop_info": shop_data.get("shop_info", {}),
        "products": products,
        "total_products": len(products),
        "detail_collected": detail_count,
    }

    output_path = os.path.join(OUTPUT_DIR, "crawl_result.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(final_result, f, indent=2, ensure_ascii=False)

    print(f"최종 결과 생성 완료:")
    print(f"  매장: {final_result['shop_info'].get('shop_name', 'N/A')}")
    print(f"  카테고리: {len(final_result['shop_info'].get('categories', []))}개")
    print(f"  상품 목록: {final_result['total_products']}개")
    print(f"  상세 수집: {final_result['detail_collected']}개")
    print(f"  결과 파일: {output_path}")


if __name__ == "__main__":
    main()
