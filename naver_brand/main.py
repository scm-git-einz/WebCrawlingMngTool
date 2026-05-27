"""
네이버 브랜드스토어 크롤링 에이전트 - 통합 실행

전체 파이프라인을 순차 실행합니다:
  STEP 1: 매장 정보 수집   (매장명, 평점, 리뷰수, 주소)
  STEP 2: 상품 목록 수집   (상품명, 가격, 할인율, 이미지)
  STEP 3: 상품 상세 수집   (상세 설명 텍스트)
  STEP 4: 통합 결과 생성   (전체 데이터 병합 → crawl_result.json)

사용법:
  python main.py --store kerastase            # 케라스타즈 전체 실행
  python main.py --store esteelauderkorea     # 에스티 로더 전체 실행
  python main.py --store kerastase --step 1   # 특정 단계만
"""
import argparse
import os
import sys
import time

# ─── 패키지 경로 설정 ─────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(__file__))

import config.settings as settings
from config.settings import reload_for_store
from utils.browser import close_browser
from utils.file_handler import save_json, load_json, get_timestamp
from crawlers.store_crawler import StoreCrawler
from crawlers.product_crawler import ProductCrawler


def run_step1() -> dict:
    """STEP 1: 매장 정보 수집"""
    print("\n" + "=" * 60)
    print("  STEP 1: 매장 정보 수집")
    print("=" * 60)
    crawler = StoreCrawler()
    return crawler.crawl()


def run_step2() -> list[dict]:
    """STEP 2: 상품 목록 수집"""
    print("\n" + "=" * 60)
    print("  STEP 2: 상품 목록 수집")
    print("=" * 60)
    crawler = ProductCrawler()
    return crawler.crawl_list()


def run_step3() -> list[dict]:
    """STEP 3: 상품 상세 수집"""
    print("\n" + "=" * 60)
    print("  STEP 3: 상품 상세 수집")
    print("=" * 60)

    # 이전 단계 결과 로드
    products = load_json("product_list.json")
    if not products:
        print("[오류] product_list.json 이 없습니다. STEP 2를 먼저 실행하세요.")
        return []

    crawler = ProductCrawler()
    return crawler.crawl_details(products)


def run_step4(store_info: dict = None, product_details: list = None) -> dict:
    """STEP 4: 통합 결과 생성"""
    print("\n" + "=" * 60)
    print("  STEP 4: 통합 결과 생성")
    print("=" * 60)

    # 각 단계 결과 로드 (인자가 없으면 파일에서 읽기)
    if store_info is None:
        store_info = load_json("store_info.json") or {}
    if product_details is None:
        product_details = load_json("product_details.json") or []

    product_list = load_json("product_list.json") or []

    # 통합 결과 구성
    result = {
        "crawl_meta": {
            "target_url": settings.TARGET_URL,
            "crawl_date": get_timestamp(),
            "crawl_method": "Playwright Stealth + BeautifulSoup",
            "tool": "naver_brand_crawler",
        },
        "store_info": store_info,
        "products": product_details if product_details else product_list,
        "total_products_listed": len(product_list),
        "total_products_detailed": len(product_details),
    }

    save_json(result, "crawl_result.json")

    print(f"\n[결과] 매장 정보: {store_info.get('store_name', 'N/A')}")
    print(f"[결과] 목록 상품 수: {len(product_list)}")
    print(f"[결과] 상세 수집 수: {len(product_details)}")
    print(f"[결과] 최종 파일: {settings.OUTPUT_DIR}/crawl_result.json")

    return result


def main():
    parser = argparse.ArgumentParser(
        description="네이버 브랜드스토어 크롤링 에이전트"
    )
    parser.add_argument(
        "--store", type=str, default=None,
        help="브랜드스토어 슬러그 (예: kerastase, esteelauderkorea)"
    )
    parser.add_argument(
        "--step", type=int, nargs="*",
        help="실행할 단계 번호 (1~4). 미지정 시 전체 실행"
    )
    args = parser.parse_args()

    # --store 인자가 있으면 설정 갱신
    if args.store:
        reload_for_store(args.store)

    os.makedirs(settings.OUTPUT_DIR, exist_ok=True)

    steps_to_run = args.step if args.step else [1, 2, 3, 4]

    print("=" * 60)
    print("  네이버 브랜드스토어 크롤링 에이전트")
    print(f"  대상: {settings.STORE_SLUG}")
    print("=" * 60)
    print(f"  실행 단계: {steps_to_run}")
    print(f"  대상 URL:  {settings.TARGET_URL}")
    print(f"  출력 경로: {settings.OUTPUT_DIR}")

    start = time.time()

    store_info = None
    product_details = None

    try:
        for step_num in steps_to_run:
            step_start = time.time()

            if step_num == 1:
                store_info = run_step1()
            elif step_num == 2:
                run_step2()
            elif step_num == 3:
                product_details = run_step3()
            elif step_num == 4:
                run_step4(store_info, product_details)
            else:
                print(f"\n  [오류] 존재하지 않는 단계: {step_num}")
                continue

            elapsed = time.time() - step_start
            print(f"\n  [STEP {step_num}] 완료 ({elapsed:.1f}초)")

    except KeyboardInterrupt:
        print("\n\n[중단] 사용자에 의해 중단되었습니다.")
    except Exception as e:
        print(f"\n[오류] 예상치 못한 오류: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 브라우저 정리
        close_browser()

    total = time.time() - start
    print(f"\n{'=' * 60}")
    print(f"  전체 완료: {total:.1f}초")
    print(f"  결과: {settings.OUTPUT_DIR}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
