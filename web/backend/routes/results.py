"""수집 결과 조회 API"""
from fastapi import APIRouter, HTTPException, Query
from core.db import CrawlDB

router = APIRouter(tags=["results"])


def _db():
    return CrawlDB()


@router.get("/dashboard/stats")
def dashboard_stats():
    db = _db()
    try:
        cur = db._cur()

        cur.execute("SELECT COUNT(*) AS cnt FROM crawl_sites")
        total_sites = cur.fetchone()["cnt"]

        cur.execute("SELECT COUNT(*) AS cnt FROM crawl_sites WHERE is_active = 1")
        active_sites = cur.fetchone()["cnt"]

        cur.execute("SELECT COUNT(*) AS cnt FROM crawl_results")
        total_crawls = cur.fetchone()["cnt"]

        cur.execute(
            "SELECT COUNT(*) AS cnt FROM crawl_results WHERE status = 'success'"
        )
        success_crawls = cur.fetchone()["cnt"]

        cur.execute("SELECT COALESCE(SUM(product_count), 0) AS cnt FROM crawl_results WHERE status = 'success'")
        total_products = cur.fetchone()["cnt"]

        cur.execute("""
            SELECT s.id as site_id, s.site_name, s.site_url, s.category,
                   s.agent_type, s.is_active,
                   r.id as result_id, r.crawl_date, r.status,
                   r.product_count, r.elapsed_sec, r.error_msg
            FROM crawl_sites s
            LEFT JOIN crawl_results r ON r.id = (
                SELECT r2.id FROM crawl_results r2
                WHERE r2.site_id = s.id
                ORDER BY r2.crawl_date DESC LIMIT 1
            )
            ORDER BY s.category, s.site_name
        """)
        site_status = [dict(row) for row in cur.fetchall()]

        cur.execute("""
            SELECT r.id, r.site_id, s.site_name, s.agent_type, s.category,
                   r.crawl_date, r.status, r.product_count, r.elapsed_sec, r.error_msg
            FROM crawl_results r
            JOIN crawl_sites s ON r.site_id = s.id
            ORDER BY r.crawl_date DESC
            LIMIT 10
        """)
        recent = [dict(row) for row in cur.fetchall()]

        return {
            "total_sites": total_sites,
            "active_sites": active_sites,
            "total_crawls": total_crawls,
            "success_crawls": success_crawls,
            "total_products": total_products,
            "site_status": site_status,
            "recent_crawls": recent,
        }
    finally:
        db.close()


@router.get("/results")
def list_results(
    site_id: int = Query(0, description="사이트 ID (0=전체)"),
    limit: int = Query(50, description="조회 건수"),
):
    db = _db()
    try:
        cur = db._cur()
        if site_id:
            cur.execute("""
                SELECT r.id, r.site_id, s.site_name, s.agent_type, s.category,
                       r.crawl_date, r.status,
                       r.product_count, r.elapsed_sec, r.error_msg
                FROM crawl_results r
                JOIN crawl_sites s ON r.site_id = s.id
                WHERE r.site_id = %s
                ORDER BY r.crawl_date DESC
                LIMIT %s
            """, (site_id, limit))
        else:
            cur.execute("""
                SELECT r.id, r.site_id, s.site_name, s.agent_type, s.category,
                       r.crawl_date, r.status,
                       r.product_count, r.elapsed_sec, r.error_msg
                FROM crawl_results r
                JOIN crawl_sites s ON r.site_id = s.id
                ORDER BY r.crawl_date DESC
                LIMIT %s
            """, (limit,))
        return [dict(row) for row in cur.fetchall()]
    finally:
        db.close()


@router.get("/results/{result_id}")
def get_result_detail(result_id: int):
    db = _db()
    try:
        cur = db._cur()
        cur.execute("""
            SELECT r.id, r.site_id, r.crawl_date, r.status,
                   r.product_count, r.error_msg, r.elapsed_sec,
                   s.site_name, s.site_url, s.agent_type, s.category
            FROM crawl_results r
            JOIN crawl_sites s ON r.site_id = s.id
            WHERE r.id = %s
        """, (result_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "결과를 찾을 수 없습니다")

        result = dict(row)

        crawl_data = db.get_crawl_data(result_id)
        if crawl_data:
            result["items"] = crawl_data.get("items", [])
            result["store_info"] = crawl_data.get("store_info", {})
        else:
            result["items"] = []
            result["store_info"] = {}

        return result
    finally:
        db.close()
