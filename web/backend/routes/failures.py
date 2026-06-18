"""실패 모니터링 API"""
from fastapi import APIRouter, Query
from core.db import CrawlDB

router = APIRouter(tags=["failures"])


def _db():
    return CrawlDB()


@router.get("/api/failures/stats")
def get_failure_stats(days: int = Query(30, ge=1, le=365)):
    """기간별 실패 통계 요약 (StatCard용)."""
    db = _db()
    try:
        stats = db.get_failure_stats(days=days)
        return stats
    finally:
        db.close()


@router.get("/api/failures")
def get_failure_list(
    site_id: int | None = Query(None),
    agent_type: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
):
    """실패 로그 목록 조회 (필터링)."""
    db = _db()
    try:
        rows = db.get_failure_logs(
            site_id=site_id,
            agent_type=agent_type,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
        )
        return rows
    finally:
        db.close()


@router.get("/api/failures/{failure_id}")
def get_failure_detail(failure_id: int):
    """단건 상세 (failure_events 포함)."""
    db = _db()
    try:
        row = db.get_failure_log_detail(failure_id)
        if not row:
            return {"error": "not found"}
        return row
    finally:
        db.close()
