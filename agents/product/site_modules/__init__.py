"""
플랫폼별 전용 수집 모듈 레지스트리

도메인 패턴으로 URL을 매칭하여 전용 모듈의 수집 로직을 실행한다.
매칭되지 않으면 기존 RuleAnalyzer 기반 범용 수집으로 폴백한다.

사용 방법:
    from agents.product.site_modules import find_site_module

    module = find_site_module(site_url)
    if module:
        store_info, products = module.collect(page, config)
    else:
        # 기존 범용 수집 로직
"""
from urllib.parse import urlparse


class BaseSiteModule:
    """플랫폼별 수집 모듈 기본 클래스

    서브클래스는 다음을 구현해야 한다:
        DOMAIN_PATTERNS: list[str]  — 매칭할 도메인 패턴 목록
        collect_store_info(page)    — 매장 정보 수집
        collect_products(page, config) — 상품 목록 수집
    """

    # 서브클래스에서 오버라이드: 매칭할 도메인 문자열 목록
    # 예: ["brand.naver.com", "smartstore.naver.com"]
    DOMAIN_PATTERNS = []

    def matches(self, url: str) -> bool:
        """URL이 이 모듈의 도메인 패턴에 매칭되는지 확인한다."""
        domain = urlparse(url).netloc.lower()
        return any(pattern in domain for pattern in self.DOMAIN_PATTERNS)

    def collect(self, page, config: dict) -> tuple[dict, list[dict]]:
        """매장 정보 + 상품 목록을 수집한다.

        Args:
            page: Playwright Page 객체 (이미 사이트에 접속된 상태)
            config: 정규화된 crawl_config

        Returns:
            (store_info, products) 튜플
        """
        store_info = self.collect_store_info(page)
        products = self.collect_products(page, config)

        # display_order 보정
        for i, p in enumerate(products):
            p["display_order"] = i + 1

        return store_info, products

    def collect_store_info(self, page) -> dict:
        """매장 정보를 수집한다. 기본 구현: meta 태그에서 추출."""
        try:
            info = page.evaluate("""() => {
                const getMeta = (name) => {
                    const el = document.querySelector(
                        `meta[property="${name}"], meta[name="${name}"]`
                    );
                    return el ? el.getAttribute('content') : '';
                };
                return {
                    store_name: document.title || '',
                    description: getMeta('og:description') || getMeta('description') || '',
                    logo_url: getMeta('og:image') || '',
                };
            }""")
            return info or {"store_name": "N/A"}
        except Exception:
            return {"store_name": "N/A"}

    def collect_products(self, page, config: dict) -> list[dict]:
        """상품 목록을 수집한다. 서브클래스에서 구현."""
        raise NotImplementedError


# ─── 모듈 레지스트리 ─────────────────────────────────────
# 모듈 인스턴스를 등록한다. import 시 자동 등록.
_MODULES: list[BaseSiteModule] = []


def register_module(module_cls):
    """모듈 클래스를 레지스트리에 등록하는 데코레이터"""
    _MODULES.append(module_cls())
    return module_cls


def find_site_module(url: str) -> BaseSiteModule | None:
    """URL에 매칭되는 전용 모듈을 찾는다.

    Returns:
        매칭된 모듈 인스턴스 또는 None (범용 폴백 필요)
    """
    for module in _MODULES:
        if module.matches(url):
            return module
    return None


# ─── 모듈 자동 import (등록 트리거) ──────────────────────
from agents.product.site_modules.naver_store import NaverStoreModule      # noqa
from agents.product.site_modules.oliveyoung import OliveYoungModule       # noqa
from agents.product.site_modules.musinsa import MusinsaModule             # noqa
from agents.product.site_modules.cm29 import CM29Module                   # noqa
from agents.product.site_modules.wconcept import WConceptModule           # noqa
from agents.product.site_modules.kream import KreamModule                 # noqa
from agents.product.site_modules.lotte_dfs import LotteDFSModule          # noqa
from agents.product.site_modules.shilla_dfs import ShillaDFSModule        # noqa
from agents.product.site_modules.hyundai_dfs import HyundaiDFSModule      # noqa
from agents.product.site_modules.ssg_dfs import SSGDFSModule              # noqa
from agents.product.site_modules.sephora import SephoraModule             # noqa
from agents.product.site_modules.ulta import UltaModule                   # noqa
from agents.product.site_modules.luxury import LuxuryBrandModule          # noqa
