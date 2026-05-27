"""
STEP 1: 랭킹 페이지 HTML 수집

Playwright Stealth 모바일 브라우저로 롯데면세점 랭킹/트렌딩 페이지의
렌더링된 HTML을 수집합니다.

봇 감지 우회:
  - playwright-stealth: WebDriver 플래그 제거, navigator 속성 위장
  - 모바일 User-Agent (iPhone Safari 17.5)
  - 실제 브라우저 헤더 (Accept, Accept-Language, Sec-Fetch-*)
  - 사람처럼 랜덤 딜레이/스크롤 패턴

수집 전략:
  1. Stealth 브라우저로 랭킹 페이지 접속 (세션/쿠키 획득)
  2. 브라우저 내부에서 AJAX API 직접 호출 (모든 카테고리, 모든 페이지)
  3. DOM HTML + AJAX HTML 조각 모두 저장
"""

import asyncio
import json
import os

from browser import (
    create_stealth_browser,
    human_delay,
    human_scroll,
    wait_for_content,
    is_allowed_url,
)
from config import (
    MOBILE_HOME_URL,
    MOBILE_RANKING_URL,
    OUTPUT_DIR,
    PAGE_LOAD_TIMEOUT,
)

# 카테고리 목록 (사이트에서 확인된 코드)
CATEGORIES = [
    {"name": "주류", "code": "10055924"},
    {"name": "스킨케어", "code": "10031760"},
    {"name": "메이크업", "code": "10031766"},
    {"name": "향수/바디/헤어", "code": "10031772"},
    {"name": "뷰티 디바이스", "code": "10079706"},
    {"name": "가방/지갑", "code": "10031778"},
    {"name": "시계/주얼리", "code": "10031784"},
    {"name": "아이웨어/잡화", "code": "10031790"},
    {"name": "패션/슈즈", "code": "10031796"},
    {"name": "스포츠/레저", "code": "10031802"},
    {"name": "건강/가공식품", "code": "10031808"},
    {"name": "디지털/가전", "code": "10031814"},
    {"name": "리빙/헬스케어", "code": "10031820"},
    {"name": "키즈/베이비", "code": "10031832"},
]


