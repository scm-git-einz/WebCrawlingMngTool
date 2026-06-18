-- ============================================================
-- 크롤링 관리 플랫폼 — PostgreSQL 테이블 생성 스크립트
-- 원본: SQLite (core/db.py) → PostgreSQL 변환
-- ============================================================

-- 1. platforms: 플랫폼 정의 (감지 규칙 + 브라우저 설정)
CREATE TABLE IF NOT EXISTS platforms (
    id           SERIAL       PRIMARY KEY,
    name         TEXT         NOT NULL UNIQUE,
    display_name TEXT         NOT NULL,
    detection    JSONB        NOT NULL DEFAULT '{}',
    browser      JSONB        NOT NULL DEFAULT '{}',
    is_active    SMALLINT     NOT NULL DEFAULT 1,
    created_at   TIMESTAMP    NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  platforms                IS '플랫폼 정의 — 사이트 감지 규칙 및 브라우저 설정';
COMMENT ON COLUMN platforms.id             IS '플랫폼 고유 ID';
COMMENT ON COLUMN platforms.name           IS '플랫폼 식별 코드 (예: naver_smartstore)';
COMMENT ON COLUMN platforms.display_name   IS '화면 표시용 플랫폼명';
COMMENT ON COLUMN platforms.detection      IS '사이트 감지 규칙 (JSON: rules, match_mode)';
COMMENT ON COLUMN platforms.browser        IS '브라우저 설정 (JSON: user_agent, viewport, headers, allowed_domains)';
COMMENT ON COLUMN platforms.is_active      IS '활성 여부 (1=활성, 0=비활성)';
COMMENT ON COLUMN platforms.created_at     IS '등록 일시';

-- 2. extraction_templates: 플랫폼별 추출 템플릿
CREATE TABLE IF NOT EXISTS extraction_templates (
    id           SERIAL       PRIMARY KEY,
    platform_id  INTEGER      NOT NULL REFERENCES platforms(id),
    target       TEXT         NOT NULL,
    strategy     TEXT         NOT NULL,
    config       JSONB        NOT NULL DEFAULT '{}',
    priority     INTEGER      NOT NULL DEFAULT 0
);

COMMENT ON TABLE  extraction_templates              IS '플랫폼별 데이터 추출 템플릿';
COMMENT ON COLUMN extraction_templates.id           IS '템플릿 고유 ID';
COMMENT ON COLUMN extraction_templates.platform_id  IS '플랫폼 FK (platforms.id)';
COMMENT ON COLUMN extraction_templates.target       IS '추출 대상 (예: product_list, product_detail)';
COMMENT ON COLUMN extraction_templates.strategy     IS '추출 전략 (예: dom, api, state_var)';
COMMENT ON COLUMN extraction_templates.config       IS '추출 설정 (JSON: 셀렉터, 매핑 규칙 등)';
COMMENT ON COLUMN extraction_templates.priority     IS '우선순위 (높을수록 먼저 시도)';

-- 3. crawl_sites: 수집 대상 사이트
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
);

COMMENT ON TABLE  crawl_sites                IS '수집 대상 사이트 목록';
COMMENT ON COLUMN crawl_sites.id             IS '사이트 고유 ID';
COMMENT ON COLUMN crawl_sites.site_name      IS '사이트명 (화면 표시용)';
COMMENT ON COLUMN crawl_sites.site_url       IS '수집 대상 URL';
COMMENT ON COLUMN crawl_sites.is_active      IS '활성 여부 (1=활성, 0=비활성)';
COMMENT ON COLUMN crawl_sites.platform_id    IS '플랫폼 FK (platforms.id)';
COMMENT ON COLUMN crawl_sites.agent_type     IS '에이전트 유형 (product, news, cafe, promotion, banner, directory, order, coupon)';
COMMENT ON COLUMN crawl_sites.crawl_config   IS '수집 설정 (JSON: 에이전트별 상세 설정)';
COMMENT ON COLUMN crawl_sites.category       IS '카테고리 (경쟁사상품, 뉴스, 카페 등)';
COMMENT ON COLUMN crawl_sites.crawl_schedule IS '수집 주기 (daily, weekly, monthly 등)';
COMMENT ON COLUMN crawl_sites.created_at     IS '등록 일시';
COMMENT ON COLUMN crawl_sites.updated_at     IS '최종 수정 일시';

-- 4. news_keywords: 뉴스 검색 키워드 (사이트별)
CREATE TABLE IF NOT EXISTS news_keywords (
    id           SERIAL       PRIMARY KEY,
    site_id      INTEGER      NOT NULL REFERENCES crawl_sites(id),
    keyword      TEXT         NOT NULL,
    is_active    SMALLINT     NOT NULL DEFAULT 1,
    created_at   TIMESTAMP    NOT NULL DEFAULT NOW(),
    UNIQUE(site_id, keyword)
);

