"""
롯데면세점 크롤링 에이전트 - 통합 실행

전체 파이프라인을 순차 실행합니다:
  STEP 1: 랭킹 페이지 HTML 수집 (Playwright Stealth)
  STEP 2: 매장 정보 + 상품 목록 추출 (BeautifulSoup)
  STEP 3: 상품 상세 수집 (Playwright Stealth)
  STEP 4: 통합 결과 생성

사용법:
  python run.py              # 전체 실행
  python run.py --step 1     # 특정 단계만 실행
  python run.py --step 2 3   # 2~3단계만 실행
"""

import argparse
import os
import sys
import time

from config import OUTPUT_DIR


def run_step1():
    """STEP 1: 랭킹 페이지 HTML 수집"""
    print("\n" + "=" * 60)
    print("  STEP 1: 랭킹 페이지 HTML 수집 (Playwright Stealth)")
    print("=" * 60)
    from fetch_ranking import main as fetch_main
    fetch_main()


def run_step2():
    """STEP 2: 매장 정보 + 상품 목록 추출"""
    print("\n" + "=" * 60)
    print("  STEP 2: 매장 정보 + 상품 목록 추출 (BeautifulSoup)")
    print("=" * 60)
    from extract_data import main as extract_main
    extract_main()


def run_step3():
    """STEP 3: 상품 상세 수집"""
    print("\n" + "=" * 60)
    print("  STEP 3: 상품 상세 페이지 수집 (Playwright Stealth)")
    print("=" * 60)
    from fetch_product_details import main as detail_main
    detail_main()


def run_step4():
    """STEP 4: 통합 결과 생성"""
    print("\n" + "=" * 60)
    print("  STEP 4: 통합 결과 생성")
    print("=" * 60)
    from generate_final import main as final_main
    final_main()


STEPS = {
    1: run_step1,
    2: run_step2,
    3: run_step3,
    4: run_step4,
}


def main():
    parser = argparse.ArgumentParser(description="롯데면세점 크롤링 에이전트")
    parser.add_argument(
        "--step", type=int, nargs="*",
        help="실행할 단계 번호 (1~4). 미지정 시 전체 실행"
    )
    args = parser.parse_args()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    steps_to_run = args.step if args.step else [1, 2, 3, 4]

    print("=" * 60)
    print("  롯데면세점 크롤링 에이전트 (Stealth Mode)")
    print("=" * 60)
    print(f"  실행 단계: {steps_to_run}")
    print(f"  출력 디렉토리: {OUTPUT_DIR}")

    start = time.time()

    for step_num in steps_to_run:
        if step_num in STEPS:
            step_start = time.time()
            STEPS[step_num]()
            elapsed = time.time() - step_start
            print(f"\n  [STEP {step_num}] 완료 ({elapsed:.1f}초)")
        else:
            print(f"\n  [오류] 존재하지 않는 단계: {step_num}")

    total = time.time() - start
    print(f"\n{'=' * 60}")
    print(f"  전체 완료: {total:.1f}초")
    print(f"  결과: {OUTPUT_DIR}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
