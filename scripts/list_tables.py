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
cur.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
for r in cur.fetchall():
    prefix = "OK" if r["tablename"].startswith("crawl_") else "RENAME"
    print(f"  [{prefix}] {r['tablename']}")
db.close()
