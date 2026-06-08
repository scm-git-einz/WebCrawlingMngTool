"""
에이전트 패키지

각 에이전트 타입은 하위 패키지로 구성된다:
  - product:   상품/랭킹 수집 에이전트 (v2)
  - news:      뉴스 기사 수집 에이전트
  - cafe:      카페 인기글 수집 에이전트
  - promotion: 프로모션/이벤트 수집 에이전트
  - banner:    배너/비주얼 수집 에이전트 (v2)
  - directory: 브랜드/이벤트 목록 수집 에이전트 (v2)
  - order:     주문서 결제정보 수집 에이전트

에이전트 레지스트리:
  AGENT_REGISTRY 에 등록된 에이전트만 main.py 에서 사용 가능하다.
"""
from agents.product.engine import ProductAgent
from agents.news.engine import NewsAgent
from agents.cafe.engine import CafeAgent
from agents.promotion.engine import PromotionAgent
from agents.banner.engine import BannerAgent
from agents.directory.engine import DirectoryAgent
from agents.order.engine import OrderAgent


AGENT_REGISTRY = {
    "product": ProductAgent,
    "news": NewsAgent,
    "cafe": CafeAgent,
    "promotion": PromotionAgent,
    "banner": BannerAgent,
    "directory": DirectoryAgent,
    "order": OrderAgent,
}


def get_agent(agent_type: str, db=None):
    """에이전트 타입으로 인스턴스를 생성하여 반환한다."""
    cls = AGENT_REGISTRY.get(agent_type)
    if cls is None:
        raise ValueError(
            f"알 수 없는 에이전트 타입: {agent_type}. "
            f"사용 가능: {list(AGENT_REGISTRY.keys())}"
        )
    return cls(db=db)
