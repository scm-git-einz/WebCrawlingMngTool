"""예거 르쿨트르 상품 수집 에이전트 (jaeger-lecoultre.com) — Richemont Group

주의: 상품 상세 페이지에 가격 정보가 공개되지 않는 정책.
      JSON-LD / API 캡처로 내부 데이터 확인을 시도하나
      실패 시 '가격 미제공' 결과를 반환한다.
"""
import re
from agents.brand.base import BrandAgent


class JLCAgent(BrandAgent):

    _TAG = "[jlc]"

    @property
    def agent_type(self) -> str:
        return "jlc"

    def _sku_from_url(self, url: str) -> str:
        # 예: /p/Q3578420/ 또는 마지막 경로 세그먼트
        m = re.search(r"/p/([A-Z0-9]+)/?", url, re.IGNORECASE)
        if m:
            return m.group(1).upper()
        # 마지막 경로 세그먼트 fallback
        parts = url.rstrip("/").split("/")
        return parts[-1] if parts else ""
