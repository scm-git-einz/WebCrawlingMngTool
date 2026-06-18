-- ============================================================
-- 크롤링 관리 플랫폼 — SQLite 테이블 생성 스크립트
-- 원본: core/db.py _create_tables()
-- ============================================================

-- 1. platforms: 플랫폼 정의 (감지 규칙 + 브라우저 설정)
CREATE TABLE IF NOT EXISTS platforms (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT    NOT NULL UNIQUE,
    display_name TEXT    NOT NULL,
    detection    TEXT    NOT NULL DEFAULT '{}',
    browser      TEXT    NOT NULL DEFAULT '{}',
    is_active    INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

-- 2. extraction_templates: 플랫폼별 추출 템플릿
CREATE TABLE IF NOT EXISTS extraction_templates (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    platform_id  INTEGER NOT NULL,
    target       TEXT    NOT NULL,
    strategy     TEXT    NOT NULL,
    config       TEXT    NOT NULL DEFAULT '{}',
    priority     INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (platform_id) REFERENCES platforms(id)
);

-- 3. crawl_sites: 수집 대상 사이트
CREATE TABLE IF NOT EXISTS crawl_sites (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    site_name      TEXT    NOT NULL,
    site_url       TEXT    NOT NULL,
    is_active      INTEGER NOT NULL DEFAULT 1,
    platform_id    INTEGER,
    agent_type     TEXT    NOT NULL DEFAULT 'product',
    crawl_config   TEXT    NOT NULL DEFAULT '{}',
    category       TEXT    NOT NULL DEFAULT '',
    crawl_schedule TEXT    NOT NULL DEFAULT '',
    created_at     TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at     TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (platform_id) REFERENCES platforms(id)
);

-- 4. news_keywords: 뉴스 검색 키워드 (사이트별)
CREATE TABLE IF NOT EXISTS news_keywords (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id      INTEGER NOT NULL,
    keyword      TEXT    NOT NULL,
    is_active    INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (site_id) REFERENCES crawl_sites(id),
    UNIQUE(site_id, keyword)
);

-- 5. crawl_results: 수집 결과
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
);

-- 6. ocr_usage_log: OCR/Document Parser API 사용 이력
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
);

-- 7. llm_usage: LLM API 토큰 사용량 추적
CREATE TABLE IF NOT EXISTS llm_usage (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id           INTEGER,
    agent_type        TEXT    NOT NULL,
    task_type         TEXT    NOT NULL,
    model             TEXT    NOT NULL DEFAULT '',
    prompt_tokens     INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens      INTEGER NOT NULL DEFAULT 0,
    cost_usd          REAL    NOT NULL DEFAULT 0.0,
    input_preview     TEXT    NOT NULL DEFAULT '',
    output_preview    TEXT    NOT NULL DEFAULT '',
    elapsed_ms        INTEGER NOT NULL DEFAULT 0,
    created_at        TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (site_id) REFERENCES crawl_sites(id)
);

-- 8. agent_field_defs: 에이전트별 수집 필드 정의
CREATE TABLE IF NOT EXISTS agent_field_defs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_type   TEXT    NOT NULL,
    field_key    TEXT    NOT NULL,
    label        TEXT    NOT NULL,
    config_key   TEXT    NOT NULL DEFAULT '',
    sort_order   INTEGER NOT NULL DEFAULT 0,
    is_active    INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    UNIQUE(agent_type, field_key)
);

-- 9. site_credentials: 사이트별 로그인 계정
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
);

-- ============================================================
-- 인덱스
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_crawl_sites_agent_type     ON crawl_sites(agent_type);
CREATE INDEX IF NOT EXISTS idx_crawl_sites_category       ON crawl_sites(category);
CREATE INDEX IF NOT EXISTS idx_crawl_results_site_id      ON crawl_results(site_id);
CREATE INDEX IF NOT EXISTS idx_crawl_results_status       ON crawl_results(status);
CREATE INDEX IF NOT EXISTS idx_ocr_usage_log_site_id      ON ocr_usage_log(site_id);
CREATE INDEX IF NOT EXISTS idx_llm_usage_site_id          ON llm_usage(site_id);
CREATE INDEX IF NOT EXISTS idx_agent_field_defs_agent     ON agent_field_defs(agent_type);
CREATE INDEX IF NOT EXISTS idx_site_credentials_site_id   ON site_credentials(site_id);
CREATE INDEX IF NOT EXISTS idx_news_keywords_site_id      ON news_keywords(site_id);
