"""
LLM 사이트 분석용 프롬프트 상수

엔진이 LLM API를 호출할 때 사용하는 프롬프트 템플릿을 정의한다.
- SYSTEM_PROMPT: 모든 호출에 공통으로 적용되는 시스템 프롬프트
- ANALYSIS_PROMPT: 사이트 구조 분석 및 템플릿 생성 요청
- RETRY_PROMPT: 검증 실패 시 재분석 요청

변수 치환: str.format() 으로 {변수명} 을 런타임 데이터로 교체한다.
"""

# ═══════════════════════════════════════════════════════════════════
# 시스템 프롬프트 (모든 LLM 호출에 공통)
# ═══════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """\
당신은 웹 크롤링 자동화 시스템의 사이트 분석 엔진입니다.

[역할]
주어진 웹사이트의 구조 정보를 분석하여, 상품 데이터를 자동 수집하기 위한
"플랫폼 감지 규칙"과 "추출 템플릿"을 JSON 형식으로 생성합니다.

[사용 가능한 추출 전략]
1. state_var
   - 브라우저의 window 전역 변수(예: __PRELOADED_STATE__)에 저장된
     JSON 데이터에서 필드 매핑으로 추출하는 전략.
   - SSR 프레임워크가 초기 데이터를 전역 변수에 주입하는 사이트에 적합.

2. dom
   - CSS 셀렉터로 DOM 요소에서 직접 텍스트/속성을 추출하는 전략.
   - 전통적인 서버 렌더링 HTML 사이트에 적합.

3. api
   - 페이지가 호출하는 REST API 엔드포인트를 직접 호출하고
     응답 JSON에서 필드 매핑으로 추출하는 전략.
   - SPA에서 XHR/Fetch로 데이터를 로드하는 사이트에 적합.

[전략 선택 기준]
- window 전역 변수에 상품 데이터가 있으면 state_var 우선.
- 전역 변수가 없고, XHR/Fetch API 호출이 보이면 api.
- 둘 다 없으면 dom.
- 여러 전략이 가능하면 state_var > api > dom 순으로 우선.

[필드 매핑 작성 규칙]
- dot notation 경로: "a.b.c" -> obj.a.b.c 접근.
- 폴백 체인: ["primaryPath", "fallbackPath"] -> 첫 번째 실패 시 두 번째 시도.
- 필드명은 반드시 아래 표준 스키마의 키를 사용.

[표준 출력 스키마 - 매장 정보]
store_name      : 매장/브랜드 이름 (필수)
store_id        : 매장 고유 ID
description     : 매장 설명
representative  : 대표자명
sale_count      : 누적 판매 수
logo_url        : 로고 이미지 URL
address         : 주소
phone           : 전화번호

[표준 출력 스키마 - 상품 정보]
product_id      : 상품 고유 ID (필수)
product_name    : 상품명 (필수)
original_price  : 원래 가격
selling_price   : 판매 가격 (필수)
discount_rate   : 할인율
image_url       : 대표 이미지 URL
product_url     : 상품 상세 페이지 URL
review_count    : 리뷰 수
average_score   : 평균 평점
brand_name      : 브랜드명
category_name   : 카테고리명
description     : 상품 설명

