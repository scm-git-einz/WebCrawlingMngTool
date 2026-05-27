"""OCR 사용 이력 API"""
from fastapi import APIRouter, Query
from core.db import CrawlDB

router = APIRouter(tags=["ocr"])


def _db():
    return CrawlDB()


@router.get("/ocr/summary")
def ocr_summary(site_id: int = Query(0, description="사이트 ID (0=전체)")):
    db = _db()
    try:
        rows = db.get_ocr_usage_summary(site_id=site_id)
        return rows if rows else []
    finally:
        db.close()


@router.get("/ocr/detail")
def ocr_detail(
    site_id: int = Query(0, description="사이트 ID (0=전체)"),
    limit: int = Query(100, description="조회 건수"),
):
    db = _db()
    try:
        rows = db.get_ocr_usage_detail(site_id=site_id, limit=limit)
        return [dict(r) for r in rows]
    finally:
        db.close()


@router.get("/ocr/sites")
def ocr_sites():
    """OCR 이력이 있는 사이트 목록"""
    db = _db()
    try:
        cur = db.conn.cursor()
        cur.execute("""
            SELECT DISTINCT o.site_id, s.site_name
            FROM ocr_usage_log o
            JOIN crawl_sites s ON o.site_id = s.id
            ORDER BY s.site_name
        """)
        return [dict(row) for row in cur.fetchall()]
    finally:
        db.close()
