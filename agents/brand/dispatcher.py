"""브랜드 에이전트 디스패처 — agent_type='brand' 로 등록되는 진입점.

crawl_config.brand_type 값에 따라 실제 브랜드 에이전트로 위임한다.
"""
from core.base_agent import BaseAgent


_BRAND_MAP: dict = {}  # 순환 import 방지 — 첫 호출 시 지연 초기화


def _load_brand_map():
    global _BRAND_MAP
    if _BRAND_MAP:
        return
    from agents.brand.longchamp.engine import LongchampAgent
    from agents.brand.cartier.engine import CartierAgent
    from agents.brand.toryburch.engine import ToryBurchAgent
    from agents.brand.rogervivier.engine import RogerVivierAgent
    from agents.brand.iwc.engine import IWCAgent
    from agents.brand.jlc.engine import JLCAgent
    from agents.brand.louisvuitton.engine import LouisVuittonAgent
    from agents.brand.chanel.engine import ChanelAgent
    _BRAND_MAP.update({
        'longchamp':   LongchampAgent,
        'cartier':     CartierAgent,
        'toryburch':   ToryBurchAgent,
        'rogervivier': RogerVivierAgent,
        'iwc':         IWCAgent,
        'jlc':         JLCAgent,
        'louisvuitton': LouisVuittonAgent,
        'chanel':      ChanelAgent,
    })


class BrandDispatcher(BaseAgent):
    """brand agent_type 의 진입점. brand_type 설정에 따라 개별 에이전트로 위임."""

    _TAG = "[brand]"

    @property
    def agent_type(self) -> str:
        return "brand"

    def _normalize_config(self, crawl_cfg: dict) -> dict:
        return crawl_cfg

    def run_site(self, site_id: int):
        from core.db import CrawlDB
        import json
        db = CrawlDB()
        try:
            site = db.get_site(site_id)
        finally:
            db.close()

        if not site:
            print(f"{self._TAG} site_id={site_id} 를 찾을 수 없음")
            return

        config = json.loads(site.get("crawl_config") or "{}")
        brand_type = config.get("brand_type", "")

        _load_brand_map()
        agent_cls = _BRAND_MAP.get(brand_type)
        if not agent_cls:
            print(f"{self._TAG} 알 수 없는 brand_type: '{brand_type}'")
            return

        print(f"{self._TAG} → {brand_type} 에이전트로 위임 (site_id={site_id})")
        agent_cls().run_site(site_id)
