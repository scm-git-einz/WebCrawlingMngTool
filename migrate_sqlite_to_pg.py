"""SQLite → PostgreSQL 데이터 마이그레이션 스크립트"""
import json
import os
import sqlite3

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

SQLITE_PATH = os.path.join(os.path.dirname(__file__), "data", "crawling.db")

PG = {
    "host": os.getenv("DB_HOST", "10.149.67.179"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "dbname": os.getenv("DB_NAME", "aops"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
}


def migrate():
    lite = sqlite3.connect(SQLITE_PATH)
    lite.row_factory = sqlite3.Row

    pg = psycopg2.connect(**PG)
    cur = pg.cursor(cursor_factory=RealDictCursor)

    # ── crawl_sites ──────────────────────────────────────────────────
    rows = lite.execute("SELECT * FROM crawl_sites ORDER BY id").fetchall()
    print(f"crawl_sites: {len(rows)}건 이전 중...")
    for r in rows:
        cur.execute(
            """
            INSERT INTO crawl_sites
                (id, site_name, site_url, is_active, platform_id, agent_type,
                 crawl_config, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                site_name    = EXCLUDED.site_name,
                site_url     = EXCLUDED.site_url,
                is_active    = EXCLUDED.is_active,
                platform_id  = EXCLUDED.platform_id,
                agent_type   = EXCLUDED.agent_type,
                crawl_config = EXCLUDED.crawl_config,
                updated_at   = EXCLUDED.updated_at
            """,
            (
                r["id"], r["site_name"], r["site_url"], r["is_active"],
                r["platform_id"], r["agent_type"],
                r["crawl_config"] or "{}",
                r["created_at"], r["updated_at"],
            ),
        )
    # SERIAL 시퀀스를 현재 max id에 맞춤
    cur.execute("SELECT setval('crawl_sites_id_seq', (SELECT MAX(id) FROM crawl_sites))")

    # ── news_keywords ─────────────────────────────────────────────────
    rows = lite.execute("SELECT * FROM news_keywords ORDER BY id").fetchall()
    print(f"news_keywords: {len(rows)}건 이전 중...")
    for r in rows:
        cur.execute(
            """
            INSERT INTO news_keywords (id, site_id, keyword, is_active, created_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (r["id"], r["site_id"], r["keyword"], r["is_active"], r["created_at"]),
        )
    if rows:
        cur.execute("SELECT setval('news_keywords_id_seq', (SELECT MAX(id) FROM news_keywords))")

    # ── crawl_results ─────────────────────────────────────────────────
    rows = lite.execute("SELECT * FROM crawl_results ORDER BY id").fetchall()
    print(f"crawl_results: {len(rows)}건 이전 중...")
    for r in rows:
        cur.execute(
            """
            INSERT INTO crawl_results
                (id, site_id, crawl_date, status, store_info, products,
                 product_count, error_msg, elapsed_sec)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (
                r["id"], r["site_id"], r["crawl_date"], r["status"],
                r["store_info"], r["products"], r["product_count"],
                r["error_msg"], r["elapsed_sec"],
            ),
        )
    if rows:
        cur.execute("SELECT setval('crawl_results_id_seq', (SELECT MAX(id) FROM crawl_results))")

    pg.commit()
    print("마이그레이션 완료!")

    lite.close()
    pg.close()


if __name__ == "__main__":
    migrate()