[주의사항]
- 실제 데이터 구조에 존재하는 키만 매핑하세요. 추측으로 만들지 마세요.
- 제공된 구조 정보에 없는 필드는 매핑에서 제외하세요.
- 응답은 반드시 유효한 JSON만 출력하세요. 설명 텍스트를 포함하지 마세요.
- JSON 외의 텍스트(```json, 설명 등)를 절대 포함하지 마세요.\
"""


# ═══════════════════════════════════════════════════════════════════
# 사이트 분석 프롬프트 (최초 분석 시 사용)
# ═══════════════════════════════════════════════════════════════════

ANALYSIS_PROMPT = """\
아래 웹사이트의 구조 정보를 분석하여 플랫폼 감지 규칙과 추출 템플릿을 생성해주세요.

===============================================
[사이트 기본 정보]
===============================================
- URL: {site_url}
- 페이지 타이틀: {page_title}

===============================================
[JS 전역 변수 탐색 결과]
===============================================
{js_global_vars}

===============================================
[전역 변수 상세 구조 (깊이 2단계)]
===============================================
{state_structure}

===============================================
[DOM 구조 분석 - 반복 패턴]
===============================================
{dom_patterns}

===============================================
[네트워크 요청 (XHR/Fetch)]
===============================================
{network_requests}

===============================================
[메타 태그]
===============================================
{meta_tags}

===============================================
[응답 형식]
===============================================
아래 JSON 구조로만 응답하세요. JSON 외의 텍스트를 포함하지 마세요.

{{
  "platform": {{
    "name": "플랫폼 식별 이름 (영문 snake_case, 예: naver_smartstore)",
    "display_name": "플랫폼 표시 이름 (한글 가능)",
    "detection": {{
      "rules": [
        {{"type": "js_var_exists", "var": "전역변수명"}},
        {{"type": "url_match", "pattern": "URL 정규식 패턴"}},
        {{"type": "meta_match", "name": "메타태그명", "content": "값 패턴"}}
      ],
      "match_mode": "all 또는 any"
    }},
    "browser": {{
      "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
      "viewport": {{"width": 1920, "height": 1080}},
      "headers": {{
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"
      }},
      "allowed_domains": ["사이트에 필요한 도메인 목록"],
      "blocked_resource_types": ["font", "media"],
      "timeout": 30000
    }}
  }},

  "templates": [
    {{
      "target": "store",
      "strategy": "state_var 또는 dom 또는 api",
      "config": {{

        "__state_var 전략일 때__": "",
        "state_var": "전역변수명",
        "root_key": "매장 데이터 루트 키",
        "fields": {{
          "store_name": "키경로 또는 [폴백경로 배열]"
        }},
        "dom_fallback": {{
          "store_name": "title"
        }},

        "__dom 전략일 때__": "",
        "selectors": {{
          "store_name": {{"selector": "CSS셀렉터", "attr": "textContent 또는 속성명"}}
        }},

        "__api 전략일 때__": "",
        "endpoint": "/api/...",
        "method": "GET",
        "response": {{
          "data_path": "응답 내 데이터 경로",
          "fields": {{}}
        }}
      }}
    }},

    {{
      "target": "category",
      "strategy": "state_var 또는 dom 또는 api",
      "config": {{
        "state_var": "전역변수명 (state_var 전략 시)",
        "root_key": "카테고리 메뉴 루트 키",
        "list_key": "카테고리 배열 키",
        "fields": {{
          "id": "카테고리 ID 경로",
          "name": "카테고리 이름 경로"
        }},
        "url_pattern": "/카테고리 페이지 URL 패턴 ({{cat_id}}, {{page}} 치환자)"
      }}
    }},

    {{
      "target": "product_list",
      "strategy": "state_var 또는 dom 또는 api",
      "config": {{

        "__state_var 전략일 때__": "",
        "state_var": "전역변수명",
        "root_key": "상품 목록 루트 키",
        "list_key": "상품 배열 키",
        "total_count_key": "전체 개수 키",
        "page_size": 40,
        "fields": {{
          "product_id": "상품ID 경로",
          "product_name": "상품명 경로",
          "selling_price": "판매가 경로"
        }},

        "__dom 전략일 때__": "",
        "container": "상품 목록 컨테이너 CSS 셀렉터",
        "item_selector": "개별 상품 CSS 셀렉터",
        "fields_dom": {{
          "product_name": {{"selector": ".name", "attr": "textContent"}},
          "selling_price": {{"selector": ".price", "attr": "textContent", "regex": "[\\\\d,]+"}},
          "image_url": {{"selector": "img", "attr": "src"}},
          "product_url": {{"selector": "a", "attr": "href"}}
        }},
        "pagination": {{
          "type": "url_param 또는 click 또는 scroll",
          "param": "page 파라미터명 (url_param 시)",
          "next_button": "CSS셀렉터 (click 시)",
          "max_pages": 50
        }},

        "__api 전략일 때__": "",
        "endpoint": "/api/products",
        "method": "GET",
        "params": {{
          "page": "{{page}}",
          "size": 40
        }},
        "response": {{
          "list_path": "응답 내 상품 배열 경로",
          "total_count_path": "전체 개수 경로",
          "fields": {{}}
        }}
      }}
    }},

    {{
      "target": "product_detail",
      "strategy": "state_var 또는 dom 또는 api",
      "config": {{
        "url_pattern": "/상품 상세 URL 패턴 ({{product_id}} 치환자)",

        "__state_var 전략일 때__": "",
        "state_var": "전역변수명",
        "root_keys": ["시도할 루트키1", "시도할 루트키2"],
        "fields": {{
          "description": "상세 설명 경로",
          "detail_images": "상세 이미지 배열 경로"
        }},
        "dom_fallback": [
          "CSS셀렉터1 (상세 설명 영역)",
          "CSS셀렉터2"
        ],

        "__dom 전략일 때__": "",
        "selectors": {{
          "description": {{"selector": ".detail-content", "attr": "textContent"}},
          "detail_images": {{"selector": ".detail-content img", "attr": "src", "multiple": true}}
        }}
      }}
    }}
  ]
}}

중요: 선택한 전략에 해당하는 필드만 포함하세요.
"__state_var 전략일 때__" 같은 주석 키는 실제 응답에 포함하지 마세요.
해당 target에서 사용할 전략 하나를 선택하고, 그 전략의 필드만 작성하세요.\
"""


# ═══════════════════════════════════════════════════════════════════
# 검증 실패 시 재분석 프롬프트
# ═══════════════════════════════════════════════════════════════════

RETRY_PROMPT = """\
이전에 생성한 추출 템플릿으로 테스트 수집을 실행했지만 실패했습니다.
오류 정보와 실제 페이지 데이터를 참고하여 템플릿을 수정해주세요.

===============================================
[사이트 정보]
===============================================
- URL: {site_url}
- 감지된 플랫폼: {platform_name}

===============================================
[이전 생성 템플릿]
===============================================
{previous_template}

===============================================
[실패 상세]
===============================================
- 실패 대상: {failed_target}
- 오류 유형: {error_type}
- 오류 메시지: {error_message}

===============================================
[실제 데이터 샘플]
===============================================
{actual_data}

===============================================
[요청]
===============================================
위 오류 원인을 분석하고, 수정된 전체 JSON을 출력해주세요.
이전과 동일한 JSON 형식을 사용하세요.
변경된 부분에 "_change_reason" 키로 사유를 기록해주세요.
JSON 외의 텍스트를 포함하지 마세요.\
"""
