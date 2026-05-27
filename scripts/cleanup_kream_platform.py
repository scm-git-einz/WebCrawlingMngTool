"""KREAM 관련 이전 불완전한 플랫폼 데이터 정리"""
import sys
sys.path.insert(0, "D:\\crawling")
from core.db import CrawlDB

db = CrawlDB()
cur = db.conn.cursor()

# platform 24 확인
cur.execute("SELECT * FROM platforms WHERE id = 24")
row = cur.fetchone()
if row:
    cols = [d[0] for d in cur.description]
    platform = dict(zip(cols, row))
    print(f"Platform 24: {platform.get('display_name')}, {platform.get('name')}")

    # 관련 템플릿 확인
    cur.execute("SELECT target, strategy FROM extraction_templates WHERE platform_id = 24")
    tmpls = cur.fetchall()
    print(f"Templates: {[t[0] for t in tmpls]}")

    # 템플릿 삭제
    cur.execute("DELETE FROM extraction_templates WHERE platform_id = 24")
    # 플랫폼 삭제
    cur.execute("DELETE FROM platforms WHERE id = 24")
    # 사이트 연결 해제
    cur.execute("UPDATE crawl_sites SET platform_id = NULL WHERE platform_id = 24")
    db.conn.commit()
    print("Platform 24 및 관련 데이터 삭제 완료")
else:
    print("Platform 24 없음")

# 확인
site = db.get_site(7)
print(f"Site 7: {site}")
