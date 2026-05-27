"""
전략 실행기 추상 베이스 클래스

모든 전략 실행기가 구현해야 할 인터페이스를 정의한다.
"""
from abc import ABC, abstractmethod

from playwright.sync_api import Page


class BaseStrategy(ABC):
    """추출 전략 베이스"""

    @abstractmethod
    def extract(self, page: Page, config: dict) -> dict | list | None:
        """
        설정에 따라 페이지에서 데이터를 추출한다.

        Args:
            page:   Playwright Page 객체 (이미 대상 URL 에 접속된 상태)
            config: extraction_templates.config JSON (DB 에서 읽어온 것)

        Returns:
            추출된 데이터 (dict 또는 list) 또는 실패 시 None
        """
        ...
