"""루이비통 코리아 상품 수집 에이전트"""
import re
from agents.brand.base import BrandAgent


class LouisVuittonAgent(BrandAgent):

    _TAG = "[louisvuitton]"

    @property
    def agent_type(self) -> str:
        return "louisvuitton"

    def _sku_from_url(self, url: str) -> str:
        m = re.search(r"kr\.louisvuitton\.com/kor-kr/products/[^/]+/([A-Z0-9]+)", url)
        return m.group(1) if m else ""
