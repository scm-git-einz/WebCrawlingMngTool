"""로컬 에이전트 디스패처 — agent_type='local' 로 등록되는 진입점.

crawl_config.local_type 값에 따라 실제 로컬 에이전트로 위임한다.
"""
from core.base_agent import BaseAgent


_LOCAL_MAP: dict = {}  # 순환 import 방지 — 첫 호출 시 지연 초기화


def _load_local_map():
    global _LOCAL_MAP
    if _LOCAL_MAP:
        return
    from agents.local.oliveyoung.engine import OliveYoungAgent
    _LOCAL_MAP.update({
        "oliveyoung": OliveYoungAgent,
    })


class LocalDispatcher(BaseAgent):
    """local agent_type 의 진입점. local_type 설정에 따라 개별 에이전트로 위임."""

    _TAG = "[local]"

    @property
    def agent_type(self) -> str:
        return "local"

    def _normalize_config(self, crawl_cfg: dict) -> dict:
        return crawl_cfg

    def run_site(self, site_id: int):
        import json
        from core.db import CrawlDB

        db = CrawlDB()
        try:
            site = db.get_site(site_id)
        finally:
            db.close()

        if not site:
            print(f"{self._TAG} site_id={site_id} 를 찾을 수 없음")
            return

        raw = site.get("crawl_config") or {}
        config = raw if isinstance(raw, dict) else json.loads(raw)
        local_type = config.get("local_type", "")

        _load_local_map()
        agent_cls = _LOCAL_MAP.get(local_type)
        if not agent_cls:
            print(f"{self._TAG} 알 수 없는 local_type: '{local_type}'")
            return

        print(f"{self._TAG} → {local_type} 에이전트로 위임 (site_id={site_id})")
        agent_cls().run_site(site_id)