COMMENT ON TABLE  news_keywords              IS '뉴스 에이전트 검색 키워드 (사이트별)';
COMMENT ON COLUMN news_keywords.id           IS '키워드 고유 ID';
COMMENT ON COLUMN news_keywords.site_id      IS '사이트 FK (crawl_sites.id)';
COMMENT ON COLUMN news_keywords.keyword      IS '검색 키워드';
COMMENT ON COLUMN news_keywords.is_active    IS '활성 여부 (1=활성, 0=비활성)';
COMMENT ON COLUMN news_keywords.created_at   IS '등록 일시';

-- 5. crawl_results: 수집 결과
CREATE TABLE IF NOT EXISTS crawl_results (
    id            SERIAL       PRIMARY KEY,
    site_id       INTEGER      NOT NULL REFERENCES crawl_sites(id),
    crawl_date    TIMESTAMP    NOT NULL DEFAULT NOW(),
    status        TEXT         NOT NULL DEFAULT 'pending',
    store_info    JSONB,
    products      JSONB,
    product_count INTEGER      NOT NULL DEFAULT 0,
    error_msg     TEXT,
    elapsed_sec   DOUBLE PRECISION
);

COMMENT ON TABLE  crawl_results                IS '크롤링 수집 결과';
COMMENT ON COLUMN crawl_results.id             IS '결과 고유 ID';
COMMENT ON COLUMN crawl_results.site_id        IS '사이트 FK (crawl_sites.id)';
COMMENT ON COLUMN crawl_results.crawl_date     IS '수집 시작 일시';
COMMENT ON COLUMN crawl_results.status         IS '수집 상태 (pending, running, success, failed, blocked, stopped)';
COMMENT ON COLUMN crawl_results.store_info     IS '사이트/매장 메타정보 (JSON)';
COMMENT ON COLUMN crawl_results.products       IS '수집된 상품/기사/이벤트 목록 (JSON 배열)';
COMMENT ON COLUMN crawl_results.product_count  IS '수집 건수';
COMMENT ON COLUMN crawl_results.error_msg      IS '오류 메시지 (실패 시)';
COMMENT ON COLUMN crawl_results.elapsed_sec    IS '소요 시간 (초)';

-- 6. ocr_usage_log: OCR/Document Parser API 사용 이력
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
);

COMMENT ON TABLE  ocr_usage_log               IS 'OCR/Document Parser API 사용 이력';
COMMENT ON COLUMN ocr_usage_log.id            IS '로그 고유 ID';
COMMENT ON COLUMN ocr_usage_log.site_id       IS '사이트 FK (crawl_sites.id)';
COMMENT ON COLUMN ocr_usage_log.post_id       IS '게시글 ID (카페 인기글 등)';
COMMENT ON COLUMN ocr_usage_log.image_url     IS '처리한 이미지 URL';
COMMENT ON COLUMN ocr_usage_log.engine        IS 'OCR 엔진 (document_parse, tesseract)';
COMMENT ON COLUMN ocr_usage_log.status        IS '처리 결과 (success, error)';
COMMENT ON COLUMN ocr_usage_log.text_length   IS '추출된 텍스트 길이 (문자 수)';
COMMENT ON COLUMN ocr_usage_log.price_count   IS '추출된 가격 정보 개수';
COMMENT ON COLUMN ocr_usage_log.elapsed_ms    IS '처리 소요 시간 (밀리초)';
COMMENT ON COLUMN ocr_usage_log.error_msg     IS '오류 메시지 (실패 시)';
COMMENT ON COLUMN ocr_usage_log.created_at    IS '처리 일시';

-- 7. llm_usage: LLM API 토큰 사용량 추적
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
);

COMMENT ON TABLE  llm_usage                       IS 'LLM API 토큰 사용량 추적';
COMMENT ON COLUMN llm_usage.id                    IS '로그 고유 ID';
COMMENT ON COLUMN llm_usage.site_id               IS '사이트 FK (crawl_sites.id, NULL 가능)';
COMMENT ON COLUMN llm_usage.agent_type            IS '호출한 에이전트 유형';
COMMENT ON COLUMN llm_usage.task_type             IS '작업 유형 (예: url_analysis, content_extract)';
COMMENT ON COLUMN llm_usage.model                 IS 'LLM 모델명 (예: gpt-4o-mini)';
COMMENT ON COLUMN llm_usage.prompt_tokens         IS '입력 토큰 수';
COMMENT ON COLUMN llm_usage.completion_tokens     IS '출력 토큰 수';
COMMENT ON COLUMN llm_usage.total_tokens          IS '총 토큰 수';
COMMENT ON COLUMN llm_usage.cost_usd              IS '비용 (USD)';
COMMENT ON COLUMN llm_usage.input_preview         IS '입력 프롬프트 미리보기';
COMMENT ON COLUMN llm_usage.output_preview        IS '출력 결과 미리보기';
COMMENT ON COLUMN llm_usage.elapsed_ms            IS '처리 소요 시간 (밀리초)';
COMMENT ON COLUMN llm_usage.created_at            IS '호출 일시';

