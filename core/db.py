"""
PostgreSQL DB 연동 모듈

테이블:
  - crawl_sites:           현업 담당자가 등록하는 수집 대상 사이트
  - platforms:             플랫폼 정의 (감지 규칙 + 브라우저 설정)
  - extraction_templates:  플랫폼별 추출 템플릿
  - crawl_results:         수집 모니터링 (상태/건수/소요시간/에러)
  - crawl_data:            수집 원시 데이터 (메달리온 Bronze 레이어)
  - news_keywords:         뉴스 검색 키워드 (사이트별, 활성/비활성)
  - site_credentials:      사이트별 로그인 계정 (복수 계정, 로테이션 지원)
  - ocr_usage_log:         OCR/Document Parser API 사용 이력
  - llm_usage:             LLM API 토큰 사용량 추적
"""
import json
import os
from datetime import datetime

import psycopg2
import psycopg2.extras

# PostgreSQL 연결 기본값
_DEFAULT_PG = {
    "host": os.getenv("DB_HOST", "10.149.67.179"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "dbname": os.getenv("DB_NAME", "aops"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
}


class CrawlDB:
    """크롤링 PostgreSQL DB 관리 클래스"""

    def __init__(self, pg_config: dict | None = None):
        cfg = pg_config or _DEFAULT_PG
        self.conn = psycopg2.connect(
            host=cfg["host"],
            port=cfg["port"],
            dbname=cfg["dbname"],
            user=cfg["user"],
            password=cfg["password"],
        )
        self.conn.autocommit = False
        self._create_tables()

    def close(self):
        if self.conn:
            self.conn.close()

    def _cur(self):
        return self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # ═══════════════════════════════════════════════════════════════
    # 테이블 생성
    # ═══════════════════════════════════════════════════════════════

    def _create_tables(self):
        cur = self._cur()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS platforms (
                id           SERIAL       PRIMARY KEY,
                name         TEXT         NOT NULL UNIQUE,
                display_name TEXT         NOT NULL,
                detection    JSONB        NOT NULL DEFAULT '{}',
                browser      JSONB        NOT NULL DEFAULT '{}',
                is_active    SMALLINT     NOT NULL DEFAULT 1,
                created_at   TIMESTAMP    NOT NULL DEFAULT NOW()
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS extraction_templates (
                id           SERIAL       PRIMARY KEY,
                platform_id  INTEGER      NOT NULL REFERENCES platforms(id),
                target       TEXT         NOT NULL,
                strategy     TEXT         NOT NULL,
                config       JSONB        NOT NULL DEFAULT '{}',
                priority     INTEGER      NOT NULL DEFAULT 0
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS crawl_sites (
                id             SERIAL       PRIMARY KEY,
                site_name      TEXT         NOT NULL,
                site_url       TEXT         NOT NULL,
                is_active      SMALLINT     NOT NULL DEFAULT 1,
                platform_id    INTEGER      REFERENCES platforms(id),
                agent_type     TEXT         NOT NULL DEFAULT 'product',
                crawl_config   JSONB        NOT NULL DEFAULT '{}',
                category       TEXT         NOT NULL DEFAULT '',
                crawl_schedule TEXT         NOT NULL DEFAULT '',
                created_at     TIMESTAMP    NOT NULL DEFAULT NOW(),
                updated_at     TIMESTAMP    NOT NULL DEFAULT NOW()
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS news_keywords (
                id           SERIAL       PRIMARY KEY,
                site_id      INTEGER      NOT NULL REFERENCES crawl_sites(id),
                keyword      TEXT         NOT NULL,
                is_active    SMALLINT     NOT NULL DEFAULT 1,
                created_at   TIMESTAMP    NOT NULL DEFAULT NOW(),
                UNIQUE(site_id, keyword)
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS crawl_results (
                id            SERIAL           PRIMARY KEY,
                site_id       INTEGER          NOT NULL REFERENCES crawl_sites(id),
                crawl_date    TIMESTAMP         NOT NULL DEFAULT NOW(),
                status        TEXT             NOT NULL DEFAULT 'pending',
                product_count INTEGER          NOT NULL DEFAULT 0,
                error_msg     TEXT,
                elapsed_sec   DOUBLE PRECISION
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS ocr_usage_log (
                id            SERIAL       PRIMARY KEY,
                site_id       INTEGER      NOT NULL REFERENCES crawl_sites(id),
                post_id       TEXT,
                image_url     TEXT,
                engine        TEXT         NOT NULL,
                status        TEXT         NOT NULL DEFAULT 'success',
                text_length   INTEGER      NOT NULL DEFAULT 0,
                price_count   INTEGER      NOT NULL DEFAULT 0,
                elapsed_ms    INTEGER      NOT NULL DEFAULT 0,
                error_msg     TEXT,
                created_at    TIMESTAMP    NOT NULL DEFAULT NOW()
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS llm_usage (
                id                SERIAL           PRIMARY KEY,
                site_id           INTEGER          REFERENCES crawl_sites(id),
                agent_type        TEXT             NOT NULL,
                task_type         TEXT             NOT NULL,
                model             TEXT             NOT NULL DEFAULT '',
                prompt_tokens     INTEGER          NOT NULL DEFAULT 0,
                completion_tokens INTEGER          NOT NULL DEFAULT 0,
                total_tokens      INTEGER          NOT NULL DEFAULT 0,
                cost_usd          DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                input_preview     TEXT             NOT NULL DEFAULT '',
                output_preview    TEXT             NOT NULL DEFAULT '',
                elapsed_ms        INTEGER          NOT NULL DEFAULT 0,
                created_at        TIMESTAMP        NOT NULL DEFAULT NOW()
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS agent_field_defs (
                id           SERIAL       PRIMARY KEY,
                agent_type   TEXT         NOT NULL,
                field_key    TEXT         NOT NULL,
                label        TEXT         NOT NULL,
                config_key   TEXT         NOT NULL DEFAULT '',
                sort_order   INTEGER      NOT NULL DEFAULT 0,
                is_active    SMALLINT     NOT NULL DEFAULT 1,
                created_at   TIMESTAMP    NOT NULL DEFAULT NOW(),
                UNIQUE(agent_type, field_key)
            )
        """)
        self._seed_agent_field_defs(cur)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS crawl_failure_log (
                id              SERIAL PRIMARY KEY,
                site_id         INTEGER NOT NULL REFERENCES crawl_sites(id),
                crawl_result_id INTEGER REFERENCES crawl_results(id),
                agent_type      TEXT NOT NULL,
                crawl_date      TIMESTAMP NOT NULL DEFAULT NOW(),
                failure_summary JSONB NOT NULL DEFAULT '{}',
                failure_events  JSONB NOT NULL DEFAULT '[]',
                log_file        TEXT,
                created_at      TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_cfl_site_id ON crawl_failure_log(site_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_cfl_crawl_date ON crawl_failure_log(crawl_date DESC)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_cfl_agent_type ON crawl_failure_log(agent_type)")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS crawl_data (
                id              SERIAL       PRIMARY KEY,
                crawl_result_id INTEGER      NOT NULL REFERENCES crawl_results(id),
                site_id         INTEGER      NOT NULL REFERENCES crawl_sites(id),
                agent_type      TEXT         NOT NULL,
                items           JSONB        NOT NULL DEFAULT '[]',
                store_info      JSONB        DEFAULT '{}',
                item_count      INTEGER      NOT NULL DEFAULT 0,
                created_at      TIMESTAMP    NOT NULL DEFAULT NOW()
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_crawl_data_result ON crawl_data(crawl_result_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_crawl_data_site ON crawl_data(site_id)")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS site_credentials (
                id           SERIAL       PRIMARY KEY,
                site_id      INTEGER      NOT NULL REFERENCES crawl_sites(id),
                login_id     TEXT         NOT NULL,
                login_pwd    TEXT         NOT NULL,
                label        TEXT         NOT NULL DEFAULT '',
                is_active    SMALLINT     NOT NULL DEFAULT 1,
                last_used_at TIMESTAMP,
                created_at   TIMESTAMP    NOT NULL DEFAULT NOW()
            )
        """)

        self.conn.commit()

    # ═══════════════════════════════════════════════════════════════
    # agent_field_defs 시드 / CRUD
    # ═══════════════════════════════════════════════════════════════

    def _seed_agent_field_defs(self, cur):
        cur.execute("SELECT COUNT(*) AS cnt FROM agent_field_defs")
        if cur.fetchone()["cnt"] > 0:
            return

        seeds = [
            ("product", "name",           "상품명",       "collect_fields", 1),
            ("product", "price",          "가격",         "collect_fields", 2),
            ("product", "brand",          "브랜드",       "collect_fields", 3),
            ("product", "image",          "이미지",       "collect_fields", 4),
            ("product", "rank",           "순위",         "collect_fields", 5),
            ("product", "original_price", "원가",         "collect_fields", 6),
            ("product", "discount_rate",  "할인율",       "collect_fields", 7),
            ("product", "gift",           "사은품",       "collect_fields", 8),
            ("product", "reference_no",   "레퍼런스번호", "collect_fields", 9),
            ("product", "category",       "카테고리",     "collect_fields", 10),
            ("product", "detail_page",    "상세수집",     "detail_page",    11),

            ("news", "title",        "제목",     "",              1),
            ("news", "url",          "URL",      "",              2),
            ("news", "press",        "언론사",   "",              3),
            ("news", "date",         "날짜",     "",              4),
            ("news", "description",  "요약",     "",              5),
            ("news", "collect_body", "본문수집", "collect_body",  6),

            ("cafe", "title",          "제목",       "",               1),
            ("cafe", "collect_body",   "본문수집",   "collect_body",   2),
            ("cafe", "collect_links",  "링크수집",   "collect_links",  3),
            ("cafe", "collect_images", "이미지수집", "collect_images", 4),
            ("cafe", "collect_ocr",    "OCR수집",    "collect_ocr",    5),

            ("promotion", "title",                  "이벤트명",   "",                        1),
            ("promotion", "period",                 "기간",       "",                        2),
            ("promotion", "image",                  "이미지",     "",                        3),
            ("promotion", "collect_details",        "상세수집",   "collect_details",         4),
            ("promotion", "collect_event_products", "이벤트상품", "collect_event_products",  5),

            ("banner", "hero",               "히어로배너",  "banner_areas",        1),
            ("banner", "sub_banner",         "서브배너",    "banner_areas",        2),
            ("banner", "popup",              "팝업",        "banner_areas",        3),
            ("banner", "capture_screenshot", "스크린샷",    "capture_screenshot",  4),
            ("banner", "download_images",    "이미지저장",  "download_images",     5),
            ("banner", "include_text",       "텍스트수집",  "include_text",        6),

            ("directory", "name",             "이름",       "collect_fields",      1),
            ("directory", "category",         "카테고리",   "collect_fields",      2),
            ("directory", "branch",           "지점명",     "collect_fields",      3),
            ("directory", "location",         "위치(층)",   "collect_fields",      4),
            ("directory", "phone",            "전화번호",   "collect_fields",      5),
            ("directory", "description",      "설명",       "collect_fields",      6),
            ("directory", "period",           "기간",       "collect_fields",      7),
            ("directory", "status",           "상태",       "collect_fields",      8),
            ("directory", "detail_url",       "상세URL",    "collect_fields",      9),
            ("directory", "index_navigation", "인덱스탐색", "index_navigation",    10),
            ("directory", "collect_details",  "상세수집",   "collect_details",     11),

            ("order", "brand",                  "브랜드",       "collect_fields", 1),
            ("order", "product_name",           "상품명",       "collect_fields", 2),
            ("order", "regular_price_usd",      "정상가($)",    "collect_fields", 3),
            ("order", "regular_price_krw",      "정상가(원)",   "collect_fields", 4),
            ("order", "member_discount_usd",    "회원할인($)",  "collect_fields", 5),
            ("order", "member_discount_krw",    "회원할인(원)", "collect_fields", 6),
            ("order", "member_discount_reason", "할인사유",     "collect_fields", 7),
            ("order", "benefit_usd",            "혜택($)",      "collect_fields", 8),
            ("order", "benefit_krw",            "혜택(원)",     "collect_fields", 9),
            ("order", "benefit_reason",         "혜택사유",     "collect_fields", 10),
            ("order", "payment_usd",            "결제($)",      "collect_fields", 11),
            ("order", "payment_krw",            "결제(원)",     "collect_fields", 12),
            ("order", "discount_rate",          "할인율",       "collect_fields", 13),
            ("order", "duty_free_limit",        "면세한도",     "collect_fields", 14),
            ("order", "tax_point",              "과세포인트",   "collect_fields", 15),
            ("order", "l_point",                "L.POINT",      "collect_fields", 16),
            ("order", "event_coupons",          "이벤트쿠폰",  "event_coupons",  17),
            ("order", "auto_discovery",         "자동탐색",     "auto_discovery", 18),
            ("order", "coupon_keywords",        "쿠폰키워드",  "coupon_keywords", 19),

            ("coupon", "event_coupons",   "이벤트쿠폰",  "event_coupons",   1),
            ("coupon", "auto_discovery",  "자동탐색",     "auto_discovery",  2),
            ("coupon", "coupon_keywords", "쿠폰키워드",  "coupon_keywords", 3),
        ]

        for s in seeds:
            cur.execute(
                "INSERT INTO agent_field_defs "
                "(agent_type, field_key, label, config_key, sort_order) "
                "VALUES (%s, %s, %s, %s, %s) "
                "ON CONFLICT (agent_type, field_key) DO NOTHING",
                s,
            )

    def get_agent_field_defs(self, agent_type: str | None = None) -> list[dict]:
        cur = self._cur()
        if agent_type:
            cur.execute(
                "SELECT * FROM agent_field_defs "
                "WHERE agent_type = %s AND is_active = 1 "
                "ORDER BY sort_order",
                (agent_type,),
            )
        else:
            cur.execute(
                "SELECT * FROM agent_field_defs "
                "WHERE is_active = 1 "
                "ORDER BY agent_type, sort_order",
            )
        return [dict(row) for row in cur.fetchall()]

    def upsert_agent_field_def(
        self, agent_type: str, field_key: str, label: str,
        config_key: str = "", sort_order: int = 0,
    ) -> int:
        cur = self._cur()
        cur.execute(
            "INSERT INTO agent_field_defs "
            "(agent_type, field_key, label, config_key, sort_order) "
            "VALUES (%s, %s, %s, %s, %s) "
            "ON CONFLICT (agent_type, field_key) DO UPDATE SET "
            "label = EXCLUDED.label, config_key = EXCLUDED.config_key, "
            "sort_order = EXCLUDED.sort_order, is_active = 1 "
            "RETURNING id",
            (agent_type, field_key, label, config_key, sort_order),
        )
        row_id = cur.fetchone()["id"]
        self.conn.commit()
        return row_id

    def delete_agent_field_def(self, agent_type: str, field_key: str):
        cur = self._cur()
        cur.execute(
            "UPDATE agent_field_defs SET is_active = 0 "
            "WHERE agent_type = %s AND field_key = %s",
            (agent_type, field_key),
        )
        self.conn.commit()

    # ═══════════════════════════════════════════════════════════════
    # crawl_sites CRUD
    # ═══════════════════════════════════════════════════════════════

    def add_site(
        self, site_name: str, site_url: str,
        agent_type: str = "product",
        crawl_config: dict | None = None,
    ) -> int:
        cur = self._cur()
        cur.execute(
            "INSERT INTO crawl_sites "
            "(site_name, site_url, agent_type, crawl_config) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (
                site_name,
                site_url,
                agent_type,
                json.dumps(crawl_config or {}, ensure_ascii=False),
            ),
        )
        row_id = cur.fetchone()["id"]
        self.conn.commit()
        return row_id

    def get_active_sites(self) -> list[dict]:
        cur = self._cur()
        cur.execute(
            "SELECT * FROM crawl_sites WHERE is_active = 1 ORDER BY id",
        )
        return [dict(row) for row in cur.fetchall()]

    def get_site(self, site_id: int) -> dict | None:
        cur = self._cur()
        cur.execute("SELECT * FROM crawl_sites WHERE id = %s", (site_id,))
        row = cur.fetchone()
        return dict(row) if row else None

    def get_all_sites(self) -> list[dict]:
        cur = self._cur()
        cur.execute("SELECT * FROM crawl_sites ORDER BY id")
        return [dict(row) for row in cur.fetchall()]

    def update_site_platform(self, site_id: int, platform_id: int):
        cur = self._cur()
        cur.execute(
            "UPDATE crawl_sites SET platform_id = %s, updated_at = %s WHERE id = %s",
            (platform_id, _now(), site_id),
        )
        self.conn.commit()

    def deactivate_site(self, site_id: int):
        cur = self._cur()
        cur.execute(
            "UPDATE crawl_sites SET is_active = 0, updated_at = %s WHERE id = %s",
            (_now(), site_id),
        )
        self.conn.commit()

    def activate_site(self, site_id: int):
        cur = self._cur()
        cur.execute(
            "UPDATE crawl_sites SET is_active = 1, updated_at = %s WHERE id = %s",
            (_now(), site_id),
        )
        self.conn.commit()

    def get_crawl_config(self, site_id: int) -> dict:
        site = self.get_site(site_id)
        if not site:
            return {}
        raw = site.get("crawl_config", "{}")
        if isinstance(raw, dict):
            return raw
        try:
            return json.loads(raw) if isinstance(raw, str) else (raw or {})
        except (json.JSONDecodeError, TypeError):
            return {}

    def update_crawl_config(self, site_id: int, crawl_config: dict):
        cur = self._cur()
        cur.execute(
            "UPDATE crawl_sites SET crawl_config = %s, updated_at = %s WHERE id = %s",
            (json.dumps(crawl_config, ensure_ascii=False), _now(), site_id),
        )
        self.conn.commit()

    def update_site_agent_type(self, site_id: int, agent_type: str):
        cur = self._cur()
        cur.execute(
            "UPDATE crawl_sites SET agent_type = %s, updated_at = %s WHERE id = %s",
            (agent_type, _now(), site_id),
        )
        self.conn.commit()

    def get_active_sites_by_agent(self, agent_type: str) -> list[dict]:
        cur = self._cur()
        cur.execute(
            "SELECT * FROM crawl_sites "
            "WHERE is_active = 1 AND agent_type = %s ORDER BY id",
            (agent_type,),
        )
        return [dict(row) for row in cur.fetchall()]

    # ═══════════════════════════════════════════════════════════════
    # platforms CRUD
    # ═══════════════════════════════════════════════════════════════

    def add_platform(self, platform_data: dict) -> int:
        cur = self._cur()
        cur.execute(
            "INSERT INTO platforms (name, display_name, detection, browser) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (
                platform_data["name"],
                platform_data.get("display_name", platform_data["name"]),
                json.dumps(platform_data.get("detection", {}), ensure_ascii=False),
                json.dumps(platform_data.get("browser", {}), ensure_ascii=False),
            ),
        )
        row_id = cur.fetchone()["id"]
        self.conn.commit()
        return row_id

    def get_platform(self, platform_id: int) -> dict | None:
        cur = self._cur()
        cur.execute("SELECT * FROM platforms WHERE id = %s", (platform_id,))
        row = cur.fetchone()
        if not row:
            return None
        d = dict(row)
        if isinstance(d.get("detection"), str):
            d["detection"] = json.loads(d["detection"])
        if isinstance(d.get("browser"), str):
            d["browser"] = json.loads(d["browser"])
        return d

    def get_platform_by_name(self, name: str) -> dict | None:
        cur = self._cur()
        cur.execute("SELECT * FROM platforms WHERE name = %s", (name,))
        row = cur.fetchone()
        if not row:
            return None
        d = dict(row)
        if isinstance(d.get("detection"), str):
            d["detection"] = json.loads(d["detection"])
        if isinstance(d.get("browser"), str):
            d["browser"] = json.loads(d["browser"])
        return d

    def get_all_platforms(self) -> list[dict]:
        cur = self._cur()
        cur.execute("SELECT * FROM platforms WHERE is_active = 1 ORDER BY id")
        result = []
        for row in cur.fetchall():
            d = dict(row)
            if isinstance(d.get("detection"), str):
                d["detection"] = json.loads(d["detection"])
            if isinstance(d.get("browser"), str):
                d["browser"] = json.loads(d["browser"])
            result.append(d)
        return result

    def find_platform_by_detection(
        self, page_url: str, detected_vars: list[str], meta: dict,
    ) -> dict | None:
        import re as _re

        platforms = self.get_all_platforms()
        for platform in platforms:
            detection = platform.get("detection", {})
            rules = detection.get("rules", [])
            match_mode = detection.get("match_mode", "all")

            if not rules:
                continue

            results = []
            for rule in rules:
                rule_type = rule.get("type", "")

                if rule_type == "js_var_exists":
                    var_name = rule.get("var", "")
                    results.append(var_name in detected_vars)

                elif rule_type == "url_match":
                    pattern = rule.get("pattern", "")
                    try:
                        results.append(bool(_re.search(pattern, page_url)))
                    except _re.error:
                        results.append(False)

                elif rule_type == "meta_match":
                    meta_name = rule.get("name", "")
                    content_pattern = rule.get("content", "")
                    meta_val = meta.get(meta_name, "")
                    try:
                        results.append(bool(_re.search(content_pattern, meta_val)))
                    except _re.error:
                        results.append(False)
                else:
                    results.append(False)

            if match_mode == "all" and all(results):
                return platform
            elif match_mode == "any" and any(results):
                return platform

        return None

    # ═══════════════════════════════════════════════════════════════
    # extraction_templates CRUD
    # ═══════════════════════════════════════════════════════════════

    def add_template(self, platform_id: int, template_data: dict) -> int:
        cur = self._cur()
        cur.execute(
            "INSERT INTO extraction_templates "
            "(platform_id, target, strategy, config, priority) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (
                platform_id,
                template_data["target"],
                template_data["strategy"],
                json.dumps(template_data.get("config", {}), ensure_ascii=False),
                template_data.get("priority", 0),
            ),
        )
        row_id = cur.fetchone()["id"]
        self.conn.commit()
        return row_id

    def get_templates_for_platform(self, platform_id: int) -> list[dict]:
        cur = self._cur()
        cur.execute(
            "SELECT * FROM extraction_templates "
            "WHERE platform_id = %s ORDER BY target, priority DESC",
            (platform_id,),
        )
        result = []
        for row in cur.fetchall():
            d = dict(row)
            if isinstance(d.get("config"), str):
                d["config"] = json.loads(d["config"])
            result.append(d)
        return result

    def get_template(self, platform_id: int, target: str) -> dict | None:
        cur = self._cur()
        cur.execute(
            "SELECT * FROM extraction_templates "
            "WHERE platform_id = %s AND target = %s ORDER BY priority DESC LIMIT 1",
            (platform_id, target),
        )
        row = cur.fetchone()
        if not row:
            return None
        d = dict(row)
        if isinstance(d.get("config"), str):
            d["config"] = json.loads(d["config"])
        return d

    def delete_templates_for_platform(self, platform_id: int):
        cur = self._cur()
        cur.execute(
            "DELETE FROM extraction_templates WHERE platform_id = %s",
            (platform_id,),
        )
        self.conn.commit()

    # ═══════════════════════════════════════════════════════════════
    # crawl_results CRUD
    # ═══════════════════════════════════════════════════════════════

    def create_result(self, site_id: int) -> int:
        cur = self._cur()
        cur.execute(
            "INSERT INTO crawl_results (site_id, status) "
            "VALUES (%s, 'running') RETURNING id",
            (site_id,),
        )
        row_id = cur.fetchone()["id"]
        self.conn.commit()
        return row_id

    def update_result(
        self,
        result_id: int,
        status: str,
        store_info: dict | None = None,
        products: list | None = None,
        product_count: int = 0,
        error_msg: str | None = None,
        elapsed_sec: float | None = None,
    ):
        cur = self._cur()
        cur.execute(
            "UPDATE crawl_results SET "
            "status = %s, "
            "product_count = %s, error_msg = %s, elapsed_sec = %s "
            "WHERE id = %s",
            (
                status,
                product_count,
                error_msg,
                elapsed_sec,
                result_id,
            ),
        )
        if products is not None:
            cur.execute(
                "SELECT site_id FROM crawl_results WHERE id = %s",
                (result_id,),
            )
            row = cur.fetchone()
            site_id = row["site_id"] if row else 0
            agent_type = ""
            if site_id:
                cur.execute(
                    "SELECT agent_type FROM crawl_sites WHERE id = %s",
                    (site_id,),
                )
                site_row = cur.fetchone()
                agent_type = site_row["agent_type"] if site_row else ""
            cur.execute(
                "INSERT INTO crawl_data "
                "(crawl_result_id, site_id, agent_type, items, store_info, item_count) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (
                    result_id,
                    site_id,
                    agent_type,
                    json.dumps(products, ensure_ascii=False),
                    json.dumps(store_info, ensure_ascii=False) if store_info else "{}",
                    product_count,
                ),
            )
        self.conn.commit()

    def mark_running_as_stopped(self, site_id: int | None = None) -> int:
        cur = self._cur()
        if site_id is not None:
            cur.execute(
                "UPDATE crawl_results SET status = 'stopped', "
                "error_msg = '사용자에 의해 강제 종료됨' "
                "WHERE status = 'running' AND site_id = %s",
                (site_id,),
            )
        else:
            cur.execute(
                "UPDATE crawl_results SET status = 'stopped', "
                "error_msg = '서버 재시작으로 인한 강제 종료' "
                "WHERE status = 'running'",
            )
        count = cur.rowcount
        self.conn.commit()
        return count

    def get_latest_result(self, site_id: int) -> dict | None:
        cur = self._cur()
        cur.execute(
            "SELECT * FROM crawl_results "
            "WHERE site_id = %s ORDER BY crawl_date DESC LIMIT 1",
            (site_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        d = dict(row)
        crawl_data = self.get_crawl_data(d["id"])
        if crawl_data:
            d["items"] = crawl_data.get("items")
            d["store_info"] = crawl_data.get("store_info")
        return d

    def get_crawl_data(self, result_id: int) -> dict | None:
        cur = self._cur()
        cur.execute(
            "SELECT * FROM crawl_data WHERE crawl_result_id = %s",
            (result_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        d = dict(row)
        if isinstance(d.get("items"), str):
            d["items"] = json.loads(d["items"])
        if isinstance(d.get("store_info"), str):
            d["store_info"] = json.loads(d["store_info"])
        return d

    # ═══════════════════════════════════════════════════════════════
    # news_keywords CRUD
    # ═══════════════════════════════════════════════════════════════

    def add_keyword(self, site_id: int, keyword: str) -> int | None:
        cur = self._cur()
        cur.execute(
            "SELECT id, is_active FROM news_keywords "
            "WHERE site_id = %s AND keyword = %s",
            (site_id, keyword),
        )
        row = cur.fetchone()
        if row:
            if not row["is_active"]:
                cur.execute(
                    "UPDATE news_keywords SET is_active = 1 WHERE id = %s",
                    (row["id"],),
                )
                self.conn.commit()
            return None
        cur.execute(
            "INSERT INTO news_keywords (site_id, keyword) "
            "VALUES (%s, %s) RETURNING id",
            (site_id, keyword),
        )
        row_id = cur.fetchone()["id"]
        self.conn.commit()
        return row_id

    def add_keywords(self, site_id: int, keywords: list[str]) -> int:
        added = 0
        for kw in keywords:
            kw = kw.strip()
            if not kw:
                continue
            result = self.add_keyword(site_id, kw)
            if result is not None:
                added += 1
        return added

    def remove_keyword(self, site_id: int, keyword: str) -> bool:
        cur = self._cur()
        cur.execute(
            "DELETE FROM news_keywords WHERE site_id = %s AND keyword = %s",
            (site_id, keyword),
        )
        deleted = cur.rowcount > 0
        self.conn.commit()
        return deleted

    def get_keywords(self, site_id: int) -> list[dict]:
        cur = self._cur()
        cur.execute(
            "SELECT * FROM news_keywords "
            "WHERE site_id = %s ORDER BY id",
            (site_id,),
        )
        return [dict(row) for row in cur.fetchall()]

    def get_active_keywords(self, site_id: int) -> list[str]:
        cur = self._cur()
        cur.execute(
            "SELECT keyword FROM news_keywords "
            "WHERE site_id = %s AND is_active = 1 ORDER BY id",
            (site_id,),
        )
        return [row["keyword"] for row in cur.fetchall()]

    def set_keyword_active(
        self, site_id: int, keyword: str, is_active: bool,
    ) -> bool:
        cur = self._cur()
        cur.execute(
            "UPDATE news_keywords SET is_active = %s "
            "WHERE site_id = %s AND keyword = %s",
            (1 if is_active else 0, site_id, keyword),
        )
        updated = cur.rowcount > 0
        self.conn.commit()
        return updated

    def migrate_keywords_from_config(self, site_id: int) -> int:
        existing = self.get_keywords(site_id)
        if existing:
            return 0

        config = self.get_crawl_config(site_id)
        keywords = config.get("search_keywords", [])
        if not keywords:
            return 0

        return self.add_keywords(site_id, keywords)

    # ═══════════════════════════════════════════════════════════════
    # site_credentials CRUD
    # ═══════════════════════════════════════════════════════════════

    def add_credential(
        self, site_id: int, login_id: str, login_pwd: str, label: str = "",
    ) -> int:
        cur = self._cur()
        cur.execute(
            "INSERT INTO site_credentials (site_id, login_id, login_pwd, label) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (site_id, login_id, login_pwd, label),
        )
        row_id = cur.fetchone()["id"]
        self.conn.commit()
        return row_id

    def get_credentials(self, site_id: int) -> list[dict]:
        cur = self._cur()
        cur.execute(
            "SELECT * FROM site_credentials "
            "WHERE site_id = %s ORDER BY id",
            (site_id,),
        )
        return [dict(row) for row in cur.fetchall()]

    def get_active_credentials(self, site_id: int) -> list[dict]:
        cur = self._cur()
        cur.execute(
            "SELECT * FROM site_credentials "
            "WHERE site_id = %s AND is_active = 1 "
            "ORDER BY last_used_at ASC NULLS FIRST, id ASC",
            (site_id,),
        )
        return [dict(row) for row in cur.fetchall()]

    def update_credential(
        self, cred_id: int, login_id: str, login_pwd: str, label: str = "",
    ) -> bool:
        cur = self._cur()
        cur.execute(
            "UPDATE site_credentials "
            "SET login_id = %s, login_pwd = %s, label = %s WHERE id = %s",
            (login_id, login_pwd, label, cred_id),
        )
        updated = cur.rowcount > 0
        self.conn.commit()
        return updated

    def delete_credential(self, cred_id: int) -> bool:
        cur = self._cur()
        cur.execute(
            "DELETE FROM site_credentials WHERE id = %s", (cred_id,),
        )
        deleted = cur.rowcount > 0
        self.conn.commit()
        return deleted

    def toggle_credential(self, cred_id: int) -> dict | None:
        cur = self._cur()
        cur.execute("SELECT id, is_active FROM site_credentials WHERE id = %s", (cred_id,))
        row = cur.fetchone()
        if not row:
            return None
        new_active = 0 if row["is_active"] else 1
        cur.execute(
            "UPDATE site_credentials SET is_active = %s WHERE id = %s",
            (new_active, cred_id),
        )
        self.conn.commit()
        return {"id": cred_id, "is_active": new_active}

    def mark_credential_used(self, cred_id: int):
        cur = self._cur()
        cur.execute(
            "UPDATE site_credentials SET last_used_at = %s WHERE id = %s",
            (_now(), cred_id),
        )
        self.conn.commit()

    # ═══════════════════════════════════════════════════════════════
    # ocr_usage_log CRUD
    # ═══════════════════════════════════════════════════════════════

    def add_ocr_usage(
        self,
        site_id: int,
        engine: str,
        status: str = "success",
        post_id: str = "",
        image_url: str = "",
        text_length: int = 0,
        price_count: int = 0,
        elapsed_ms: int = 0,
        error_msg: str = "",
    ) -> int:
        cur = self._cur()
        cur.execute(
            "INSERT INTO ocr_usage_log "
            "(site_id, post_id, image_url, engine, status, "
            " text_length, price_count, elapsed_ms, error_msg) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (
                site_id,
                post_id,
                image_url[:500] if image_url else "",
                engine,
                status,
                text_length,
                price_count,
                elapsed_ms,
                error_msg[:500] if error_msg else "",
            ),
        )
        row_id = cur.fetchone()["id"]
        self.conn.commit()
        return row_id

    def get_ocr_usage_summary(self, site_id: int = 0) -> list[dict]:
        cur = self._cur()
        where = "WHERE site_id = %s" if site_id else ""
        params = (site_id,) if site_id else ()
        cur.execute(f"""
            SELECT
                engine,
                COUNT(*)                                    AS total,
                SUM(CASE WHEN status='success' THEN 1 ELSE 0 END)    AS success_count,
                SUM(CASE WHEN status='fail' THEN 1 ELSE 0 END)       AS fail_count,
                SUM(CASE WHEN status='rate_limit' THEN 1 ELSE 0 END) AS rate_limit_count,
                SUM(text_length)                            AS total_text_length,
                SUM(price_count)                            AS total_price_count,
                ROUND(AVG(elapsed_ms))                      AS avg_elapsed_ms,
                MIN(created_at)                             AS first_used,
                MAX(created_at)                             AS last_used
            FROM ocr_usage_log
            {where}
            GROUP BY engine
            ORDER BY total DESC
        """, params)
        return [dict(row) for row in cur.fetchall()]

    def get_ocr_usage_detail(
        self, site_id: int = 0, limit: int = 100,
    ) -> list[dict]:
        cur = self._cur()
        where = "WHERE site_id = %s" if site_id else ""
        params = (site_id, limit) if site_id else (limit,)
        cur.execute(f"""
            SELECT * FROM ocr_usage_log
            {where}
            ORDER BY id DESC
            LIMIT %s
        """, params)
        return [dict(row) for row in cur.fetchall()]

    # ═══════════════════════════════════════════════════════════════
    # llm_usage CRUD
    # ═══════════════════════════════════════════════════════════════

    def add_llm_usage(
        self,
        agent_type: str,
        task_type: str,
        model: str = "",
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cost_usd: float = 0.0,
        site_id: int | None = None,
        input_preview: str = "",
        output_preview: str = "",
        elapsed_ms: int = 0,
    ) -> int:
        total = prompt_tokens + completion_tokens
        cur = self._cur()
        cur.execute(
            "INSERT INTO llm_usage "
            "(site_id, agent_type, task_type, model, "
            " prompt_tokens, completion_tokens, total_tokens, cost_usd, "
            " input_preview, output_preview, elapsed_ms) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (
                site_id,
                agent_type,
                task_type,
                model,
                prompt_tokens,
                completion_tokens,
                total,
                cost_usd,
                (input_preview[:100] if input_preview else ""),
                (output_preview[:100] if output_preview else ""),
                elapsed_ms,
            ),
        )
        row_id = cur.fetchone()["id"]
        self.conn.commit()
        return row_id

    def get_llm_usage_summary(self) -> dict:
        cur = self._cur()

        cur.execute("""
            SELECT
                COUNT(*)                   AS total_calls,
                COALESCE(SUM(prompt_tokens), 0)     AS total_prompt_tokens,
                COALESCE(SUM(completion_tokens), 0) AS total_completion_tokens,
                COALESCE(SUM(total_tokens), 0)      AS total_tokens,
                COALESCE(SUM(cost_usd), 0)          AS total_cost_usd,
                MIN(created_at)            AS first_used,
                MAX(created_at)            AS last_used
            FROM llm_usage
        """)
        summary = dict(cur.fetchone())

        cur.execute("""
            SELECT
                agent_type,
                COUNT(*)                   AS calls,
                SUM(prompt_tokens)         AS prompt_tokens,
                SUM(completion_tokens)     AS completion_tokens,
                SUM(total_tokens)          AS total_tokens,
                SUM(cost_usd)              AS cost_usd
            FROM llm_usage
            GROUP BY agent_type
            ORDER BY total_tokens DESC
        """)
        summary["by_agent"] = [dict(r) for r in cur.fetchall()]

        cur.execute("""
            SELECT
                task_type,
                COUNT(*)                   AS calls,
                SUM(prompt_tokens)         AS prompt_tokens,
                SUM(completion_tokens)     AS completion_tokens,
                SUM(total_tokens)          AS total_tokens,
                SUM(cost_usd)              AS cost_usd
            FROM llm_usage
            GROUP BY task_type
            ORDER BY total_tokens DESC
        """)
        summary["by_task"] = [dict(r) for r in cur.fetchall()]

        cur.execute("""
            SELECT
                model,
                COUNT(*)                   AS calls,
                SUM(prompt_tokens)         AS prompt_tokens,
                SUM(completion_tokens)     AS completion_tokens,
                SUM(total_tokens)          AS total_tokens,
                SUM(cost_usd)              AS cost_usd
            FROM llm_usage
            GROUP BY model
            ORDER BY total_tokens DESC
        """)
        summary["by_model"] = [dict(r) for r in cur.fetchall()]

        cur.execute("""
            SELECT
                DATE(created_at) AS date,
                COUNT(*)                   AS calls,
                SUM(prompt_tokens)         AS prompt_tokens,
                SUM(completion_tokens)     AS completion_tokens,
                SUM(total_tokens)          AS total_tokens,
                SUM(cost_usd)              AS cost_usd
            FROM llm_usage
            WHERE created_at >= CURRENT_DATE - INTERVAL '30 days'
            GROUP BY DATE(created_at)
            ORDER BY date
        """)
        summary["daily"] = [dict(r) for r in cur.fetchall()]

        return summary

    def get_llm_usage_detail(
        self,
        agent_type: str = "",
        task_type: str = "",
        site_id: int = 0,
        limit: int = 100,
    ) -> list[dict]:
        cur = self._cur()
        conditions = []
        params = []
        if agent_type:
            conditions.append("l.agent_type = %s")
            params.append(agent_type)
        if task_type:
            conditions.append("l.task_type = %s")
            params.append(task_type)
        if site_id:
            conditions.append("l.site_id = %s")
            params.append(site_id)
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        params.append(limit)
        cur.execute(f"""
            SELECT l.*, s.site_name
            FROM llm_usage l
            LEFT JOIN crawl_sites s ON l.site_id = s.id
            {where}
            ORDER BY l.id DESC
            LIMIT %s
        """, params)
        return [dict(r) for r in cur.fetchall()]

    # ═══════════════════════════════════════════════════════════════
    # crawl_failure_log CRUD
    # ═══════════════════════════════════════════════════════════════

    def insert_failure_log(
        self,
        site_id: int,
        crawl_result_id: int,
        agent_type: str,
        failure_summary: dict,
        failure_events: list,
        log_file: str | None = None,
    ) -> int:
        """크롤링 실패 로그를 저장한다."""
        cur = self._cur()
        cur.execute(
            "INSERT INTO crawl_failure_log "
            "(site_id, crawl_result_id, agent_type, failure_summary, "
            " failure_events, log_file) "
            "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
            (
                site_id,
                crawl_result_id,
                agent_type,
                json.dumps(failure_summary, ensure_ascii=False),
                json.dumps(failure_events, ensure_ascii=False),
                log_file,
            ),
        )
        row_id = cur.fetchone()["id"]
        self.conn.commit()
        return row_id

    def get_failure_logs(
        self,
        site_id: int = 0,
        agent_type: str = "",
        date_from: str = "",
        date_to: str = "",
        limit: int = 50,
    ) -> list[dict]:
        """실패 로그 목록을 조회한다."""
        cur = self._cur()
        conditions = []
        params = []
        if site_id:
            conditions.append("f.site_id = %s")
            params.append(site_id)
        if agent_type:
            conditions.append("f.agent_type = %s")
            params.append(agent_type)
        if date_from:
            conditions.append("f.crawl_date >= %s")
            params.append(date_from)
        if date_to:
            conditions.append("f.crawl_date <= %s")
            params.append(date_to + " 23:59:59")
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        params.append(limit)
        cur.execute(f"""
            SELECT f.id, f.site_id, s.site_name, f.agent_type,
                   f.crawl_result_id, f.crawl_date, f.failure_summary,
                   f.log_file, f.created_at
            FROM crawl_failure_log f
            JOIN crawl_sites s ON f.site_id = s.id
            {where}
            ORDER BY f.crawl_date DESC
            LIMIT %s
        """, params)
        return [dict(r) for r in cur.fetchall()]

    def get_failure_log_detail(self, failure_id: int) -> dict | None:
        """실패 로그 단건 상세 (failure_events 포함)."""
        cur = self._cur()
        cur.execute("""
            SELECT f.*, s.site_name
            FROM crawl_failure_log f
            JOIN crawl_sites s ON f.site_id = s.id
            WHERE f.id = %s
        """, (failure_id,))
        row = cur.fetchone()
        return dict(row) if row else None

    def get_failure_stats(self, days: int = 30) -> dict:
        """기간별 실패 통계 요약."""
        cur = self._cur()

        # 전체 요약
        cur.execute("""
            SELECT
                COUNT(*) AS total_crawls,
                COALESCE(SUM((failure_summary->>'total')::int), 0) AS total_events,
                COALESCE(SUM((failure_summary->>'http_block')::int), 0) AS http_block,
                COALESCE(SUM((failure_summary->>'soft_block')::int), 0) AS soft_block,
                COALESCE(SUM((failure_summary->>'login_fail')::int), 0) AS login_fail,
                COALESCE(SUM((failure_summary->>'click_fail')::int), 0) AS click_fail,
                COALESCE(SUM((failure_summary->>'nav_fail')::int), 0) AS nav_fail,
                COALESCE(SUM((failure_summary->>'data_fail')::int), 0) AS data_fail,
                COALESCE(SUM((failure_summary->>'exception')::int), 0) AS exception
            FROM crawl_failure_log
            WHERE crawl_date >= CURRENT_DATE - INTERVAL '%s days'
        """ % days)
        summary = dict(cur.fetchone())

        # 에이전트별
        cur.execute("""
            SELECT agent_type,
                   COUNT(*) AS crawl_count,
                   COALESCE(SUM((failure_summary->>'total')::int), 0) AS event_count
            FROM crawl_failure_log
            WHERE crawl_date >= CURRENT_DATE - INTERVAL '%s days'
            GROUP BY agent_type
            ORDER BY event_count DESC
        """ % days)
        summary["by_agent"] = [dict(r) for r in cur.fetchall()]

        # 사이트별
        cur.execute("""
            SELECT f.site_id, s.site_name,
                   COUNT(*) AS crawl_count,
                   COALESCE(SUM((failure_summary->>'total')::int), 0) AS event_count
            FROM crawl_failure_log f
            JOIN crawl_sites s ON f.site_id = s.id
            WHERE f.crawl_date >= CURRENT_DATE - INTERVAL '%s days'
            GROUP BY f.site_id, s.site_name
            ORDER BY event_count DESC
        """ % days)
        summary["by_site"] = [dict(r) for r in cur.fetchall()]

        # 일별 추이
        cur.execute("""
            SELECT DATE(crawl_date) AS date,
                   COUNT(*) AS crawl_count,
                   COALESCE(SUM((failure_summary->>'total')::int), 0) AS event_count
            FROM crawl_failure_log
            WHERE crawl_date >= CURRENT_DATE - INTERVAL '%s days'
            GROUP BY DATE(crawl_date)
            ORDER BY date
        """ % days)
        summary["daily"] = [dict(r) for r in cur.fetchall()]

        return summary

    # ═══════════════════════════════════════════════════════════════
    # LLM 분석 결과 일괄 저장
    # ═══════════════════════════════════════════════════════════════

    def save_llm_analysis(self, llm_result: dict, site_id: int) -> int:
        platform_data = llm_result["platform"]
        templates = llm_result["templates"]

        existing = self.get_platform_by_name(platform_data["name"])
        if existing:
            platform_id = existing["id"]
            self.delete_templates_for_platform(platform_id)
            cur = self._cur()
            cur.execute(
                "UPDATE platforms SET browser = %s, detection = %s "
                "WHERE id = %s",
                (
                    json.dumps(
                        platform_data.get("browser", {}),
                        ensure_ascii=False,
                    ),
                    json.dumps(
                        platform_data.get("detection", {}),
                        ensure_ascii=False,
                    ),
                    platform_id,
                ),
            )
            self.conn.commit()
        else:
            platform_id = self.add_platform(platform_data)

        for tmpl in templates:
            self.add_template(platform_id, tmpl)

        self.update_site_platform(site_id, platform_id)

        print(f"[db] 플랫폼 '{platform_data['name']}' (ID={platform_id}) 저장 완료, "
              f"템플릿 {len(templates)}개")
        return platform_id


# ─── 유틸 ────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
