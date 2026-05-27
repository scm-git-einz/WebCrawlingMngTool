"""
매장 정보 수집 모듈 (StoreCrawler)

네이버 브랜드스토어 메인 페이지에서 매장 정보를 수집한다.
JS 속성 키는 config/settings.py 의 STORE_FIELD_MAP 에 정의되어 있으며
이 파일에는 사이트 종속적인 하드코딩이 없다.
"""
from playwright.sync_api import Page

import config.settings as settings
from utils.browser import create_stealth_browser
from utils.file_handler import save_json, get_timestamp
from utils.js_builder import build_store_extract_js


class StoreCrawler:
    """네이버 브랜드스토어 매장 정보 크롤러"""

    def __init__(self):
        self.page: Page | None = None
        self.store_info: dict = {}

    def crawl(self) -> dict:
        """매장 정보를 수집하여 JSON 으로 저장하고 결과를 반환한다."""
        print("\n[store] ── 매장 정보 수집 시작 ──")

        ctx, self.page = create_stealth_browser()

        print(f"[store] 페이지 접속: {settings.TARGET_URL}")
        self.page.goto(settings.TARGET_URL, wait_until="domcontentloaded")
        self.page.wait_for_timeout(5000)

        # 매핑 기반 추출
        self.store_info = self._extract_store_info()

        # 매장명 DOM 폴백
        if self.store_info.get("store_name") == "N/A":
            print("[store] 상태 변수 부족 → DOM title 폴백")
            title = self.page.title() or ""
            if title:
                self.store_info["store_name"] = title.split(":")[0].strip()

        # 메타데이터
        self.store_info["crawl_url"] = settings.TARGET_URL
        self.store_info["crawl_date"] = get_timestamp()

        save_json(self.store_info, "store_info.json")
        self._print_summary()
        return self.store_info

    # ─── 매핑 기반 추출 ───────────────────────────────────────────

    def _extract_store_info(self) -> dict:
        """settings 매핑으로 생성된 JS 를 실행하여 매장 정보를 추출한다."""
        print("[store] 매장 정보 탐색 중...")

        result = {k: "N/A" for k in settings.STORE_FIELD_MAP if k != "root_key"}

        try:
            js_code = build_store_extract_js()
            data = self.page.evaluate(js_code)

            if not data:
                print("[store] 매장 데이터 없음")
                return result

            # data 의 키를 result 에 매핑
            for key in result:
                value = data.get(key)
                result[key] = str(value) if value is not None else "N/A"

            print(f"[store] 매장명: {result.get('store_name', 'N/A')}")
            print(f"[store] 누적 판매: {result.get('sale_count', 'N/A')}건")

        except Exception as e:
            print(f"[store] 매장 정보 추출 실패: {e}")

        return result

    def _print_summary(self):
        """수집 결과 요약 출력"""
        print("\n[store] ── 매장 정보 수집 결과 ──")
        for k, v in self.store_info.items():
            print(f"  {k}: {str(v)[:80]}")
        print()
