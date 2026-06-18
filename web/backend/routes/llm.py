"""LLM 토큰 사용량 조회 API"""
from fastapi import APIRouter, Query
from core.db import CrawlDB

router = APIRouter(tags=["llm"])


def _db():
    return CrawlDB()


@router.get("/llm/summary")
def llm_summary():
    """LLM 사용량 전체 요약 (에이전트별, 작업유형별, 모델별, 일별 추이)."""
    db = _db()
    try:
        return db.get_llm_usage_summary()
    finally:
        db.close()


@router.get("/llm/detail")
def llm_detail(
    agent_type: str = Query("", description="에이전트 유형 필터"),
    task_type: str = Query("", description="작업 유형 필터"),
    site_id: int = Query(0, description="사이트 ID 필터"),
    limit: int = Query(100, description="조회 건수"),
):
    """LLM 사용 이력 상세."""
    db = _db()
    try:
        return db.get_llm_usage_detail(
            agent_type=agent_type,
            task_type=task_type,
            site_id=site_id,
            limit=limit,
        )
    finally:
        db.close()
