"""시스템 코드 테이블 마이그레이션 스크립트

1. crawl_schedule 레거시 값 → 새 형식 변환
2. 누락된 agent_type/status 코드를 system_codes에 추가
3. crawl_data/crawl_failure_log 등의 agent_type도 정합성 확인
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
except ImportError:
    pass

import json
from core.db import CrawlDB

SCHEDULE_MIGRATION = {
    "hourly":  "hourly:1",
    "daily":   "daily:0",
    "weekly":  "weekly:1:0",
    "monthly": "monthly:1:0",
}

EXTRA_AGENT_CODES = [
    ("agent_type", "brand", "브랜드 수집",  {"badge_class": "dp"},      85),
    ("agent_type", "local", "로컬 수집",    {"badge_class": "success"}, 90),
]

EXTRA_STATUS_CODES = [
    ("crawl_status", "stopped", "강제종료", {"badge_class": "stopped"}, 55),
    ("crawl_status", "blocked", "차단",     {"badge_class": "failed"},  60),
]


def migrate():
    db = CrawlDB()
    cur = db._cur()

    # 1. crawl_schedule 레거시 값 변환
    print("=== 1. crawl_schedule 마이그레이션 ===")
    for old_val, new_val in SCHEDULE_MIGRATION.items():
        cur.execute(
            "UPDATE crawl_sites SET crawl_schedule = %s WHERE crawl_schedule = %s",
            (new_val, old_val),
        )
        cnt = cur.rowcount
        if cnt:
            print(f"  '{old_val}' -> '{new_val}': {cnt}건 변환")

    # old format: '6h', '2d' 등
    cur.execute("SELECT DISTINCT crawl_schedule FROM crawl_sites WHERE crawl_schedule ~ '^[0-9]+[hdwm]$'")
    old_formats = [r["crawl_schedule"] for r in cur.fetchall()]
    for old_val in old_formats:
        import re
        m = re.match(r"^(\d+)([hdwm])$", old_val)
        if m:
            n, u = m.group(1), m.group(2)
            if u == "h":
                new_val = f"hourly:{n}"
            elif u == "d":
                new_val = f"daily:0"
            elif u == "w":
                new_val = f"weekly:{n}:0"
            elif u == "m":
                new_val = f"monthly:{n}:0"
            else:
                continue
            cur.execute(
                "UPDATE crawl_sites SET crawl_schedule = %s WHERE crawl_schedule = %s",
                (new_val, old_val),
            )
            cnt = cur.rowcount
            if cnt:
                print(f"  '{old_val}' -> '{new_val}': {cnt}건 변환")

    # 2. 누락된 agent_type 코드 추가
    print("\n=== 2. 누락 agent_type 코드 추가 ===")
    for group_code, code, label, extra, sort_order in EXTRA_AGENT_CODES:
        cur.execute(
            "INSERT INTO system_codes (group_code, code, label, extra, sort_order) "
            "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (group_code, code) DO NOTHING",
            (group_code, code, label, json.dumps(extra, ensure_ascii=False), sort_order),
        )
        if cur.rowcount:
            print(f"  추가: {group_code}/{code} ({label})")
        else:
            print(f"  이미 존재: {group_code}/{code}")

    # 3. 누락된 crawl_status 코드 추가
    print("\n=== 3. 누락 crawl_status 코드 추가 ===")
    for group_code, code, label, extra, sort_order in EXTRA_STATUS_CODES:
        cur.execute(
            "INSERT INTO system_codes (group_code, code, label, extra, sort_order) "
            "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (group_code, code) DO NOTHING",
            (group_code, code, label, json.dumps(extra, ensure_ascii=False), sort_order),
        )
        if cur.rowcount:
            print(f"  추가: {group_code}/{code} ({label})")
        else:
            print(f"  이미 존재: {group_code}/{code}")

    # 4. 정합성 확인 — DB에 있지만 system_codes에 없는 값
    print("\n=== 4. 정합성 확인 ===")

    # agent_type
    cur.execute("""
        SELECT DISTINCT t.agent_type FROM (
            SELECT agent_type FROM crawl_sites
            UNION SELECT agent_type FROM crawl_data
            UNION SELECT agent_type FROM crawl_failure_log
            UNION SELECT agent_type FROM llm_usage
        ) t
        WHERE t.agent_type NOT IN (
            SELECT code FROM system_codes WHERE group_code = 'agent_type'
        )
    """)
    missing_agents = [r["agent_type"] for r in cur.fetchall()]
    if missing_agents:
        print(f"  [경고] system_codes에 없는 agent_type: {missing_agents}")
    else:
        print("  agent_type: 모두 정합")

    # category
    cur.execute("""
        SELECT DISTINCT category FROM crawl_sites
        WHERE category != '' AND category NOT IN (
            SELECT code FROM system_codes WHERE group_code = 'category'
        )
    """)
    missing_cats = [r["category"] for r in cur.fetchall()]
    if missing_cats:
        print(f"  [경고] system_codes에 없는 category: {missing_cats}")
    else:
        print("  category: 모두 정합")

    # status
    cur.execute("""
        SELECT DISTINCT status FROM crawl_results
        WHERE status NOT IN (
            SELECT code FROM system_codes WHERE group_code = 'crawl_status'
        )
    """)
    missing_status = [r["status"] for r in cur.fetchall()]
    if missing_status:
        print(f"  [경고] system_codes에 없는 status: {missing_status}")
    else:
        print("  crawl_status: 모두 정합")

    # 5. 최종 현황
    print("\n=== 5. 최종 system_codes 현황 ===")
    cur.execute("SELECT group_code, COUNT(*) as cnt FROM system_codes GROUP BY group_code ORDER BY group_code")
    for r in cur.fetchall():
        print(f"  {r['group_code']}: {r['cnt']}개")

    cur.execute("SELECT DISTINCT crawl_schedule, COUNT(*) as cnt FROM crawl_sites GROUP BY crawl_schedule ORDER BY cnt DESC")
    print("\n  crawl_schedule 현황:")
    for r in cur.fetchall():
        print(f"    '{r['crawl_schedule']}': {r['cnt']}건")

    db.conn.commit()
    db.close()
    print("\n마이그레이션 완료!")


if __name__ == "__main__":
    migrate()
