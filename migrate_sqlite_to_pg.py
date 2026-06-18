"""SQLite → PostgreSQL 데이터 마이그레이션 스크립트"""
import json
import os
import sqlite3
import sys

sys.path.insert(0, "D:\\crawling")
import psycopg2
import psycopg2.extras

SQLITE_PATH = "D:\\crawling\\data\\crawling.db"
PG_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "aops",
    "user": "postgres",
    "password": os.getenv("DB_PASSWORD", ""),
}

# 마이그레이션 순서 (FK 의존성 고려)
TABLES = [
    "platforms",
    "crawl_sites",
    "extraction_templates",
    "news_keywords",
    "crawl_results",
    "ocr_usage_log",
    "llm_usage",
    "site_credentials",
]

# JSONB 컬럼 목록 (TEXT → JSONB 변환 필요)
JSONB_COLS = {
    "platforms": ["detection", "browser"],
    "crawl_sites": ["crawl_config"],
    "extraction_templates": ["config"],
    "crawl_results": ["store_info", "products"],
}


def migrate():
    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    sqlite_conn.row_factory = sqlite3.Row

    pg_conn = psycopg2.connect(**PG_CONFIG)
    pg_cur = pg_conn.cursor()

    # agent_field_defs는 시드로 이미 생성되므로 제외 (truncate 후 재삽입)
    print("기존 PG 테이블 데이터 삭제 (역순)...")
    pg_cur.execute("DELETE FROM site_credentials")
    pg_cur.execute("DELETE FROM llm_usage")
    pg_cur.execute("DELETE FROM ocr_usage_log")
    pg_cur.execute("DELETE FROM crawl_results")
    pg_cur.execute("DELETE FROM news_keywords")
    pg_cur.execute("DELETE FROM extraction_templates")
    pg_cur.execute("DELETE FROM crawl_sites")
    pg_cur.execute("DELETE FROM platforms")
    pg_cur.execute("DELETE FROM agent_field_defs")
    pg_conn.commit()

    for table in TABLES:
        sqlite_cur = sqlite_conn.cursor()
        sqlite_cur.execute(f"SELECT * FROM {table}")
        rows = sqlite_cur.fetchall()

        if not rows:
            print(f"  {table}: 0건 (스킵)")
            continue

        columns = [desc[0] for desc in sqlite_cur.description]
        jsonb_cols = JSONB_COLS.get(table, [])

        inserted = 0
        for row in rows:
            values = []
            for i, col in enumerate(columns):
                val = row[i]
                if col in jsonb_cols and isinstance(val, str):
                    try:
                        json.loads(val)
                        values.append(val)
                    except (json.JSONDecodeError, TypeError):
                        values.append("{}")
                else:
                    values.append(val)

            placeholders = ", ".join(["%s"] * len(columns))
            col_names = ", ".join(columns)

            try:
                pg_cur.execute(
                    f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})",
                    values,
                )
                inserted += 1
            except Exception as e:
                pg_conn.rollback()
                print(f"  {table} 행 삽입 오류: {e}")
                print(f"    columns: {columns}")
                print(f"    values: {values[:3]}...")
                return

        # SERIAL 시퀀스 갱신
        pg_cur.execute(
            f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
            f"COALESCE((SELECT MAX(id) FROM {table}), 1))"
        )

        pg_conn.commit()
        print(f"  {table}: {inserted}건 마이그레이션 완료")

    # agent_field_defs도 마이그레이션
    sqlite_cur = sqlite_conn.cursor()
    sqlite_cur.execute("SELECT * FROM agent_field_defs")
    rows = sqlite_cur.fetchall()
    if rows:
        columns = [desc[0] for desc in sqlite_cur.description]
        for row in rows:
            values = list(row)
            placeholders = ", ".join(["%s"] * len(columns))
            col_names = ", ".join(columns)
            try:
                pg_cur.execute(
                    f"INSERT INTO agent_field_defs ({col_names}) VALUES ({placeholders}) "
                    f"ON CONFLICT (agent_type, field_key) DO NOTHING",
                    values,
                )
            except Exception as e:
                pg_conn.rollback()
                print(f"  agent_field_defs 오류: {e}")
                return

        pg_cur.execute(
            "SELECT setval(pg_get_serial_sequence('agent_field_defs', 'id'), "
            "COALESCE((SELECT MAX(id) FROM agent_field_defs), 1))"
        )
        pg_conn.commit()
        print(f"  agent_field_defs: {len(rows)}건 마이그레이션 완료")

    sqlite_conn.close()
    pg_conn.close()
    print("\n마이그레이션 완료!")


if __name__ == "__main__":
    migrate()
