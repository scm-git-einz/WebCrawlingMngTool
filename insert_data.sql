-- ============================================================
-- 크롤링 관리 플랫폼 — PostgreSQL 초기 데이터 삽입 스크립트
-- agent_field_defs: 에이전트별 수집 필드 정의 (66건)
-- ============================================================

INSERT INTO agent_field_defs (agent_type, field_key, label, config_key, sort_order)
VALUES
    -- ── product: 상품 수집 필드 (11건) ──
    ('product', 'name',           '상품명',       'collect_fields', 1),
    ('product', 'price',          '가격',         'collect_fields', 2),
    ('product', 'brand',          '브랜드',       'collect_fields', 3),
    ('product', 'image',          '이미지',       'collect_fields', 4),
    ('product', 'rank',           '순위',         'collect_fields', 5),
    ('product', 'original_price', '원가',         'collect_fields', 6),
    ('product', 'discount_rate',  '할인율',       'collect_fields', 7),
    ('product', 'gift',           '사은품',       'collect_fields', 8),
    ('product', 'reference_no',   '레퍼런스번호', 'collect_fields', 9),
    ('product', 'category',       '카테고리',     'collect_fields', 10),
    ('product', 'detail_page',    '상세수집',     'detail_page',    11),

    -- ── news: 뉴스 수집 필드 (6건) ──
    ('news', 'title',        '제목',     '',             1),
    ('news', 'url',          'URL',      '',             2),
    ('news', 'press',        '언론사',   '',             3),
    ('news', 'date',         '날짜',     '',             4),
    ('news', 'description',  '요약',     '',             5),
    ('news', 'collect_body', '본문수집', 'collect_body', 6),

    -- ── cafe: 카페 수집 필드 (5건) ──
    ('cafe', 'title',          '제목',       '',              1),
    ('cafe', 'collect_body',   '본문수집',   'collect_body',  2),
    ('cafe', 'collect_links',  '링크수집',   'collect_links', 3),
    ('cafe', 'collect_images', '이미지수집', 'collect_images',4),
    ('cafe', 'collect_ocr',    'OCR수집',    'collect_ocr',   5),

    -- ── promotion: 이벤트 수집 필드 (5건) ──
    ('promotion', 'title',                  '이벤트명',   '',                       1),
    ('promotion', 'period',                 '기간',       '',                       2),
    ('promotion', 'image',                  '이미지',     '',                       3),
    ('promotion', 'collect_details',        '상세수집',   'collect_details',        4),
    ('promotion', 'collect_event_products', '이벤트상품', 'collect_event_products', 5),

    -- ── banner: 배너 수집 필드 (6건) ──
    ('banner', 'hero',               '히어로배너', 'banner_areas',       1),
    ('banner', 'sub_banner',         '서브배너',   'banner_areas',       2),
    ('banner', 'popup',              '팝업',       'banner_areas',       3),
    ('banner', 'capture_screenshot', '스크린샷',   'capture_screenshot', 4),
    ('banner', 'download_images',    '이미지저장', 'download_images',    5),
    ('banner', 'include_text',       '텍스트수집', 'include_text',       6),

    -- ── directory: 목록 수집 필드 (11건) ──
    ('directory', 'name',             '이름',       'collect_fields',   1),
    ('directory', 'category',         '카테고리',   'collect_fields',   2),
    ('directory', 'branch',           '지점명',     'collect_fields',   3),
    ('directory', 'location',         '위치(층)',   'collect_fields',   4),
    ('directory', 'phone',            '전화번호',   'collect_fields',   5),
    ('directory', 'description',      '설명',       'collect_fields',   6),
    ('directory', 'period',           '기간',       'collect_fields',   7),
    ('directory', 'status',           '상태',       'collect_fields',   8),
    ('directory', 'detail_url',       '상세URL',    'collect_fields',   9),
    ('directory', 'index_navigation', '인덱스탐색', 'index_navigation', 10),
    ('directory', 'collect_details',  '상세수집',   'collect_details',  11),

    -- ── order: 주문서 수집 필드 (19건) ──
    ('order', 'brand',                  '브랜드',       'collect_fields',  1),
    ('order', 'product_name',           '상품명',       'collect_fields',  2),
    ('order', 'regular_price_usd',      '정상가($)',    'collect_fields',  3),
    ('order', 'regular_price_krw',      '정상가(원)',   'collect_fields',  4),
    ('order', 'member_discount_usd',    '회원할인($)',  'collect_fields',  5),
    ('order', 'member_discount_krw',    '회원할인(원)', 'collect_fields',  6),
    ('order', 'member_discount_reason', '할인사유',     'collect_fields',  7),
    ('order', 'benefit_usd',            '혜택($)',      'collect_fields',  8),
    ('order', 'benefit_krw',            '혜택(원)',     'collect_fields',  9),
    ('order', 'benefit_reason',         '혜택사유',     'collect_fields',  10),
    ('order', 'payment_usd',            '결제($)',      'collect_fields',  11),
    ('order', 'payment_krw',            '결제(원)',     'collect_fields',  12),
    ('order', 'discount_rate',          '할인율',       'collect_fields',  13),
    ('order', 'duty_free_limit',        '면세한도',     'collect_fields',  14),
    ('order', 'tax_point',              '과세포인트',   'collect_fields',  15),
    ('order', 'l_point',                'L.POINT',      'collect_fields',  16),
    ('order', 'event_coupons',          '이벤트쿠폰',  'event_coupons',   17),
    ('order', 'auto_discovery',         '자동탐색',     'auto_discovery',  18),
    ('order', 'coupon_keywords',        '쿠폰키워드',  'coupon_keywords', 19),

    -- ── coupon: 쿠폰 수집 필드 (3건) ──
    ('coupon', 'event_coupons',   '이벤트쿠폰', 'event_coupons',   1),
    ('coupon', 'auto_discovery',  '자동탐색',   'auto_discovery',  2),
    ('coupon', 'coupon_keywords', '쿠폰키워드', 'coupon_keywords', 3)

ON CONFLICT (agent_type, field_key) DO NOTHING;
