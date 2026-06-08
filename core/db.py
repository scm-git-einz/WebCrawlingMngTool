"""
SQLite DB 연동 모듈

테이블:
  - crawl_sites:           현업 담당자가 등록하는 수집 대상 사이트
  - platforms:             플랫폼 정의 (감지 규칙 + 브라우저 설정)
  - extraction_templates:  플랫폼별 추출 템플릿
  - crawl_results:         수집 결과
  - news_keywords:         뉴스 검색 키워드 (사이트별, 활성/비활성)
  - site_credentials:      사이트별 로그인 계정 (복수 계정, 로테이션 지원)
  - ocr_usage_log:         OCR/Document Parser API 사용 이력
"""
import json
import os
import sqlite3
from datetime import datetime

# DB 파일 기본 경로
_DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "crawling.db",
)


class CrawlDB:
    """크롤링 SQLite DB 관리 클래스"""

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or _DEFAULT_DB_PATH
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def close(self):
        """DB 연결을 닫는다."""
        if self.conn:
            self.conn.close()

    # ═══════════════════════════════════════════════════════════════
    # 테이블 생성
    # ═══════════════════════════════════════════════════════════════

    def _create_tables(self):
        cur = self.conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS platforms (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                name         TEXT    NOT NULL UNIQUE,
                display_name TEXT    NOT NULL,
                detection    TEXT    NOT NULL DEFAULT '{}',
                browser      TEXT    NOT NULL DEFAULT '{}',
                is_active    INTEGER NOT NULL DEFAULT 1,
                created_at   TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS extraction_templates (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                platform_id  INTEGER NOT NULL,
                target       TEXT    NOT NULL,
                strategy     TEXT    NOT NULL,
                config       TEXT    NOT NULL DEFAULT '{}',
                priority     INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (platform_id) REFERENCES platforms(id)
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS crawl_sites (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                site_name    TEXT    NOT NULL,
                site_url     TEXT    NOT NULL,
                is_active    INTEGER NOT NULL DEFAULT 1,
                platform_id  INTEGER,
                agent_type   TEXT    NOT NULL DEFAULT 'product',
                crawl_config TEXT    NOT NULL DEFAULT '{}',
                created_at   TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
                updated_at   TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (platform_id) REFERENCES platforms(id)
            )
        """)

        # 기존 DB 마이그레이션: crawl_config, agent_type 컬럼 추가
        self._migrate_crawl_sites(cur)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS news_keywords (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                site_id      INTEGER NOT NULL,
                keyword      TEXT    NOT NULL,
                is_active    INTEGER NOT NULL DEFAULT 1,
                created_at   TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (site_id) REFERENCES crawl_sites(id),
                UNIQUE(site_id, keyword)
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS crawl_results (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                site_id       INTEGER NOT NULL,
                crawl_date    TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
                status        TEXT    NOT NULL DEFAULT 'pending',
                store_info    TEXT,
                products      TEXT,
                product_count INTEGER NOT NULL DEFAULT 0,
                error_msg     TEXT,
                elapsed_sec   REAL,
                FOREIGN KEY (site_id) REFERENCES crawl_sites(id)
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS ocr_usage_log (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                site_id       INTEGER NOT NULL,
                post_id       TEXT,
                image_url     TEXT,
                engine        TEXT    NOT NULL,
                status        TEXT    NOT NULL DEFAULT 'success',
                text_length   INTEGER NOT NULL DEFAULT 0,
                price_count   INTEGER NOT NULL DEFAULT 0,
                elapsed_ms    INTEGER NOT NULL DEFAULT 0,
                error_msg     TEXT,
                created_at    TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (site_id) REFERENCES crawl_sites(id)
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS site_credentials (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                site_id      INTEGER NOT NULL,
                login_id     TEXT    NOT NULL,
                login_pwd    TEXT    NOT NULL,
                label        TEXT    NOT NULL DEFAULT '',
                is_active    INTEGER NOT NULL DEFAULT 1,
                last_used_at TEXT,
                created_at   TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (site_id) REFERENCES crawl_sites(id)
            )
        """)

        self.conn.commit()

    def _migrate_crawl_sites(self, cur):
        """기존 crawl_sites 테이블에 새 컬럼이 없으면 추가한다."""
        try:
            cur.execute("PRAGMA table_info(crawl_sites)")
            columns = {row[1] for row in cur.fetchall()}

            if "crawl_config" not in columns:
                cur.execute(
                    "ALTER TABLE crawl_sites "
                    "ADD COLUMN crawl_config TEXT NOT NULL DEFAULT '{}'"
                )
                print("[db] crawl_sites.crawl_config 컬럼 추가됨")

            if "agent_type" not in columns:
                cur.execute(
                    "ALTER TABLE crawl_sites "
                    "ADD COLUMN agent_type TEXT NOT NULL DEFAULT 'product'"
                )
                print("[db] crawl_sites.agent_type 컬럼 추가됨")

            if "category" not in columns:
                cur.execute(
                    "ALTER TABLE crawl_sites "
                    "ADD COLUMN category TEXT NOT NULL DEFAULT ''"
                )
                print("[db] crawl_sites.category 컬럼 추가됨")

            if "crawl_schedule" not in columns:
                cur.execute(
                    "ALTER TABLE crawl_sites "
                    "ADD COLUMN crawl_schedule TEXT NOT NULL DEFAULT ''"
                )
                print("[db] crawl_sites.crawl_schedule 컬럼 추가됨")

            self.conn.commit()
        except Exception:
            pass  # 이미 존재하면 무시

    # ═══════════════════════════════════════════════════════════════
    # crawl_sites CRUD
    # ═══════════════════════════════════════════════════════════════

    def add_site(
        self, site_name: str, site_url: str,
        agent_type: str = "product",
        crawl_config: dict | None = None,
    ) -> int:
        """사이트를 등록하고 생성된 ID 를 반환한다."""
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO crawl_sites "
            "(site_name, site_url, agent_type, crawl_config) "
            "VALUES (?, ?, ?, ?)",
            (
                site_name,
                site_url,
                agent_type,
                json.dumps(crawl_config or {}, ensure_ascii=False),
            ),
        )
        self.conn.commit()
        return cur.lastrowid

    def get_active_sites(self) -> list[dict]:
        """활성 상태인 사이트 목록을 반환한다."""
        cur = self.conn.cursor()
        cur.execute(
            "SELECT * FROM crawl_sites WHERE is_active = 1 ORDER BY id",
        )
        return [dict(row) for row in cur.fetchall()]

    def get_site(self, site_id: int) -> dict | None:
        """ID 로 사이트 정보를 반환한다."""
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM crawl_sites WHERE id = ?", (site_id,))
        row = cur.fetchone()
        return dict(row) if row else None

    def get_all_sites(self) -> list[dict]:
        """모든 사이트 목록을 반환한다."""
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM crawl_sites ORDER BY id")
        return [dict(row) for row in cur.fetchall()]

    def update_site_platform(self, site_id: int, platform_id: int):
        """사이트에 플랫폼을 연결한다."""
        cur = self.conn.cursor()
        cur.execute(
            "UPDATE crawl_sites SET platform_id = ?, updated_at = ? WHERE id = ?",
            (platform_id, _now(), site_id),
        )
        self.conn.commit()

    def deactivate_site(self, site_id: int):
        """사이트를 비활성화한다."""
        cur = self.conn.cursor()
        cur.execute(
            "UPDATE crawl_sites SET is_active = 0, updated_at = ? WHERE id = ?",
            (_now(), site_id),
        )
        self.conn.commit()

    def activate_site(self, site_id: int):
        """사이트를 활성화한다."""
        cur = self.conn.cursor()
        cur.execute(
            "UPDATE crawl_sites SET is_active = 1, updated_at = ? WHERE id = ?",
            (_now(), site_id),
        )
        self.conn.commit()

    def get_crawl_config(self, site_id: int) -> dict:
        """사이트의 crawl_config 를 파싱하여 반환한다."""
        site = self.get_site(site_id)
        if not site:
            return {}
        raw = site.get("crawl_config", "{}")
        try:
            return json.loads(raw) if isinstance(raw, str) else (raw or {})
        except (json.JSONDecodeError, TypeError):
            return {}

    def update_crawl_config(self, site_id: int, crawl_config: dict):
        """사이트의 crawl_config 를 업데이트한다."""
        cur = self.conn.cursor()
        cur.execute(
            "UPDATE crawl_sites SET crawl_config = ?, updated_at = ? WHERE id = ?",
            (json.dumps(crawl_config, ensure_ascii=False), _now(), site_id),
        )
        self.conn.commit()

    def update_site_agent_type(self, site_id: int, agent_type: str):
        """사이트의 agent_type 을 업데이트한다."""
        cur = self.conn.cursor()
        cur.execute(
            "UPDATE crawl_sites SET agent_type = ?, updated_at = ? WHERE id = ?",
            (agent_type, _now(), site_id),
        )
        self.conn.commit()

    def get_active_sites_by_agent(self, agent_type: str) -> list[dict]:
        """특정 에이전트 타입의 활성 사이트 목록을 반환한다."""
        cur = self.conn.cursor()
        cur.execute(
            "SELECT * FROM crawl_sites "
            "WHERE is_active = 1 AND agent_type = ? ORDER BY id",
            (agent_type,),
        )
        return [dict(row) for row in cur.fetchall()]

    # ═══════════════════════════════════════════════════════════════
    # platforms CRUD
    # ═══════════════════════════════════════════════════════════════

    def add_platform(self, platform_data: dict) -> int:
        """
        플랫폼을 등록하고 생성된 ID 를 반환한다.

        platform_data:
          {"name": "...", "display_name": "...",
           "detection": {...}, "browser": {...}}
        """
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO platforms (name, display_name, detection, browser) "
            "VALUES (?, ?, ?, ?)",
            (
                platform_data["name"],
                platform_data.get("display_name", platform_data["name"]),
                json.dumps(platform_data.get("detection", {}), ensure_ascii=False),
                json.dumps(platform_data.get("browser", {}), ensure_ascii=False),
            ),
        )
        self.conn.commit()
        return cur.lastrowid

    def get_platform(self, platform_id: int) -> dict | None:
        """ID 로 플랫폼 정보를 반환한다. JSON 필드는 파싱하여 반환."""
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM platforms WHERE id = ?", (platform_id,))
        row = cur.fetchone()
        if not row:
            return None
        d = dict(row)
        d["detection"] = json.loads(d.get("detection") or "{}")
        d["browser"] = json.loads(d.get("browser") or "{}")
        return d

    def get_platform_by_name(self, name: str) -> dict | None:
        """이름으로 플랫폼 정보를 반환한다."""
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM platforms WHERE name = ?", (name,))
        row = cur.fetchone()
        if not row:
            return None
        d = dict(row)
        d["detection"] = json.loads(d.get("detection") or "{}")
        d["browser"] = json.loads(d.get("browser") or "{}")
        return d

    def get_all_platforms(self) -> list[dict]:
        """모든 플랫폼 목록을 반환한다."""
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM platforms WHERE is_active = 1 ORDER BY id")
        result = []
        for row in cur.fetchall():
            d = dict(row)
            d["detection"] = json.loads(d.get("detection") or "{}")
            d["browser"] = json.loads(d.get("browser") or "{}")
            result.append(d)
        return result

    def find_platform_by_detection(
        self, page_url: str, detected_vars: list[str], meta: dict,
    ) -> dict | None:
        """
        감지 규칙과 매칭되는 플랫폼을 찾아 반환한다.

        Args:
            page_url:      현재 페이지 URL
            detected_vars: 발견된 JS 전역 변수명 목록
            meta:          메타 태그 딕셔너리
        """
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
        """추출 템플릿을 등록하고 생성된 ID 를 반환한다."""
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO extraction_templates "
            "(platform_id, target, strategy, config, priority) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                platform_id,
                template_data["target"],
                template_data["strategy"],
                json.dumps(template_data.get("config", {}), ensure_ascii=False),
                template_data.get("priority", 0),
            ),
        )
        self.conn.commit()
        return cur.lastrowid

    def get_templates_for_platform(self, platform_id: int) -> list[dict]:
        """플랫폼 ID 로 추출 템플릿 목록을 반환한다."""
        cur = self.conn.cursor()
        cur.execute(
            "SELECT * FROM extraction_templates "
            "WHERE platform_id = ? ORDER BY target, priority DESC",
            (platform_id,),
        )
        result = []
        for row in cur.fetchall():
            d = dict(row)
            d["config"] = json.loads(d.get("config") or "{}")
            result.append(d)
        return result

    def get_template(self, platform_id: int, target: str) -> dict | None:
        """플랫폼 + 대상으로 최우선 템플릿을 반환한다."""
        cur = self.conn.cursor()
        cur.execute(
            "SELECT * FROM extraction_templates "
            "WHERE platform_id = ? AND target = ? ORDER BY priority DESC LIMIT 1",
            (platform_id, target),
        )
        row = cur.fetchone()
        if not row:
            return None
        d = dict(row)
        d["config"] = json.loads(d.get("config") or "{}")
        return d

    def delete_templates_for_platform(self, platform_id: int):
        """플랫폼의 기존 템플릿을 모두 삭제한다."""
        cur = self.conn.cursor()
        cur.execute(
            "DELETE FROM extraction_templates WHERE platform_id = ?",
            (platform_id,),
        )
        self.conn.commit()

    # ═══════════════════════════════════════════════════════════════
    # crawl_results CRUD
    # ═══════════════════════════════════════════════════════════════

    def create_result(self, site_id: int) -> int:
        """수집 결과 레코드를 생성하고 ID 를 반환한다."""
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO crawl_results (site_id, status) VALUES (?, 'running')",
            (site_id,),
        )
        self.conn.commit()
        return cur.lastrowid

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
        """수집 결과를 업데이트한다."""
        cur = self.conn.cursor()
        cur.execute(
            "UPDATE crawl_results SET "
            "status = ?, store_info = ?, products = ?, "
            "product_count = ?, error_msg = ?, elapsed_sec = ? "
            "WHERE id = ?",
            (
                status,
                json.dumps(store_info, ensure_ascii=False) if store_info else None,
                json.dumps(products, ensure_ascii=False) if products else None,
                product_count,
                error_msg,
                elapsed_sec,
                result_id,
            ),
        )
        self.conn.commit()

    def get_latest_result(self, site_id: int) -> dict | None:
        """사이트의 최신 수집 결과를 반환한다."""
        cur = self.conn.cursor()
        cur.execute(
            "SELECT * FROM crawl_results "
            "WHERE site_id = ? ORDER BY crawl_date DESC LIMIT 1",
            (site_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        d = dict(row)
        d["store_info"] = json.loads(d["store_info"]) if d.get("store_info") else None
        d["products"] = json.loads(d["products"]) if d.get("products") else None
        return d

    # ═══════════════════════════════════════════════════════════════
    # news_keywords CRUD
    # ═══════════════════════════════════════════════════════════════

    def add_keyword(self, site_id: int, keyword: str) -> int | None:
        """
        뉴스 키워드를 등록한다.

        이미 존재하면 활성화하고, 신규이면 INSERT 한다.
        Returns: keyword id (신규) 또는 None (이미 존재)
        """
        cur = self.conn.cursor()
        # 이미 존재하는지 확인
        cur.execute(
            "SELECT id, is_active FROM news_keywords "
            "WHERE site_id = ? AND keyword = ?",
            (site_id, keyword),
        )
        row = cur.fetchone()
        if row:
            if not row["is_active"]:
                cur.execute(
                    "UPDATE news_keywords SET is_active = 1 WHERE id = ?",
                    (row["id"],),
                )
                self.conn.commit()
            return None  # 이미 존재
        cur.execute(
            "INSERT INTO news_keywords (site_id, keyword) VALUES (?, ?)",
            (site_id, keyword),
        )
        self.conn.commit()
        return cur.lastrowid

    def add_keywords(self, site_id: int, keywords: list[str]) -> int:
        """
        뉴스 키워드를 일괄 등록한다.

        Returns: 신규 등록된 키워드 수
        """
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
        """뉴스 키워드를 삭제한다. 삭제 성공 여부를 반환한다."""
        cur = self.conn.cursor()
        cur.execute(
            "DELETE FROM news_keywords WHERE site_id = ? AND keyword = ?",
            (site_id, keyword),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def get_keywords(self, site_id: int) -> list[dict]:
        """사이트의 모든 뉴스 키워드를 반환한다."""
        cur = self.conn.cursor()
        cur.execute(
            "SELECT * FROM news_keywords "
            "WHERE site_id = ? ORDER BY id",
            (site_id,),
        )
        return [dict(row) for row in cur.fetchall()]

    def get_active_keywords(self, site_id: int) -> list[str]:
        """사이트의 활성 뉴스 키워드 문자열 목록을 반환한다."""
        cur = self.conn.cursor()
        cur.execute(
            "SELECT keyword FROM news_keywords "
            "WHERE site_id = ? AND is_active = 1 ORDER BY id",
            (site_id,),
        )
        return [row["keyword"] for row in cur.fetchall()]

    def set_keyword_active(
        self, site_id: int, keyword: str, is_active: bool,
    ) -> bool:
        """키워드의 활성/비활성 상태를 변경한다."""
        cur = self.conn.cursor()
        cur.execute(
            "UPDATE news_keywords SET is_active = ? "
            "WHERE site_id = ? AND keyword = ?",
            (1 if is_active else 0, site_id, keyword),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def migrate_keywords_from_config(self, site_id: int) -> int:
        """
        crawl_config.search_keywords → news_keywords 테이블로 마이그레이션.

        이미 DB 에 키워드가 있으면 스킵한다.
        Returns: 마이그레이션된 키워드 수
        """
        existing = self.get_keywords(site_id)
        if existing:
            return 0  # 이미 DB 키워드 존재 → 스킵

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
        """로그인 계정을 등록하고 생성된 ID를 반환한다."""
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO site_credentials (site_id, login_id, login_pwd, label) "
            "VALUES (?, ?, ?, ?)",
            (site_id, login_id, login_pwd, label),
        )
        self.conn.commit()
        return cur.lastrowid

    def get_credentials(self, site_id: int) -> list[dict]:
        """사이트의 모든 로그인 계정을 반환한다."""
        cur = self.conn.cursor()
        cur.execute(
            "SELECT * FROM site_credentials "
            "WHERE site_id = ? ORDER BY id",
            (site_id,),
        )
        return [dict(row) for row in cur.fetchall()]

    def get_active_credentials(self, site_id: int) -> list[dict]:
        """사이트의 활성 로그인 계정 목록을 반환한다."""
        cur = self.conn.cursor()
        cur.execute(
            "SELECT * FROM site_credentials "
            "WHERE site_id = ? AND is_active = 1 "
            "ORDER BY last_used_at ASC NULLS FIRST, id ASC",
            (site_id,),
        )
        return [dict(row) for row in cur.fetchall()]

    def update_credential(
        self, cred_id: int, login_id: str, login_pwd: str, label: str = "",
    ) -> bool:
        """로그인 계정 정보를 수정한다."""
        cur = self.conn.cursor()
        cur.execute(
            "UPDATE site_credentials "
            "SET login_id = ?, login_pwd = ?, label = ? WHERE id = ?",
            (login_id, login_pwd, label, cred_id),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def delete_credential(self, cred_id: int) -> bool:
        """로그인 계정을 삭제한다."""
        cur = self.conn.cursor()
        cur.execute(
            "DELETE FROM site_credentials WHERE id = ?", (cred_id,),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def toggle_credential(self, cred_id: int) -> dict | None:
        """로그인 계정의 활성/비활성을 토글한다."""
        cur = self.conn.cursor()
        cur.execute("SELECT id, is_active FROM site_credentials WHERE id = ?", (cred_id,))
        row = cur.fetchone()
        if not row:
            return None
        new_active = 0 if row["is_active"] else 1
        cur.execute(
            "UPDATE site_credentials SET is_active = ? WHERE id = ?",
            (new_active, cred_id),
        )
        self.conn.commit()
        return {"id": cred_id, "is_active": new_active}

    def mark_credential_used(self, cred_id: int):
        """로그인 계정 사용 시각을 갱신한다."""
        cur = self.conn.cursor()
        cur.execute(
            "UPDATE site_credentials SET last_used_at = ? WHERE id = ?",
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
        """OCR/Document Parser 사용 이력을 기록한다.

        Args:
            site_id: 사이트 ID
            engine: 사용한 엔진 ("document-parse" | "tesseract")
            status: 결과 상태 ("success" | "fail" | "rate_limit")
            post_id: 게시글 ID
            image_url: 이미지 URL
            text_length: 추출된 텍스트 길이
            price_count: 추출된 가격 수
            elapsed_ms: 처리 시간 (ms)
            error_msg: 에러 메시지

        Returns:
            생성된 로그 ID
        """
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO ocr_usage_log "
            "(site_id, post_id, image_url, engine, status, "
            " text_length, price_count, elapsed_ms, error_msg) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
        self.conn.commit()
        return cur.lastrowid

    def get_ocr_usage_summary(self, site_id: int = 0) -> list[dict]:
        """OCR 사용 이력 요약을 반환한다.

        Args:
            site_id: 0이면 전체, 양수이면 해당 사이트만

        Returns:
            엔진별 집계 [{engine, total, success, fail, rate_limit, ...}]
        """
        cur = self.conn.cursor()
        where = "WHERE site_id = ?" if site_id else ""
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
        """OCR 사용 이력 상세를 반환한다."""
        cur = self.conn.cursor()
        where = "WHERE site_id = ?" if site_id else ""
        params = (site_id, limit) if site_id else (limit,)
        cur.execute(f"""
            SELECT * FROM ocr_usage_log
            {where}
            ORDER BY id DESC
            LIMIT ?
        """, params)
        return [dict(row) for row in cur.fetchall()]

    # ═══════════════════════════════════════════════════════════════
    # LLM 분석 결과 일괄 저장
    # ═══════════════════════════════════════════════════════════════

    def save_llm_analysis(self, llm_result: dict, site_id: int) -> int:
        """
        LLM 분석 결과(platform + templates)를 DB 에 저장하고
        사이트에 플랫폼을 연결한다.

        Returns:
            생성된 platform_id
        """
        platform_data = llm_result["platform"]
        templates = llm_result["templates"]

        # 동일 이름 플랫폼이 있으면 재사용 (설정 갱신)
        existing = self.get_platform_by_name(platform_data["name"])
        if existing:
            platform_id = existing["id"]
            # 기존 템플릿 교체
            self.delete_templates_for_platform(platform_id)
            # browser / detection 설정도 최신으로 갱신
            cur = self.conn.cursor()
            cur.execute(
                "UPDATE platforms SET browser = ?, detection = ? "
                "WHERE id = ?",
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

        # 템플릿 저장
        for tmpl in templates:
            self.add_template(platform_id, tmpl)

        # 사이트에 플랫폼 연결
        self.update_site_platform(site_id, platform_id)

        print(f"[db] 플랫폼 '{platform_data['name']}' (ID={platform_id}) 저장 완료, "
              f"템플릿 {len(templates)}개")
        return platform_id


# ─── 유틸 ────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
