"""
사이트 구조 정보 수집기

Playwright Page 객체를 받아 사이트의 구조 정보를 자동 수집한다.
수집된 정보는 LLM 분석 프롬프트의 변수로 주입된다.

수집 항목:
  1. JS 전역 변수 탐색 (window.__*__)
  2. 전역 변수 상세 구조 (깊이 2단계)
  3. DOM 반복 패턴 (상품 카드 후보)
  4. 메타 태그
  5. 네트워크 요청 로그 (XHR/Fetch)
"""
import json

from playwright.sync_api import Page


# ─── JS 코드: 전역 변수 탐색 ──────────────────────────────────────

_JS_GLOBAL_VARS = """() => {
    var result = {};
    var candidates = [
        '__PRELOADED_STATE__', '__NEXT_DATA__', '__NUXT__',
        '__INITIAL_STATE__', '__APP_DATA__', '__STORE_STATE__',
        '__SSR_DATA__', '__APOLLO_STATE__', 'Shopify',
        '__pinia', '__REACT_QUERY_STATE__'
    ];
    for (var i = 0; i < candidates.length; i++) {
        var v = candidates[i];
        try {
            if (window[v] && typeof window[v] === 'object') {
                result[v] = Object.keys(window[v]).slice(0, 50);
            }
        } catch(e) {}
    }
    var allKeys = Object.keys(window);
    for (var j = 0; j < allKeys.length; j++) {
        var key = allKeys[j];
        try {
            if (key.indexOf('__') === 0
                && key.lastIndexOf('__') === key.length - 2
                && key.length > 4
                && !result[key]
                && typeof window[key] === 'object'
                && window[key] !== null) {
                result[key] = Object.keys(window[key]).slice(0, 50);
            }
        } catch(e) {}
    }
    return result;
}"""


# ─── JS 코드: 전역 변수 상세 구조 ────────────────────────────────

_JS_STATE_STRUCTURE = """(varName) => {
    var state = window[varName];
    if (!state) return null;
    var result = {};
    var keys = Object.keys(state);
    for (var i = 0; i < keys.length; i++) {
        var key = keys[i];
        var val = state[key];
        try {
            if (val && typeof val === 'object' && !Array.isArray(val)) {
                var subKeys = Object.keys(val).slice(0, 30);
                var sample = {};
                for (var j = 0; j < Math.min(subKeys.length, 15); j++) {
                    var sk = subKeys[j];
                    var sv = val[sk];
                    if (Array.isArray(sv)) {
                        sample[sk] = '[Array(' + sv.length + ')]';
                        if (sv.length > 0 && typeof sv[0] === 'object' && sv[0] !== null) {
                            sample[sk + '[0]_keys'] = Object.keys(sv[0]).slice(0, 25);
                        }
                    } else if (typeof sv === 'object' && sv !== null) {
                        sample[sk] = '{' + Object.keys(sv).slice(0, 15).join(', ') + '}';
                    } else {
                        var str = String(sv);
                        sample[sk] = str.length > 100 ? str.substring(0, 100) + '...' : str;
                    }
                }
                result[key] = {"_keys": subKeys, "_sample": sample};
            } else if (Array.isArray(val)) {
                result[key] = '[Array(' + val.length + ')]';
                if (val.length > 0 && typeof val[0] === 'object' && val[0] !== null) {
                    result[key + '[0]_keys'] = Object.keys(val[0]).slice(0, 25);
                }
            } else {
                var s = String(val);
                result[key] = s.length > 100 ? s.substring(0, 100) + '...' : s;
            }
        } catch(e) {
            result[key] = '[Error: ' + e.message + ']';
        }
    }
    return result;
}"""


# ─── JS 코드: DOM 반복 패턴 탐색 ─────────────────────────────────

_JS_DOM_PATTERNS = """() => {
    var tagClassCount = {};
    var allEls = document.querySelectorAll('*');
    for (var i = 0; i < allEls.length; i++) {
        var el = allEls[i];
        var cls = el.className;
        if (typeof cls === 'string' && cls.trim().length > 0) {
            var tag = el.tagName.toLowerCase();
            var firstClass = cls.trim().split(/\\s+/)[0];
            var key = tag + '.' + firstClass;
            tagClassCount[key] = (tagClassCount[key] || 0) + 1;
        }
    }
    var repeated = {};
    for (var k in tagClassCount) {
        if (tagClassCount[k] >= 5) {
            repeated[k] = tagClassCount[k];
        }
    }
    var items = [];
    for (var rk in repeated) {
        items.push({selector: rk, count: repeated[rk]});
    }
    items.sort(function(a, b) { return b.count - a.count; });
    items = items.slice(0, 20);

    var result = {};
    for (var m = 0; m < items.length; m++) {
        var sel = items[m].selector;
        var cnt = items[m].count;
        var dotIdx = sel.indexOf('.');
        var clsName = sel.substring(dotIdx + 1);
        var sample = document.querySelector('.' + clsName);
        var childInfo = '';
        if (sample) {
            var children = sample.children;
            var childTags = [];
            for (var n = 0; n < Math.min(children.length, 10); n++) {
                var child = children[n];
                var cTag = child.tagName.toLowerCase();
                var cCls = (typeof child.className === 'string' && child.className.trim())
                           ? '.' + child.className.trim().split(/\\s+/)[0]
                           : '';
                childTags.push(cTag + cCls);
            }
            childInfo = childTags.join(', ');
        }
        result[sel] = {"count": cnt, "children": childInfo};
    }
    return result;
}"""