-- 8. agent_field_defs: 에이전트별 수집 필드 정의
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
);

COMMENT ON TABLE  agent_field_defs              IS '에이전트별 수집 필드 정의 (매트릭스 대시보드용)';
COMMENT ON COLUMN agent_field_defs.id           IS '필드 정의 고유 ID';
COMMENT ON COLUMN agent_field_defs.agent_type   IS '에이전트 유형 (product, news, cafe 등)';
COMMENT ON COLUMN agent_field_defs.field_key    IS '필드 식별 키 (예: name, price, brand)';
COMMENT ON COLUMN agent_field_defs.label        IS '화면 표시용 한글 라벨';
COMMENT ON COLUMN agent_field_defs.config_key   IS '수집 여부를 결정하는 crawl_config 키 (빈 문자열=항상 수집)';
COMMENT ON COLUMN agent_field_defs.sort_order   IS '화면 정렬 순서';
COMMENT ON COLUMN agent_field_defs.is_active    IS '활성 여부 (1=활성, 0=비활성)';
COMMENT ON COLUMN agent_field_defs.created_at   IS '등록 일시';

-- 9. site_credentials: 사이트별 로그인 계정
CREATE TABLE IF NOT EXISTS site_credentials (
    id           SERIAL       PRIMARY KEY,
    site_id      INTEGER      NOT NULL REFERENCES crawl_sites(id),
    login_id     TEXT         NOT NULL,
    login_pwd    TEXT         NOT NULL,
    label        TEXT         NOT NULL DEFAULT '',
    is_active    SMALLINT     NOT NULL DEFAULT 1,
    last_used_at TIMESTAMP,
    created_at   TIMESTAMP    NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  site_credentials              IS '사이트별 로그인 계정 정보';
COMMENT ON COLUMN site_credentials.id           IS '계정 고유 ID';
COMMENT ON COLUMN site_credentials.site_id      IS '사이트 FK (crawl_sites.id)';
COMMENT ON COLUMN site_credentials.login_id     IS '로그인 아이디';
COMMENT ON COLUMN site_credentials.login_pwd    IS '로그인 비밀번호';
COMMENT ON COLUMN site_credentials.label        IS '계정 라벨 (화면 표시용, 예: 본계정, 테스트)';
COMMENT ON COLUMN site_credentials.is_active    IS '활성 여부 (1=활성, 0=비활성)';
COMMENT ON COLUMN site_credentials.last_used_at IS '마지막 사용 일시';
COMMENT ON COLUMN site_credentials.created_at   IS '등록 일시';

-- 10. crawl_failure_log: 크롤링 실패 이벤트 로그
CREATE TABLE IF NOT EXISTS crawl_failure_log (
    id              SERIAL       PRIMARY KEY,
    site_id         INTEGER      NOT NULL REFERENCES crawl_sites(id),
    crawl_result_id INTEGER      REFERENCES crawl_results(id),
    agent_type      TEXT         NOT NULL,
    crawl_date      TIMESTAMP    NOT NULL DEFAULT NOW(),
    failure_summary JSONB        NOT NULL DEFAULT '{}',
    failure_events  JSONB        NOT NULL DEFAULT '[]',
    log_file        TEXT,
    created_at      TIMESTAMP    NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  crawl_failure_log                 IS '크롤링 실패 이벤트 로그 (크롤 1회 = 1행)';
COMMENT ON COLUMN crawl_failure_log.id              IS '실패 로그 고유 ID';
COMMENT ON COLUMN crawl_failure_log.site_id         IS '사이트 FK (crawl_sites.id)';
COMMENT ON COLUMN crawl_failure_log.crawl_result_id IS '수집 결과 FK (crawl_results.id)';
COMMENT ON COLUMN crawl_failure_log.agent_type      IS '에이전트 유형 (product, order, news 등)';
COMMENT ON COLUMN crawl_failure_log.crawl_date      IS '크롤링 실행 일시';
COMMENT ON COLUMN crawl_failure_log.failure_summary IS '실패 유형별 건수 요약 (JSON: total, http_block, soft_block, login_fail, click_fail, nav_fail, data_fail, exception)';
COMMENT ON COLUMN crawl_failure_log.failure_events  IS '실패 이벤트 상세 배열 (JSON: time, type, subtype, message, domain, url, target, context)';
COMMENT ON COLUMN crawl_failure_log.log_file        IS '연결된 크롤링 로그 파일명';
COMMENT ON COLUMN crawl_failure_log.created_at      IS '등록 일시';

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
CREATE INDEX IF NOT EXISTS idx_cfl_site_id                ON crawl_failure_log(site_id);
CREATE INDEX IF NOT EXISTS idx_cfl_crawl_date             ON crawl_failure_log(crawl_date DESC);
CREATE INDEX IF NOT EXISTS idx_cfl_agent_type             ON crawl_failure_log(agent_type);
