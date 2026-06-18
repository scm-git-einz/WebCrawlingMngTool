-- ============================================================
-- 크롤링 관리 플랫폼 — 테이블 생성 DDL
-- Database: PostgreSQL (aops)
-- ============================================================

-- ─── 플랫폼 정의 ───
CREATE TABLE IF NOT EXISTS crawl_platforms (
    id           SERIAL       PRIMARY KEY,
    name         TEXT         NOT NULL UNIQUE,
    display_name TEXT         NOT NULL,
    detection    JSONB        NOT NULL DEFAULT '{}',
    browser      JSONB        NOT NULL DEFAULT '{}',
    is_active    SMALLINT     NOT NULL DEFAULT 1,
    created_at   TIMESTAMP    NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  crawl_platforms                IS '플랫폼 정의 (감지 규칙 + 브라우저 설정)';
COMMENT ON COLUMN crawl_platforms.name           IS '플랫폼 고유 식별자 (예: cafe24, shopify)';
COMMENT ON COLUMN crawl_platforms.display_name   IS '화면 표시명';
COMMENT ON COLUMN crawl_platforms.detection      IS '플랫폼 감지 규칙 (URL 패턴, HTML 시그니처 등)';
COMMENT ON COLUMN crawl_platforms.browser        IS '브라우저 설정 (viewport, user-agent 등)';
COMMENT ON COLUMN crawl_platforms.is_active      IS '활성 여부 (1=활성, 0=비활성)';


-- ─── 플랫폼별 추출 템플릿 ───
CREATE TABLE IF NOT EXISTS crawl_extraction_templates (
    id           SERIAL       PRIMARY KEY,
    platform_id  INTEGER      NOT NULL REFERENCES crawl_platforms(id),
    target       TEXT         NOT NULL,
    strategy     TEXT         NOT NULL,
    config       JSONB        NOT NULL DEFAULT '{}',
    priority     INTEGER      NOT NULL DEFAULT 0
);

COMMENT ON TABLE  crawl_extraction_templates              IS '플랫폼별 데이터 추출 템플릿';
COMMENT ON COLUMN crawl_extraction_templates.platform_id  IS '소속 플랫폼 FK';
COMMENT ON COLUMN crawl_extraction_templates.target       IS '추출 대상 (product, price 등)';
COMMENT ON COLUMN crawl_extraction_templates.strategy     IS '추출 전략 (dom, api, state_var)';
COMMENT ON COLUMN crawl_extraction_templates.config       IS '전략별 설정 (셀렉터, 엔드포인트 등)';
COMMENT ON COLUMN crawl_extraction_templates.priority     IS '우선순위 (높을수록 먼저 시도)';


-- ─── 수집 대상 사이트 ───
CREATE TABLE IF NOT EXISTS crawl_sites (
    id             SERIAL       PRIMARY KEY,
    site_name      TEXT         NOT NULL,
    site_url       TEXT         NOT NULL,
    is_active      SMALLINT     NOT NULL DEFAULT 1,
    platform_id    INTEGER      REFERENCES crawl_platforms(id),
    agent_type     TEXT         NOT NULL DEFAULT 'product',
    crawl_config   JSONB        NOT NULL DEFAULT '{}',
    category       TEXT         NOT NULL DEFAULT '',
    crawl_schedule TEXT         NOT NULL DEFAULT '',
    created_at     TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMP    NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  crawl_sites                IS '수집 대상 사이트 등록 정보';
COMMENT ON COLUMN crawl_sites.site_name      IS '사이트 표시명';
COMMENT ON COLUMN crawl_sites.site_url       IS '수집 대상 URL';
COMMENT ON COLUMN crawl_sites.is_active      IS '활성 여부 (1=활성, 0=비활성)';
COMMENT ON COLUMN crawl_sites.platform_id    IS '플랫폼 FK (자동 감지 또는 수동 지정)';
COMMENT ON COLUMN crawl_sites.agent_type     IS '에이전트 유형 (system_codes.agent_type 참조)';
COMMENT ON COLUMN crawl_sites.crawl_config   IS '에이전트별 수집 설정 (JSONB)';
COMMENT ON COLUMN crawl_sites.category       IS '사이트 카테고리 (system_codes.category 참조)';
COMMENT ON COLUMN crawl_sites.crawl_schedule IS '수집 주기 (adhoc, hourly:N, daily:H, weekly:W:H, monthly:D:H)';


-- ─── 뉴스 검색 키워드 ───
CREATE TABLE IF NOT EXISTS crawl_news_keywords (
    id           SERIAL       PRIMARY KEY,
    site_id      INTEGER      NOT NULL REFERENCES crawl_sites(id),
    keyword      TEXT         NOT NULL,
    is_active    SMALLINT     NOT NULL DEFAULT 1,
    created_at   TIMESTAMP    NOT NULL DEFAULT NOW(),
    UNIQUE(site_id, keyword)
);

COMMENT ON TABLE  crawl_news_keywords            IS '뉴스 에이전트 검색 키워드 (사이트별)';
COMMENT ON COLUMN crawl_news_keywords.site_id    IS '소속 사이트 FK';
COMMENT ON COLUMN crawl_news_keywords.keyword    IS '검색 키워드';
COMMENT ON COLUMN crawl_news_keywords.is_active  IS '활성 여부 (1=활성, 0=비활성)';


-- ─── 수집 결과 (모니터링) ───
CREATE TABLE IF NOT EXISTS crawl_results (
    id            SERIAL           PRIMARY KEY,
    site_id       INTEGER          NOT NULL REFERENCES crawl_sites(id),
    crawl_date    TIMESTAMP        NOT NULL DEFAULT NOW(),
    status        TEXT             NOT NULL DEFAULT 'pending',
    product_count INTEGER          NOT NULL DEFAULT 0,
    error_msg     TEXT,
    elapsed_sec   DOUBLE PRECISION
);

COMMENT ON TABLE  crawl_results                IS '수집 실행 결과 — 모니터링 전용 (상태/건수/소요시간)';
COMMENT ON COLUMN crawl_results.site_id        IS '대상 사이트 FK';
COMMENT ON COLUMN crawl_results.crawl_date     IS '수집 실행 시각';
COMMENT ON COLUMN crawl_results.status         IS '실행 상태 (system_codes.crawl_status 참조)';
COMMENT ON COLUMN crawl_results.product_count  IS '수집 건수';
COMMENT ON COLUMN crawl_results.error_msg      IS '에러 메시지 (실패 시)';
COMMENT ON COLUMN crawl_results.elapsed_sec    IS '소요 시간 (초)';


-- ─── 수집 원시 데이터 (메달리온 Bronze) ───
CREATE TABLE IF NOT EXISTS crawl_data (
    id              SERIAL       PRIMARY KEY,
    crawl_result_id INTEGER      NOT NULL REFERENCES crawl_results(id),
    site_id         INTEGER      NOT NULL REFERENCES crawl_sites(id),
    agent_type      TEXT         NOT NULL,
    items           JSONB        NOT NULL DEFAULT '[]',
    store_info      JSONB        DEFAULT '{}',
    item_count      INTEGER      NOT NULL DEFAULT 0,
    created_at      TIMESTAMP    NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_crawl_data_result ON crawl_data(crawl_result_id);
CREATE INDEX IF NOT EXISTS idx_crawl_data_site   ON crawl_data(site_id);

COMMENT ON TABLE  crawl_data                  IS '수집 원시 데이터 — 메달리온 아키텍처 Bronze 레이어';
COMMENT ON COLUMN crawl_data.crawl_result_id  IS '수집 결과 FK';
COMMENT ON COLUMN crawl_data.site_id          IS '대상 사이트 FK';
COMMENT ON COLUMN crawl_data.agent_type       IS '에이전트 유형';
COMMENT ON COLUMN crawl_data.items            IS '수집 데이터 (상품/뉴스/배너 등 JSONB 배열)';
COMMENT ON COLUMN crawl_data.store_info       IS '매장 부가정보 (JSONB)';
COMMENT ON COLUMN crawl_data.item_count       IS '수집 건수';


-- ─── OCR 사용 이력 ───
CREATE TABLE IF NOT EXISTS crawl_ocr_usage_log (
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
);

COMMENT ON TABLE  crawl_ocr_usage_log             IS 'OCR/Document Parser API 사용 이력';
COMMENT ON COLUMN crawl_ocr_usage_log.site_id     IS '대상 사이트 FK';
COMMENT ON COLUMN crawl_ocr_usage_log.engine      IS 'OCR 엔진 (document-parse, tesseract)';
COMMENT ON COLUMN crawl_ocr_usage_log.status      IS '처리 결과 (success, fail, rate_limit)';
COMMENT ON COLUMN crawl_ocr_usage_log.text_length IS '추출 텍스트 길이 (자)';
COMMENT ON COLUMN crawl_ocr_usage_log.price_count IS '추출 가격 건수';
COMMENT ON COLUMN crawl_ocr_usage_log.elapsed_ms  IS '처리 소요시간 (ms)';


-- ─── LLM 토큰 사용량 ───
CREATE TABLE IF NOT EXISTS crawl_llm_usage (
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
);

COMMENT ON TABLE  crawl_llm_usage                   IS 'LLM API 토큰 사용량 추적';
COMMENT ON COLUMN crawl_llm_usage.agent_type        IS '호출 에이전트 유형';
COMMENT ON COLUMN crawl_llm_usage.task_type         IS '작업 유형 (analyze, extract 등)';
COMMENT ON COLUMN crawl_llm_usage.model             IS 'LLM 모델명';
COMMENT ON COLUMN crawl_llm_usage.prompt_tokens     IS '입력 토큰 수';
COMMENT ON COLUMN crawl_llm_usage.completion_tokens IS '출력 토큰 수';
COMMENT ON COLUMN crawl_llm_usage.cost_usd          IS '비용 (USD)';


-- ─── 에이전트 수집 필드 정의 ───
CREATE TABLE IF NOT EXISTS crawl_agent_field_defs (
    id           SERIAL       PRIMARY KEY,
    agent_type   TEXT         NOT NULL,
    field_key    TEXT         NOT NULL,
    label        TEXT         NOT NULL,
    config_key   TEXT         NOT NULL DEFAULT '',
    sort_order   INTEGER      NOT NULL DEFAULT 0,
    is_active    SMALLINT     NOT NULL DEFAULT 1,
    created_at   TIMESTAMP    NOT NULL DEFAULT NOW(),
    UNIQUE(agent_type, field_key)
);

COMMENT ON TABLE  crawl_agent_field_defs              IS '에이전트별 수집 가능 필드 정의 (DB 관리)';
COMMENT ON COLUMN crawl_agent_field_defs.agent_type   IS '에이전트 유형';
COMMENT ON COLUMN crawl_agent_field_defs.field_key    IS '필드 키 (collect_fields 배열 값)';
COMMENT ON COLUMN crawl_agent_field_defs.label        IS '화면 표시 라벨';
COMMENT ON COLUMN crawl_agent_field_defs.config_key   IS '설정 키 그룹 (collect_fields, options 등)';
COMMENT ON COLUMN crawl_agent_field_defs.sort_order   IS '표시 정렬 순서';
COMMENT ON COLUMN crawl_agent_field_defs.is_active    IS '활성 여부';


-- ─── 수집 실패 로그 ───
CREATE TABLE IF NOT EXISTS crawl_failure_log (
    id              SERIAL    PRIMARY KEY,
    site_id         INTEGER   NOT NULL REFERENCES crawl_sites(id),
    crawl_result_id INTEGER   REFERENCES crawl_results(id),
    agent_type      TEXT      NOT NULL,
    crawl_date      TIMESTAMP NOT NULL DEFAULT NOW(),
    failure_summary JSONB     NOT NULL DEFAULT '{}',
    failure_events  JSONB     NOT NULL DEFAULT '[]',
    log_file        TEXT,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cfl_site_id    ON crawl_failure_log(site_id);
CREATE INDEX IF NOT EXISTS idx_cfl_crawl_date ON crawl_failure_log(crawl_date DESC);
CREATE INDEX IF NOT EXISTS idx_cfl_agent_type ON crawl_failure_log(agent_type);

COMMENT ON TABLE  crawl_failure_log                  IS '수집 실패 상세 로그 (이벤트 단위 기록)';
COMMENT ON COLUMN crawl_failure_log.failure_summary  IS '실패 요약 (카테고리별 건수 등)';
COMMENT ON COLUMN crawl_failure_log.failure_events   IS '실패 이벤트 목록 (타임스탬프, 유형, 메시지)';
COMMENT ON COLUMN crawl_failure_log.log_file         IS '로그 파일 경로';


-- ─── 사이트별 로그인 계정 ───
CREATE TABLE IF NOT EXISTS crawl_site_credentials (
    id           SERIAL       PRIMARY KEY,
    site_id      INTEGER      NOT NULL REFERENCES crawl_sites(id),
    login_id     TEXT         NOT NULL,
    login_pwd    TEXT         NOT NULL,
    label        TEXT         NOT NULL DEFAULT '',
    is_active    SMALLINT     NOT NULL DEFAULT 1,
    last_used_at TIMESTAMP,
    created_at   TIMESTAMP    NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  crawl_site_credentials              IS '사이트별 로그인 계정 (복수 계정, 로테이션 지원)';
COMMENT ON COLUMN crawl_site_credentials.login_id     IS '로그인 ID';
COMMENT ON COLUMN crawl_site_credentials.login_pwd    IS '로그인 비밀번호';
COMMENT ON COLUMN crawl_site_credentials.label        IS '계정 라벨 (구분용)';
COMMENT ON COLUMN crawl_site_credentials.is_active    IS '활성 여부';
COMMENT ON COLUMN crawl_site_credentials.last_used_at IS '마지막 사용 시각';


-- ─── 시스템 코드 ───
CREATE TABLE IF NOT EXISTS crawl_system_codes (
    id          SERIAL       PRIMARY KEY,
    group_code  TEXT         NOT NULL,
    code        TEXT         NOT NULL,
    label       TEXT         NOT NULL,
    extra       JSONB        NOT NULL DEFAULT '{}',
    sort_order  INTEGER      NOT NULL DEFAULT 0,
    is_active   SMALLINT     NOT NULL DEFAULT 1,
    created_at  TIMESTAMP    NOT NULL DEFAULT NOW(),
    UNIQUE(group_code, code)
);

COMMENT ON TABLE  crawl_system_codes              IS '시스템 코드 관리 (카테고리, 에이전트 유형, 상태 등)';
COMMENT ON COLUMN crawl_system_codes.group_code   IS '코드 그룹 (agent_type, category, crawl_status)';
COMMENT ON COLUMN crawl_system_codes.code         IS '코드 값';
COMMENT ON COLUMN crawl_system_codes.label        IS '화면 표시 라벨';
COMMENT ON COLUMN crawl_system_codes.extra        IS '부가 정보 (icon, color, badge_class, agent_type 매핑 등)';
COMMENT ON COLUMN crawl_system_codes.sort_order   IS '표시 정렬 순서';
COMMENT ON COLUMN crawl_system_codes.is_active    IS '활성 여부 (1=활성, 0=비활성)';
