"""크롤링 실패 이벤트 수집기

크롤 1회 동안 발생하는 실패 이벤트를 메모리에 모았다가,
크롤 종료 시 한 번에 DB에 저장한다. (A안: 크롤 단위 요약 저장)
"""
from collections import Counter
from datetime import datetime


class FailureCollector:
    """크롤 1회 동안 발생하는 실패 이벤트를 수집하고 요약 저장한다.

    사용법:
        collector = FailureCollector(site_id, result_id, "product")
        collector.add("click_fail", "카드 클릭 실패", target="상품코드 123")
        collector.add("http_block", "HTTP 429", subtype="429", domain="example.com")
        # 크롤 종료 시
        collector.save(db, log_file="crawl_35_20260617.log")
    """

    # 지원하는 실패 유형
    TYPES = {
        "http_block",   # HTTP 429/403/503
        "soft_block",   # HTTP 200이지만 빈 페이지/이미지만
        "login_fail",   # 로그인 실패/차단
        "click_fail",   # 카드/버튼 클릭 실패
        "nav_fail",     # 페이지 이동/도달 실패
        "data_fail",    # 데이터 추출 실패
        "exception",    # 예외 발생 (미분류)
    }

    def __init__(self, site_id: int, crawl_result_id: int, agent_type: str):
        self.site_id = site_id
        self.crawl_result_id = crawl_result_id
        self.agent_type = agent_type
        self._events: list[dict] = []

    def add(self, event_type: str, message: str, **kwargs):
        """실패 이벤트를 추가한다.

        Args:
            event_type: 실패 유형 (TYPES 참조)
            message: 사람이 읽을 수 있는 설명
            **kwargs: 선택적 필드
                subtype: 세부 유형 (예: "429", "payment_info")
                domain: 도메인명
                url: 대상 URL
                target: 대상 (상품코드, 상품명 등)
                context: dict — 추가 컨텍스트 (attempt, wait_secs, proxy 등)
        """
        event = {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "type": event_type,
            "message": message,
        }
        for key in ("subtype", "domain", "url", "target", "context"):
            val = kwargs.get(key)
            if val is not None:
                event[key] = val
        self._events.append(event)

    @property
    def has_failures(self) -> bool:
        """실패 이벤트가 있는지 확인."""
        return len(self._events) > 0

    @property
    def total(self) -> int:
        return len(self._events)

    def build_summary(self) -> dict:
        """유형별 카운트 요약을 생성한다."""
        counter = Counter(e["type"] for e in self._events)
        summary = {"total": len(self._events)}
        for t in self.TYPES:
            summary[t] = counter.get(t, 0)
        return summary

    def save(self, db, log_file: str | None = None):
        """DB에 저장한다. 실패가 없으면 저장하지 않는다."""
        if not self._events:
            return
        db.insert_failure_log(
            site_id=self.site_id,
            crawl_result_id=self.crawl_result_id,
            agent_type=self.agent_type,
            failure_summary=self.build_summary(),
            failure_events=self._events,
            log_file=log_file,
        )
