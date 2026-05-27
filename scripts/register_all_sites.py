"""전체 크롤링 대상 사이트 일괄 등록 스크립트

카테고리별로 사이트를 등록/업데이트한다.
- 기존 사이트: category 업데이트 + URL 변경
- 신규 사이트: 추가
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, "D:\\crawling")
from core.db import CrawlDB

db = CrawlDB()
cur = db.conn.cursor()

# ─── 1) category 컬럼 추가 (마이그레이션) ────────────────────────
cur.execute("PRAGMA table_info(crawl_sites)")
columns = {row[1] for row in cur.fetchall()}
if "category" not in columns:
    cur.execute(
        "ALTER TABLE crawl_sites "
        "ADD COLUMN category TEXT NOT NULL DEFAULT ''"
    )
    db.conn.commit()
    print("[migrate] crawl_sites.category 컬럼 추가됨")
else:
    print("[migrate] category 컬럼 이미 존재")


# ─── 2) 기존 사이트 카테고리 + URL 업데이트 ─────────────────────
EXISTING_UPDATES = [
    (1, "네이버스토어",   "에스티로더",      "https://brand.naver.com/esteelauderkorea"),
    (2, "네이버스토어",   "케라스타즈",      "https://brand.naver.com/kerastase"),
    (3, "트렌드매장",     "올리브영",        "https://www.oliveyoung.co.kr/store/main/main.do"),
    (4, "트렌드매장",     "무신사",          "https://www.musinsa.com/main/musinsa"),
    (5, "트렌드매장",     "29CM",           "https://www.29cm.co.kr/"),
    (6, "트렌드매장",     "W컨셉",          "https://display.wconcept.co.kr/rn/women"),
    (7, "트렌드매장",     "크림",            "https://kream.co.kr/"),
    (8, "뉴스",           "네이버뉴스검색",  None),  # URL 유지
    (9, "카페",           "꼬냑클럽",        None),  # URL 유지
]

for site_id, category, name, url in EXISTING_UPDATES:
    if url:
        cur.execute(
            "UPDATE crawl_sites SET category=?, site_name=?, site_url=?, "
            "updated_at=datetime('now','localtime') WHERE id=?",
            (category, name, url, site_id),
        )
    else:
        cur.execute(
            "UPDATE crawl_sites SET category=?, site_name=?, "
            "updated_at=datetime('now','localtime') WHERE id=?",
            (category, name, site_id),
        )
    print(f"  [update] #{site_id} {name} → category={category}")

db.conn.commit()


# ─── 3) 신규 사이트 등록 ────────────────────────────────────────
NEW_SITES = [
    # (카테고리, 사이트명, URL, agent_type)
    # 트렌드 Global 매장
    ("트렌드Global매장", "SEPHORA",             "https://www.sephora.com/",               "product"),
    ("트렌드Global매장", "ULTA BEAUTY",         "https://www.ulta.com/",                  "product"),
    ("트렌드Global매장", "OLIVE YOUNG GLOBAL",  "https://global.oliveyoung.com/",         "product"),

    # 경쟁사
    ("경쟁사",   "롯데면세점",    "https://kor.lottedfs.com/kr/shopmain/home",             "product"),
    ("경쟁사",   "신라면세점",    "https://www.shilladfs.com/estore/kr/ko/",               "product"),
    ("경쟁사",   "현대면세점",    "https://www.hddfs.com/shop/dm/main.do",                 "product"),

    # 경쟁사-중국
    ("경쟁사중국", "신라면세점(중국)", "https://www.shilladutyfree.cn/estore/kr/zh/?uiel=Desktop",  "product"),
    ("경쟁사중국", "롯데면세점(중국)", "https://chn.lottedfs.cn/kr/shopmain/home?changeLang=ZH",    "product"),

    # 경쟁사 이벤트
    ("경쟁사이벤트", "롯데면세점 이벤트", "https://kor.lottedfs.com/kr/eventmain/benefit",              "product"),
    ("경쟁사이벤트", "신라면세점 이벤트", "https://www.shilladfs.com/estore/kr/ko/event?XAREA=GNB",     "product"),
    ("경쟁사이벤트", "현대면세점 이벤트", "https://www.hddfs.com/event/op/evnt/evntShop.do",            "product"),

    # 브랜드 공식 홈페이지
    ("브랜드공식", "까르띠에",   "https://www.cartier.com/ko-kr/home",          "product"),
    ("브랜드공식", "샤넬",       "https://www.chanel.com/kr/",                  "product"),
    ("브랜드공식", "루이비통",   "https://kr.louisvuitton.com/kor-kr/",         "product"),
    ("브랜드공식", "티파니",     "https://www.tiffany.kr/",                     "product"),
    ("브랜드공식", "불가리",     "https://www.bulgari.com/ko-kr/",              "product"),

    # 당사 온라인몰 메인
    ("당사온라인몰", "SSG면세점 K몰", "https://www.ssgdfs.com/kr/main/initMain",  "product"),
    ("당사온라인몰", "SSG면세점 C몰", "https://www.ssgdfs.com/cn/main/initMain",  "product"),
    ("당사온라인몰", "SSG면세점 E몰", "https://www.ssgdfs.com/en/main/initMain",  "product"),

    # 카페
    ("카페", "헥센양 (위스키카페)", "https://cafe.naver.com/hexenyang",  "cafe"),
]

added = 0
skipped = 0

for category, name, url, agent_type in NEW_SITES:
    # URL 중복 체크
    cur.execute("SELECT id FROM crawl_sites WHERE site_url LIKE ?", (f"%{url.split('//')[1].split('?')[0]}%",))
    existing = cur.fetchone()
    if existing:
        # 카테고리만 업데이트
        cur.execute(
            "UPDATE crawl_sites SET category=?, updated_at=datetime('now','localtime') WHERE id=?",
            (category, existing[0]),
        )
        print(f"  [skip] {name} 이미 존재 (#{existing[0]}), category 업데이트")
        skipped += 1
        continue

    cur.execute(
        "INSERT INTO crawl_sites (site_name, site_url, agent_type, category, crawl_config) "
        "VALUES (?, ?, ?, ?, '{}')",
        (name, url, agent_type, category),
    )
    added += 1
    print(f"  [add] {name} ({category}) → #{cur.lastrowid}")

db.conn.commit()

# ─── 4) 결과 요약 ─────────────────────────────────────────────
print(f"\n{'='*60}")
print(f"  완료: 업데이트 {len(EXISTING_UPDATES)}건, 추가 {added}건, 스킵 {skipped}건")
print(f"{'='*60}")

cur.execute("""
    SELECT category, COUNT(*) as cnt, GROUP_CONCAT(site_name, ', ') as sites
    FROM crawl_sites
    GROUP BY category
    ORDER BY category
""")
print("\n카테고리별 사이트:")
for row in cur.fetchall():
    cat = row[0] or '(미분류)'
    print(f"  [{cat}] {row[1]}개: {row[2]}")

cur.execute("SELECT COUNT(*) FROM crawl_sites")
total = cur.fetchone()[0]
print(f"\n  전체 사이트: {total}개")

db.close()
print("\nDone!")