# ─── JS 코드: 메타 태그 수집 ─────────────────────────────────────

_JS_META_TAGS = """() => {
    var metas = document.querySelectorAll('meta');
    var result = {};
    for (var i = 0; i < metas.length; i++) {
        var name = metas[i].getAttribute('name')
                || metas[i].getAttribute('property')
                || '';
        var content = metas[i].getAttribute('content') || '';
        if (name && content) {
            result[name] = content.length > 200
                           ? content.substring(0, 200) + '...'
                           : content;
        }
    }
    result['_title'] = document.title || '';
    var gen = document.querySelector('meta[name="generator"]');
    if (gen) {
        result['_generator'] = gen.getAttribute('content') || '';
    }
    return result;
}"""


# ═══════════════════════════════════════════════════════════════════
# 구조 수집 함수
# ═══════════════════════════════════════════════════════════════════

def collect_site_structure(page: Page) -> dict:
    """
    사이트에 접속한 Page 객체에서 구조 정보를 수집하여 반환한다.

    반환 딕셔너리 키:
      - site_url:          현재 페이지 URL
      - page_title:        페이지 타이틀
      - js_global_vars:    발견된 전역 변수와 최상위 키 목록
      - state_structure:   전역 변수 상세 구조 (깊이 2단계)
      - dom_patterns:      DOM 반복 패턴 (상품 카드 후보)
      - meta_tags:         메타 태그 정보
      - network_requests:  네트워크 요청 로그 (별도 수집 필요)
    """
    result = {
        "site_url": page.url,
        "page_title": "",
        "js_global_vars": "발견된 전역 변수 없음",
        "state_structure": "전역 변수가 없어 상세 구조 없음",
        "dom_patterns": "분석 실패",
        "meta_tags": "메타 태그 없음",
        "network_requests": "수집되지 않음",
    }

    # 페이지 타이틀
    try:
        result["page_title"] = page.title() or ""
    except Exception:
        pass

    # 1. JS 전역 변수 탐색
    try:
        global_vars = page.evaluate(_JS_GLOBAL_VARS)
        if global_vars:
            result["js_global_vars"] = json.dumps(
                global_vars, ensure_ascii=False, indent=2,
            )

            # 2. 첫 번째 발견된 전역 변수의 상세 구조
            first_var = list(global_vars.keys())[0]
            state_detail = page.evaluate(_JS_STATE_STRUCTURE, first_var)
            if state_detail:
                result["state_structure"] = json.dumps(
                    state_detail, ensure_ascii=False, indent=2,
                )
                result["_detected_state_var"] = first_var
        else:
            result["js_global_vars"] = "발견된 전역 변수 없음"
    except Exception as e:
        result["js_global_vars"] = f"탐색 실패: {e}"

    # 3. DOM 반복 패턴
    try:
        dom = page.evaluate(_JS_DOM_PATTERNS)
        if dom:
            result["dom_patterns"] = json.dumps(
                dom, ensure_ascii=False, indent=2,
            )
    except Exception as e:
        result["dom_patterns"] = f"분석 실패: {e}"

    # 4. 메타 태그
    try:
        meta = page.evaluate(_JS_META_TAGS)
        if meta:
            result["meta_tags"] = json.dumps(
                meta, ensure_ascii=False, indent=2,
            )
    except Exception as e:
        result["meta_tags"] = f"수집 실패: {e}"

    return result


def format_network_log(entries: list[dict]) -> str:
    """
    네트워크 요청 로그 목록을 프롬프트용 문자열로 포매팅한다.

    entries 형식: [{"method": "GET", "url": "...", "status": 200, "type": "xhr"}, ...]
    """
    if not entries:
        return "XHR/Fetch 요청 없음"

    lines = []
    for e in entries[:30]:
        method = e.get("method", "GET")
        url = e.get("url", "")
        status = e.get("status", "")
        res_type = e.get("type", "")
        lines.append(f"  {method} {url} -> {status} ({res_type})")

    return "\n".join(lines)