async def fetch_ranking_html() -> str:
    """모바일 Stealth 브라우저로 랭킹 페이지 HTML 수집"""
    pw, browser, context, page = await create_stealth_browser(
        headless=True, mobile=True
    )

    ranking_html = ""

    try:
        # 1. 홈페이지 접속 (쿠키/세션 획득 + Incapsula 챌린지 통과)
        print("[STEP 1] 홈페이지 접속 (세션 획득)...")
        await page.goto(MOBILE_HOME_URL, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT)
        await human_delay(3.0, 5.0)
        print(f"  URL: {page.url}")
        home_html_len = len(await page.content())
        print(f"  홈 HTML: {home_html_len:,} chars")

        # 2. 랭킹 페이지로 이동
        print("\n[STEP 2] 랭킹 페이지 이동...")
        await page.goto(MOBILE_RANKING_URL, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT)
        await human_delay(3.0, 5.0)

        # 상품 카드 로드 대기
        loaded = await wait_for_content(page, "div.goods_list", timeout=15000)
        print(f"  상품 목록: {'감지됨' if loaded else '미감지'}")

        # 스크롤하여 초기 데이터 로드
        await human_scroll(page, total_scrolls=10, scroll_px=500)
        await human_delay(2.0, 3.0)

        # DOM HTML 캡처 (초기 페이지)
        ranking_html = await page.content()
        dom_count = await page.evaluate(
            "() => document.querySelectorAll('div.goods_list ul.unit_LSTE li a.unit_link').length"
        )
        print(f"  DOM 상품 카드: {dom_count}개")
        print(f"  HTML: {len(ranking_html):,} chars")

        # 3. 브라우저 내부에서 AJAX API 직접 호출 (모든 카테고리/페이지)
        print("\n[STEP 3] AJAX API로 전체 카테고리 상품 수집...")
        ajax_fragments = []

        for cat in CATEGORIES:
            cat_name = cat["name"]
            cat_code = cat["code"]
            page_num = 1

            while page_num <= 10:  # 최대 10페이지
                try:
                    ajax_html = await page.evaluate(f"""
                        async () => {{
                            const resp = await fetch(
                                '/kr/shopmain/rankingTrending/getCategoryPrdasRanking'
                                + '?dispShopNo={cat_code}'
                                + '&cateNm={cat_name}'
                                + '&curPageNo={page_num}'
                                + '&cntPerPage=20',
                                {{
                                    method: 'GET',
                                    headers: {{
                                        'X-Requested-With': 'XMLHttpRequest',
                                        'Accept': 'text/html, */*; q=0.01',
                                    }}
                                }}
                            );
                            return await resp.text();
                        }}
                    """)

                    if ajax_html and len(ajax_html) > 200:
                        ajax_fragments.append({
                            "category": cat_name,
                            "category_code": cat_code,
                            "page": page_num,
                            "html": ajax_html,
                            "size": len(ajax_html),
                        })
                        page_num += 1
                        await human_delay(0.3, 0.8)
                    else:
                        break  # 빈 페이지 = 더 이상 데이터 없음

                except Exception as e:
                    print(f"    {cat_name} page {page_num} 오류: {e}")
                    break

            total_pages = page_num - 1
            if total_pages > 0:
                print(f"  {cat_name}: {total_pages}페이지 수집")

        # 트렌딩/추천 상품도 수집
        print("\n  트렌딩/추천 상품 수집...")
        for api_name, api_path in [
            ("트렌딩", "/kr/shopmain/rankingTrending/getTrendingPrdListAjax?gaevtlabel=trending"),
            ("추천 베스트", "/kr/shopmain/rankingTrending/getRecomBestListAjax?dispConrNm=recommend"),
        ]:
            try:
                ajax_html = await page.evaluate(f"""
                    async () => {{
                        const resp = await fetch('{api_path}', {{
                            method: 'GET',
                            headers: {{ 'X-Requested-With': 'XMLHttpRequest' }}
                        }});
                        return await resp.text();
                    }}
                """)
                if ajax_html and len(ajax_html) > 200:
                    ajax_fragments.append({
                        "category": api_name,
                        "category_code": "",
                        "page": 1,
                        "html": ajax_html,
                        "size": len(ajax_html),
                    })
                    print(f"  {api_name}: {len(ajax_html):,} chars")
            except Exception as e:
                print(f"  {api_name} 오류: {e}")

        # 4. 저장
        print(f"\n[결과]")
        print(f"  DOM HTML: {len(ranking_html):,} chars ({dom_count}개 상품)")
        print(f"  AJAX 조각: {len(ajax_fragments)}개")
        total_ajax_size = sum(f["size"] for f in ajax_fragments)
        print(f"  AJAX 총 크기: {total_ajax_size:,} chars")

        # DOM HTML 저장
        html_path = os.path.join(OUTPUT_DIR, "mobile_ranking.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(ranking_html)
        print(f"  DOM HTML: {html_path}")

        # AJAX 조각 저장
        ajax_path = os.path.join(OUTPUT_DIR, "ajax_fragments.json")
        with open(ajax_path, "w", encoding="utf-8") as f:
            json.dump(ajax_fragments, f, indent=2, ensure_ascii=False)
        print(f"  AJAX 조각: {ajax_path}")

    except Exception as e:
        print(f"\n[오류] {e}")
        try:
            ranking_html = await page.content()
            err_path = os.path.join(OUTPUT_DIR, "error_page.html")
            with open(err_path, "w", encoding="utf-8") as f:
                f.write(ranking_html)
        except Exception:
            pass

    finally:
        await browser.close()
        await pw.stop()

    return ranking_html


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print("=" * 60)
    print("  롯데면세점 랭킹 페이지 수집 (Stealth 모바일)")
    print("=" * 60)
    html = asyncio.run(fetch_ranking_html())
    if html:
        print(f"\n수집 완료: {len(html):,} chars")
    else:
        print("\n수집 실패")


if __name__ == "__main__":
    main()
