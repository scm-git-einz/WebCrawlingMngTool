-- ============================================================
-- 크롤링 관리 플랫폼 — 초기 데이터 INSERT
-- Database: PostgreSQL (aops)
-- ============================================================

-- ─── 시스템 코드 (crawl_system_codes) ───

-- agent_type: 에이전트 유형
INSERT INTO crawl_system_codes (group_code, code, label, extra, sort_order) VALUES
('agent_type', 'product',   '상품 수집',     '{"badge_class": "primary"}',  10),
('agent_type', 'news',      '뉴스 수집',     '{"badge_class": "info"}',     20),
('agent_type', 'cafe',      '카페 수집',     '{"badge_class": "success"}',  30),
('agent_type', 'promotion', '프로모션 수집', '{"badge_class": "warning"}',  40),
('agent_type', 'banner',    '배너 수집',     '{"badge_class": "dp"}',       50),
('agent_type', 'directory', '목록 수집',     '{"badge_class": "secondary"}',60),
('agent_type', 'order',     '주문 수집',     '{"badge_class": "danger"}',   70),
('agent_type', 'ranking',   '랭킹 수집',     '{"badge_class": "primary"}',  80),
('agent_type', 'brand',     '브랜드 수집',   '{"badge_class": "dp"}',       85),
('agent_type', 'local',     '로컬 수집',     '{"badge_class": "success"}',  90)
ON CONFLICT (group_code, code) DO NOTHING;

-- category: 사이트 카테고리
INSERT INTO crawl_system_codes (group_code, code, label, extra, sort_order) VALUES
('category', '자사몰',         '자사몰',         '{"agent_type": "product"}',   10),
('category', '경쟁사몰',       '경쟁사몰',       '{"agent_type": "product"}',   20),
('category', '오픈마켓',       '오픈마켓',       '{"agent_type": "product"}',   30),
('category', '면세점',         '면세점',         '{"agent_type": "product"}',   40),
('category', '뉴스',           '뉴스',           '{"agent_type": "news"}',      50),
('category', '카페',           '카페',           '{"agent_type": "cafe"}',      60),
('category', '경쟁사이벤트',   '경쟁사이벤트',   '{"agent_type": "promotion"}', 70),
('category', '경쟁사배너',     '경쟁사배너',     '{"agent_type": "banner"}',    80),
('category', '브랜드목록',     '브랜드목록',     '{"agent_type": "directory"}', 90),
('category', '백화점',         '백화점',         '{"agent_type": "product"}',   100),
('category', '소셜커머스',     '소셜커머스',     '{"agent_type": "product"}',   110),
('category', '해외직구',       '해외직구',       '{"agent_type": "product"}',   120),
('category', '주문수집',       '주문수집',       '{"agent_type": "order"}',     130),
('category', '랭킹',           '랭킹',           '{"agent_type": "ranking"}',   140)
ON CONFLICT (group_code, code) DO NOTHING;

-- crawl_status: 수집 실행 상태
INSERT INTO crawl_system_codes (group_code, code, label, extra, sort_order) VALUES
('crawl_status', 'pending',  '대기중',   '{"badge_class": "secondary"}', 10),
('crawl_status', 'running',  '실행중',   '{"badge_class": "running"}',   20),
('crawl_status', 'success',  '성공',     '{"badge_class": "success"}',   30),
('crawl_status', 'partial',  '부분성공', '{"badge_class": "warning"}',   40),
('crawl_status', 'failed',   '실패',     '{"badge_class": "failed"}',    50),
('crawl_status', 'stopped',  '강제종료', '{"badge_class": "stopped"}',   55),
('crawl_status', 'blocked',  '차단',     '{"badge_class": "failed"}',    60)
ON CONFLICT (group_code, code) DO NOTHING;


-- ─── 테이블 리네임 마이그레이션 (기존 DB에 적용) ───

-- 이미 crawl_ 접두사가 붙은 테이블: crawl_sites, crawl_results, crawl_data, crawl_failure_log (변경 불필요)
-- 리네임 대상 테이블:
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname='public' AND tablename='platforms') THEN
        ALTER TABLE platforms RENAME TO crawl_platforms;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname='public' AND tablename='extraction_templates') THEN
        ALTER TABLE extraction_templates RENAME TO crawl_extraction_templates;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname='public' AND tablename='news_keywords') THEN
        ALTER TABLE news_keywords RENAME TO crawl_news_keywords;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname='public' AND tablename='ocr_usage_log') THEN
        ALTER TABLE ocr_usage_log RENAME TO crawl_ocr_usage_log;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname='public' AND tablename='llm_usage') THEN
        ALTER TABLE llm_usage RENAME TO crawl_llm_usage;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname='public' AND tablename='agent_field_defs') THEN
        ALTER TABLE agent_field_defs RENAME TO crawl_agent_field_defs;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname='public' AND tablename='site_credentials') THEN
        ALTER TABLE site_credentials RENAME TO crawl_site_credentials;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname='public' AND tablename='system_codes') THEN
        ALTER TABLE system_codes RENAME TO crawl_system_codes;
    END IF;
END $$;


-- ─── crawl_schedule 레거시 값 변환 ───

UPDATE crawl_sites SET crawl_schedule = 'hourly:1'   WHERE crawl_schedule = 'hourly';
UPDATE crawl_sites SET crawl_schedule = 'daily:0'    WHERE crawl_schedule = 'daily';
UPDATE crawl_sites SET crawl_schedule = 'weekly:1:0' WHERE crawl_schedule = 'weekly';
UPDATE crawl_sites SET crawl_schedule = 'monthly:1:0' WHERE crawl_schedule = 'monthly';
