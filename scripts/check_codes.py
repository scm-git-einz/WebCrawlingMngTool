import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
except ImportError:
    pass

from core.db import CrawlDB
db = CrawlDB()
cur = db._cur()

cur.execute("SELECT group_code, COUNT(*) as cnt FROM system_codes GROUP BY group_code ORDER BY group_code")
print("=== system_codes 현황 ===")
for r in cur.fetchall():
    print(f"  {r['group_code']}: {r['cnt']}개")

cur.execute("""
    SELECT DISTINCT category FROM crawl_sites
    WHERE category != '' AND category NOT IN (
        SELECT code FROM system_codes WHERE group_code = 'category'
    )
""")
missing = [r["category"] for r in cur.fetchall()]
print(f"\n누락 category: {missing if missing else '없음'}")

cur.execute("""
    SELECT DISTINCT agent_type FROM crawl_sites
    WHERE agent_type NOT IN (
        SELECT code FROM system_codes WHERE group_code = 'agent_type'
    )
""")
missing2 = [r["agent_type"] for r in cur.fetchall()]
print(f"누락 agent_type: {missing2 if missing2 else '없음'}")

cur.execute("""
    SELECT DISTINCT status FROM crawl_results
    WHERE status NOT IN (
        SELECT code FROM system_codes WHERE group_code = 'crawl_status'
    )
""")
missing3 = [r["status"] for r in cur.fetchall()]
print(f"누락 crawl_status: {missing3 if missing3 else '없음'}")

cur.execute("SELECT DISTINCT crawl_schedule, COUNT(*) as cnt FROM crawl_sites GROUP BY crawl_schedule")
print(f"\ncrawl_schedule 현황:")
for r in cur.fetchall():
    print(f"  '{r['crawl_schedule']}': {r['cnt']}건")

db.close()
