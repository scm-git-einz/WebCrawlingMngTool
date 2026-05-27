"""
추출 전략 실행기 패키지

DB 의 extraction_templates.config JSON 을 읽고
실제 데이터 추출을 수행하는 전략 엔진들을 제공한다.

지원 전략:
  - state_var: window 전역 변수 기반 추출
  - dom:       CSS 셀렉터 기반 DOM 파싱
  - api:       REST API 호출 기반 추출
"""
from core.strategies.state_var import StateVarStrategy
from core.strategies.dom_parser import DomParserStrategy
from core.strategies.api_caller import ApiCallerStrategy


STRATEGY_MAP = {
    "state_var": StateVarStrategy,
    "dom": DomParserStrategy,
    "api": ApiCallerStrategy,
}


def get_strategy(strategy_name: str):
    """전략 이름으로 실행기 인스턴스를 반환한다."""
    cls = STRATEGY_MAP.get(strategy_name)
    if cls is None:
        raise ValueError(f"알 수 없는 전략: {strategy_name}. "
                         f"사용 가능: {list(STRATEGY_MAP.keys())}")
    return cls()
