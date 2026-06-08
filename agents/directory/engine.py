"""
브랜드/이벤트 목록 수집 에이전트 (v2)

경쟁사 면세점의 입점 브랜드 디렉토리나 이벤트 목록 페이지에서
구조화된 목록 데이터를 수집한다.

수집 파이프라인:
  1. config 로드 + 정규화
  2. 브라우저 시작 + 페이지 접속
  3. 목록 구조 탐지 (인덱스/카드/테이블)
  4. 항목 수집 (인덱스 순회 / 페이지네이션 / 단일)
  5. (선택) 항목 상세 수집
  6. 저장 (DB + JSON)
"""
import json
import os
import re
import time
from datetime import datetime
from urllib.parse import urljoin

from core.base_agent import BaseAgent, DEFAULT_SETTINGS
from core.network_interceptor import NetworkInterceptor


_TAG = "[directory]"

_DEFAULT_FIELDS = ["name", "category"]


class DirectoryAgent(BaseAgent):
    """브랜드/이벤트 목록 수집 에이전트"""

    @property
    def agent_type(self) -> str:
        return "directory"

    # ══════════════════════════════════════════════════════════════
    # UI → Agent config 변환
    # ══════════════════════════════════════════════════════════════

    def _normalize_config(self, crawl_cfg: dict) -> dict:
        """UI crawl_config → Agent 내부 config 변환.

        UI 필드:
          collect_fields    → 리스트 (공백 구분 문자열도 허용)
          extra_fields      → URL 분석으로 발견된 추가 필드
                              [{raw_key, standard_key, label}, ...]
          list_type, collect_details, index_navigation, max_items
        """
        cfg = dict(crawl_cfg)

        # collect_fields: 공백 구분 문자열이면 리스트로 변환
        val = cfg.get("collect_fields")
        if isinstance(val, str):
            cfg["collect_fields"] = val.split() if val.strip() else list(_DEFAULT_FIELDS)

        cfg.setdefault("collect_fields", list(_DEFAULT_FIELDS))
        cfg.setdefault("list_type", "brand_directory")
        cfg.setdefault("collect_details", False)
        cfg.setdefault("index_navigation", False)
        cfg.setdefault("extra_fields", [])
        cfg.setdefault("categories", [])
        cfg.setdefault("load_all_pages", True)

        if cfg.pop("item_limit_type", None) == "all":
            cfg["max_items"] = 0
        cfg.setdefault("max_items", 0)

        if isinstance(cfg["max_items"], str):
            cfg["max_items"] = int(cfg["max_items"]) if cfg["max_items"].isdigit() else 0

        return cfg

    # ══════════════════════════════════════════════════════════════
    # 메인 파이프라인
    # ══════════════════════════════════════════════════════════════

    def run_site(self, site_id: int):
        site = self.db.get_site(site_id)
        if not site:
            _log(f"사이트 ID={site_id} 를 찾을 수 없습니다")
            return

        result_id = self.db.create_result(site_id)
        t0 = time.time()
        cfg = self._normalize_config(self.get_crawl_config(site))
        url = site["site_url"]

        _log(f"목록 수집 시작: {site['site_name']}  "
             f"type={cfg['list_type']}  index={cfg['index_navigation']}")

        try:
            cookie_domain = self._get_cookie_domain(url)
            interceptor = NetworkInterceptor()
            self.page = self._create_page(cookie_domain=cookie_domain)
            interceptor.start(self.page)

            resp = self._safe_goto(url)
            if self._is_blocked(resp):
                raise RuntimeError(f"차단됨 (HTTP {resp.status})")

            self.page.wait_for_timeout(DEFAULT_SETTINGS["initial_wait_ms"])
            self._human_dwell()

            interceptor.stop(self.page)
            captured = list(interceptor.captured)
            _log(f"네트워크 요청 {len(captured)}건 캡처")

            # 목록 수집
            if cfg.get("list_type") == "brand_branch":
                items = self._collect_brand_branch(cfg)
            elif cfg.get("index_navigation"):
                items = self._collect_by_index(cfg, captured)
            else:
                items = self._collect_single_page(cfg, captured)

            # 상세 수집 (선택)
            if cfg.get("collect_details") and items:
                items = self._collect_item_details(items, site)

            # max_items 제한
            max_items = cfg.get("max_items", 0)
            if max_items > 0 and len(items) > max_items:
                items = items[:max_items]

            # 필드 필터링 + 타임스탬프 추가
            items = self._filter_items(items, cfg)
            for item in items:
                item["collected_at"] = _now()

            elapsed = time.time() - t0
            self.db.update_result(
                result_id, status="success",
                store_info={"site_name": site["site_name"]},
                products=items,
                product_count=len(items),
                elapsed_sec=elapsed,
            )
            self._save_json(site, items, cfg)
            _log(f"목록 수집 완료: {len(items)}개 항목, {elapsed:.1f}초")

        except Exception as e:
            elapsed = time.time() - t0
            self.db.update_result(
                result_id, status="failed",
                error_msg=str(e), elapsed_sec=elapsed,
            )
            _log(f"목록 수집 실패: {e}")

        finally:
            self.browser_mgr.close()
            self.page = None

    # ══════════════════════════════════════════════════════════════
    # 수집 방법 0: 브랜드 지점 (카테고리 탭 + 지점별 더보기)
    # ══════════════════════════════════════════════════════════════

    def _collect_brand_branch(self, cfg: dict) -> list:
        """카테고리별 브랜드 지점 정보를 수집한다.

        면세점 브랜드 매장 페이지(dl/dt/dd 구조)에서
        브랜드명, 지점, 위치(층), 카테고리, 전화번호를 추출.
        """
        all_items = []
        seen = set()
        categories = cfg.get("categories", [])
        load_all = cfg.get("load_all_pages", True)

        # 카테고리 탭 탐지
        cat_tabs = self.page.evaluate(_JS_DETECT_CATEGORY_TABS)
        if cat_tabs:
            _log(f"카테고리 탭 {len(cat_tabs)}개 탐지: "
                 + ", ".join(t.get("text", "") for t in cat_tabs[:5]) + "...")
        else:
            _log("카테고리 탭 없음 → 현재 페이지에서 직접 추출")

        # 수집 대상 카테고리 결정
        if categories:
            targets = [{"code": c, "text": c} for c in categories]
        elif cat_tabs:
            targets = [{"code": "0", "text": "전체"}]
        else:
            targets = [{"code": None, "text": "현재페이지"}]

        for ti, target in enumerate(targets):
            code = target["code"]
            label = target["text"]
            _log(f"카테고리 [{label}] ({ti+1}/{len(targets)})")

            if code is not None and cat_tabs:
                try:
                    self.page.evaluate(
                        "(cd) => { if(typeof catChange==='function') catChange(cd, null); }",
                        code
                    )
                    self.page.wait_for_timeout(4000)
                except Exception as e:
                    _log(f"  카테고리 전환 실패: {e}")
                    continue

            # 더보기 전체 로드
            if load_all:
                self._load_all_more(cfg)

            # 브랜드 항목 추출
            items = self.page.evaluate(_JS_EXTRACT_BRAND_BRANCH)
            if not items:
                # fallback: 범용 dl/dd 추출
                items = self.page.evaluate(_JS_EXTRACT_BRAND_BRANCH_FALLBACK)

            added = 0
            for item in (items or []):
                name = (item.get("name") or "").strip()
                branch = (item.get("branch") or "").strip()
                location = (item.get("location") or "").strip()
                key = f"{name}|{branch}|{location}"
                if name and key not in seen:
                    seen.add(key)
                    all_items.append(item)
                    added += 1

            _log(f"  +{added}개 (총 {len(all_items)})")
            if ti < len(targets) - 1:
                self._delay()

        return all_items

    def _load_all_more(self, cfg: dict):
        """모든 지점의 '더보기'를 클릭하여 전체 데이터를 로드한다."""
        max_rounds = 200
        for _ in range(max_rounds):
            result = self.page.evaluate(_JS_CLICK_NEXT_MORE)
            if not result or result.get("done"):
                break
            branch = result.get("branch", "")
            loaded = result.get("loaded", 0)
            total = result.get("total", 0)
            _log(f"  더보기: {branch} ({loaded}/{total})")
            self.page.wait_for_timeout(2000)
            self._delay()

    # ══════════════════════════════════════════════════════════════
    # 수집 방법 1: 인덱스 순회 (A~Z, ㄱ~ㅎ)
    # ══════════════════════════════════════════════════════════════

    def _collect_by_index(self, cfg: dict, captured: list) -> list:
        """알파벳/가나다 인덱스를 순회하며 항목을 수집한다."""
        all_items = []
        seen = set()

        # 인덱스 탭/링크 탐지
        index_tabs = self.page.evaluate(_JS_DETECT_INDEX_TABS)
        if not index_tabs:
            _log("인덱스 탭을 찾을 수 없음 → 단일 페이지 모드로 전환")
            return self._collect_single_page(cfg, captured)

        _log(f"인덱스 탭 {len(index_tabs)}개 탐지")

        for idx, tab in enumerate(index_tabs):
            label = tab.get("label", "")
            _log(f"인덱스 [{label}] ({idx+1}/{len(index_tabs)})")

            try:
                # 탭 클릭
                self.page.evaluate(
                    "(sel) => { var el = document.querySelector(sel); if(el) el.click(); }",
                    tab.get("selector", "")
                )
                self.page.wait_for_timeout(DEFAULT_SETTINGS["page_wait_ms"])

                # 항목 추출
                items = self._extract_list_items(cfg)
                added = 0
                for item in items:
                    key = item.get("name", "").strip()
                    if key and key not in seen:
                        seen.add(key)
                        item["brand_initial"] = label
                        all_items.append(item)
                        added += 1

                _log(f"  +{added}개 (총 {len(all_items)})")

            except Exception as e:
                _log(f"  인덱스 [{label}] 오류: {e}")

            self._delay()

            max_items = cfg.get("max_items", 0)
            if max_items > 0 and len(all_items) >= max_items:
                break

        return all_items

    # ══════════════════════════════════════════════════════════════
    # 수집 방법 2: 단일 페이지 / API
    # ══════════════════════════════════════════════════════════════

    def _collect_single_page(self, cfg: dict, captured: list) -> list:
        """현재 페이지 또는 API 응답에서 목록을 수집한다."""
        # API 우선 시도
        items = self._try_api_extraction(captured, cfg)
        if items:
            return items

        # DOM 추출
        items = self._extract_list_items(cfg)
        if not items:
            # 스크롤 후 재시도
            self._human_scroll()
            self.page.wait_for_timeout(2000)
            items = self._extract_list_items(cfg)

        return items

    def _try_api_extraction(self, captured: list, cfg: dict) -> list | None:
        """네트워크 캡처에서 목록 JSON을 찾는다."""
        list_type = cfg.get("list_type", "brand_directory")
        extra_fields = cfg.get("extra_fields", [])

        for entry in captured:
            body = entry.get("body_parsed")
            if not body or not isinstance(body, (dict, list)):
                continue

            arr = _find_list_array(body, list_type)
            if arr and len(arr) >= 2:
                items = []
                for raw in arr:
                    item = _normalize_item(raw, list_type)
                    # extra_fields: raw_key로 추가 필드 추출
                    for ef in extra_fields:
                        raw_key = ef.get("raw_key", "")
                        std_key = ef.get("standard_key", "")
                        if not std_key or std_key in item:
                            continue
                        if "." in raw_key:
                            parts = raw_key.split(".", 1)
                            parent = raw.get(parts[0])
                            if isinstance(parent, dict):
                                val = parent.get(parts[1])
                                if val is not None and val != "":
                                    item[std_key] = str(val).strip()
                        else:
                            val = raw.get(raw_key)
                            if val is not None and val != "":
                                item[std_key] = str(val).strip()
                    if item.get("name"):
                        items.append(item)
                if items:
                    _log(f"API 탐지: {len(items)}개 항목")
                    return items

        return None

    def _extract_list_items(self, cfg: dict) -> list:
        """DOM에서 목록 항목을 추출한다."""
        list_type = cfg.get("list_type", "brand_directory")

        try:
            result = self.page.evaluate(
                _JS_EXTRACT_LIST_ITEMS, {"list_type": list_type}
            )
            if result and isinstance(result, list):
                return result
        except Exception:
            pass

        return []

    # ══════════════════════════════════════════════════════════════
    # 상세 수집
    # ══════════════════════════════════════════════════════════════

    def _collect_item_details(self, items: list, site: dict) -> list:
        """각 항목의 상세 페이지에서 추가 정보를 수집한다."""
        base_url = site["site_url"].rstrip("/")
        _log(f"상세 수집 대상: {len(items)}개")

        for i, item in enumerate(items, 1):
            url = item.get("detail_url", "")
            if not url:
                continue

            if not url.startswith("http"):
                url = urljoin(base_url + "/", url)

            _log(f"[{i}/{len(items)}] {item.get('name', '')[:30]}")

            try:
                resp = self._safe_goto(url)
                if self._is_blocked(resp):
                    continue
                self._human_dwell()

                detail = self.page.evaluate(_JS_EXTRACT_ITEM_DETAIL)
                if detail:
                    if detail.get("description"):
                        item["description"] = detail["description"][:2000]
                    if detail.get("period"):
                        item["period"] = detail["period"]
                    if detail.get("status"):
                        item["status"] = detail["status"]
                    if detail.get("brand_count"):
                        item["brand_count"] = detail["brand_count"]
            except Exception as e:
                _log(f"  상세 오류: {e}")

            if i < len(items):
                self._delay()

        _log("상세 수집 완료")
        return items

    # ══════════════════════════════════════════════════════════════
    # 필드 필터링
    # ══════════════════════════════════════════════════════════════

    @staticmethod
    def _filter_items(items: list, cfg: dict) -> list:
        """collect_fields + extra_fields 기준으로 항목 필드를 필터링한다."""
        keep = set(cfg.get("collect_fields", _DEFAULT_FIELDS))
        # extra_fields의 standard_key 추가
        for ef in cfg.get("extra_fields", []):
            std_key = ef.get("standard_key", "")
            if std_key:
                keep.add(std_key)
        # 항상 유지할 메타 필드
        keep.update(["collected_at", "brand_initial", "detail_url", "image_url",
                      "location", "phone", "branch"])

        result = []
        for item in items:
            filtered = {k: v for k, v in item.items() if k in keep}
            if filtered.get("name"):
                result.append(filtered)
        return result

    # ══════════════════════════════════════════════════════════════
    # 결과 저장
    # ══════════════════════════════════════════════════════════════

    def _save_json(self, site: dict, items: list, cfg: dict):
        site_name = site["site_name"].replace(" ", "_")
        output_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "output", f"{site['id']}_{site_name}",
        )
        os.makedirs(output_dir, exist_ok=True)

        result = {
            "crawl_meta": {
                "site_name": site["site_name"],
                "site_url": site["site_url"],
                "crawl_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "agent_type": "directory",
                "agent_version": "v2",
                "list_type": cfg.get("list_type", "brand_directory"),
            },
            "items": items,
            "total_items": len(items),
        }

        for path, data in [
            (os.path.join(output_dir, "directory.json"), items),
            (os.path.join(output_dir, "crawl_result.json"), result),
        ]:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

        _log(f"파일 저장: {output_dir}")


# ══════════════════════════════════════════════════════════════════
# JS: 카테고리 탭 탐지 (브랜드 지점)
# ══════════════════════════════════════════════════════════════════

_JS_DETECT_CATEGORY_TABS = """(() => {
    var tabs = [];
    var sels = [
        'ul.branch_link > li > a',
        '[class*="cate_tab"] a', '[class*="cateTab"] a',
        '[class*="filter"] li a', '[class*="tab_menu"] a'
    ];
    for (var i = 0; i < sels.length; i++) {
        var els = document.querySelectorAll(sels[i]);
        if (els.length < 3) continue;
        for (var j = 0; j < els.length; j++) {
            var el = els[j];
            var text = el.textContent.trim();
            if (!text || text.length > 20) continue;
            var onclick = el.getAttribute('onclick') || '';
            var m = onclick.match(/catChange\\s*\\(\\s*['\"]?([^'\"\\),]+)/);
            var code = m ? m[1] : String(j);
            tabs.push({ text: text, code: code });
        }
        if (tabs.length >= 3) return tabs;
    }
    return null;
})()"""


# ══════════════════════════════════════════════════════════════════
# JS: 브랜드 지점 dl/dt/dd 추출
# ══════════════════════════════════════════════════════════════════

_JS_EXTRACT_BRAND_BRANCH = """(() => {
    var container = document.getElementById('brchBrndInfo');
    if (!container) return null;
    var wraps = container.querySelectorAll('.search_wrap');
    if (wraps.length === 0) return null;
    var items = [];
    wraps.forEach(function(wrap) {
        var branch = '';
        var h4 = wrap.querySelector('h4');
        if (h4) branch = h4.textContent.trim();
        wrap.querySelectorAll('dl').forEach(function(dl) {
            var dt = dl.querySelector('dt');
            var name = dt ? dt.textContent.trim() : '';
            var lis = dl.querySelectorAll('dd > ul > li');
            var location = lis.length > 0 ? lis[0].textContent.trim() : '';
            var category = lis.length > 1 ? lis[1].textContent.trim() : '';
            var telDd = dl.querySelector('dd.tel');
            var phone = telDd ? telDd.textContent.trim() : '';
            if (name) {
                items.push({
                    name: name.substring(0, 200),
                    branch: branch,
                    location: location,
                    category: category,
                    phone: phone
                });
            }
        });
    });
    return items.length > 0 ? items : null;
})()"""


_JS_EXTRACT_BRAND_BRANCH_FALLBACK = """(() => {
    /* 범용 fallback: table 또는 반복 구조에서 브랜드 정보 추출 */
    var items = [];
    /* table 방식 */
    var rows = document.querySelectorAll('table tbody tr');
    if (rows.length >= 2) {
        rows.forEach(function(tr) {
            var tds = tr.querySelectorAll('td');
            if (tds.length >= 2) {
                var name = tds[0].textContent.trim();
                var location = tds.length > 1 ? tds[1].textContent.trim() : '';
                var category = tds.length > 2 ? tds[2].textContent.trim() : '';
                var phone = '';
                for (var i = 0; i < tds.length; i++) {
                    var t = tds[i].textContent.trim();
                    if (/\\d{2,4}-\\d{3,4}-\\d{4}/.test(t) || /^\\+\\d/.test(t)) {
                        phone = t; break;
                    }
                }
                if (name && name.length < 200) {
                    items.push({ name: name, branch: '', location: location,
                                 category: category, phone: phone });
                }
            }
        });
        if (items.length >= 2) return items;
    }
    /* dl/dd 방식 (컨테이너 ID 없는 경우) */
    var dls = document.querySelectorAll('dl');
    if (dls.length >= 3) {
        dls.forEach(function(dl) {
            var dt = dl.querySelector('dt');
            var name = dt ? dt.textContent.trim() : '';
            var dds = dl.querySelectorAll('dd');
            var location = '', category = '', phone = '';
            dds.forEach(function(dd) {
                var t = dd.textContent.trim();
                if (dd.classList.contains('tel') || /\\d{2,4}-\\d{3,4}-\\d{4}/.test(t) || /^\\+\\d/.test(t)) {
                    phone = t;
                } else {
                    var lis = dd.querySelectorAll('li');
                    if (lis.length > 0) location = lis[0].textContent.trim();
                    if (lis.length > 1) category = lis[1].textContent.trim();
                }
            });
            if (name && name.length < 200) {
                items.push({ name: name, branch: '', location: location,
                             category: category, phone: phone });
            }
        });
        if (items.length >= 2) return items;
    }
    return items.length > 0 ? items : null;
})()"""


# ══════════════════════════════════════════════════════════════════
# JS: 더보기 버튼 클릭 (지점별)
# ══════════════════════════════════════════════════════════════════

_JS_CLICK_NEXT_MORE = """(() => {
    /* 아직 더보기가 남은 지점을 찾아서 클릭 */
    var wraps = document.querySelectorAll('#brchBrndInfo .search_wrap, .branch_search .search_wrap');
    for (var i = 0; i < wraps.length; i++) {
        var wrap = wraps[i];
        /* 지점 코드와 total count 파악 */
        var totInput = wrap.querySelector('input[id^="brchTotCnt_"]');
        var pageInput = wrap.querySelector('input[id^="curPageNo_"]');
        if (!totInput || !pageInput) continue;
        var brchCd = totInput.id.replace('brchTotCnt_', '');
        var total = parseInt(totInput.value) || 0;
        var curPage = parseInt(pageInput.value) || 1;
        var loaded = (curPage - 1) * 30;
        if (loaded >= total) continue;
        /* 해당 지점의 더보기 버튼 클릭 */
        var moreBtn = document.getElementById('btnBrndMore_' + brchCd);
        if (moreBtn) {
            var a = moreBtn.querySelector('a');
            if (a) a.click();
            else moreBtn.click();
        } else if (typeof moreEvent === 'function') {
            moreEvent(brchCd);
        }
        var h4 = wrap.querySelector('h4');
        return {
            done: false,
            branch: h4 ? h4.textContent.trim() : brchCd,
            loaded: loaded,
            total: total
        };
    }
    return { done: true };
})()"""


# ══════════════════════════════════════════════════════════════════
# JS: 인덱스 탭 탐지
# ══════════════════════════════════════════════════════════════════

_JS_DETECT_INDEX_TABS = """(() => {
    /* A~Z, ㄱ~ㅎ, # 등의 인덱스 탭을 찾는다 */
    var tabSelectors = [
        '[class*="brand"] [class*="index"] a',
        '[class*="brand"] [class*="index"] button',
        '[class*="brand"] [class*="alpha"] a',
        '[class*="brand"] [class*="alpha"] button',
        '[class*="index_list"] a',
        '[class*="indexList"] a',
        '[class*="alphabet"] a',
        '[class*="alphabet"] button',
        '[class*="brand_nav"] a',
        '[class*="brandNav"] a',
        '[class*="initial"] a',
        '[class*="initial"] button',
        'nav[class*="brand"] a',
    ];

    for (var i = 0; i < tabSelectors.length; i++) {
        try {
            var els = document.querySelectorAll(tabSelectors[i]);
            if (els.length < 5) continue;

            var tabs = [];
            for (var j = 0; j < els.length; j++) {
                var text = els[j].textContent.trim();
                if (text.length > 3) continue;
                tabs.push({
                    label: text,
                    selector: _buildSelector(els[j])
                });
            }
            if (tabs.length >= 5) return tabs;
        } catch(e) {}
    }

    /* 폴백: 단일 문자 링크 그룹 탐색 */
    var allLinks = document.querySelectorAll('a, button');
    var singleCharLinks = [];
    for (var li = 0; li < allLinks.length; li++) {
        var lt = allLinks[li].textContent.trim();
        if (lt.length === 1 && /[A-Z가-힣#]/.test(lt)) {
            singleCharLinks.push(allLinks[li]);
        }
    }

    if (singleCharLinks.length >= 10) {
        /* 부모가 같은 그룹 찾기 */
        var parentMap = new Map();
        for (var pi = 0; pi < singleCharLinks.length; pi++) {
            var p = singleCharLinks[pi].parentElement;
            if (!parentMap.has(p)) parentMap.set(p, []);
            parentMap.get(p).push(singleCharLinks[pi]);
        }

        var bestGroup = null;
        parentMap.forEach(function(group) {
            if (!bestGroup || group.length > bestGroup.length) {
                bestGroup = group;
            }
        });

        if (bestGroup && bestGroup.length >= 10) {
            return bestGroup.map(function(el) {
                return {
                    label: el.textContent.trim(),
                    selector: _buildSelector(el)
                };
            });
        }
    }

    return null;

    function _buildSelector(el) {
        if (el.id) return '#' + el.id;
        var path = [];
        var cur = el;
        while (cur && cur !== document.body) {
            var tag = cur.tagName.toLowerCase();
            var parent = cur.parentElement;
            if (parent) {
                var idx = 0;
                for (var c = 0; c < parent.children.length; c++) {
                    if (parent.children[c].tagName === cur.tagName) {
                        if (parent.children[c] === cur) break;
                        idx++;
                    }
                }
                tag += ':nth-of-type(' + (idx + 1) + ')';
            }
            path.unshift(tag);
            cur = cur.parentElement;
        }
        return 'body > ' + path.join(' > ');
    }
})()"""


# ══════════════════════════════════════════════════════════════════
# JS: DOM에서 목록 항목 추출
# ══════════════════════════════════════════════════════════════════

_JS_EXTRACT_LIST_ITEMS = """(args) => {
    var listType = args.list_type;

    if (listType === 'brand_directory') {
        return extractBrandList();
    } else {
        return extractEventList();
    }

    function extractBrandList() {
        var itemSelectors = [
            '[class*="brand"] [class*="list"] li',
            '[class*="brand"] [class*="item"]',
            '[class*="brand_list"] li',
            '[class*="brandList"] li',
            '[class*="brand"] ul li',
            '[class*="brand"] a[href]',
            'ul[class*="list"] li a',
        ];

        for (var i = 0; i < itemSelectors.length; i++) {
            try {
                var els = document.querySelectorAll(itemSelectors[i]);
                if (els.length < 3) continue;

                var items = [];
                for (var j = 0; j < els.length; j++) {
                    var el = els[j];
                    var name = '';

                    /* 이름 추출: 명시적 요소 → 링크 텍스트 → 전체 텍스트 */
                    var nameEl = el.querySelector(
                        '[class*="name"], [class*="title"], [class*="brand"] span, strong'
                    );
                    if (nameEl) name = nameEl.textContent.trim();
                    if (!name) {
                        var linkEl = el.querySelector('a');
                        if (linkEl) name = linkEl.textContent.trim();
                    }
                    if (!name) name = el.textContent.trim();

                    if (!name || name.length > 100) continue;

                    var link = el.querySelector('a[href]');
                    var catEl = el.querySelector(
                        '[class*="category"], [class*="cate"], [class*="desc"]'
                    );

                    items.push({
                        name: name.substring(0, 100),
                        category: catEl ? catEl.textContent.trim().substring(0, 50) : '',
                        detail_url: link ? link.href : ''
                    });
                }
                if (items.length >= 3) return items;
            } catch(e) {}
        }
        return [];
    }

    function extractEventList() {
        var itemSelectors = [
            '[class*="event"] [class*="list"] li',
            '[class*="event"] [class*="item"]',
            '[class*="event_list"] li',
            '[class*="eventList"] li',
            '[class*="promotion"] [class*="list"] li',
            '[class*="exhibit"] [class*="list"] li',
            'ul[class*="event"] li',
            'a[href*="event"]',
        ];

        for (var i = 0; i < itemSelectors.length; i++) {
            try {
                var els = document.querySelectorAll(itemSelectors[i]);
                if (els.length < 2) continue;

                var items = [];
                for (var j = 0; j < els.length; j++) {
                    var el = els[j];

                    var titleEl = el.querySelector(
                        '[class*="title"], [class*="name"], h3, h4, strong'
                    );
                    var title = titleEl
                        ? titleEl.textContent.trim()
                        : el.textContent.trim().substring(0, 100);

                    if (!title || title.length > 200) continue;

                    var link = el.tagName === 'A' ? el : el.querySelector('a[href]');
                    var imgEl = el.querySelector('img[src]');

                    /* 기간 추출 */
                    var period = '';
                    var dateEl = el.querySelector(
                        '[class*="date"], [class*="period"], [class*="term"], time'
                    );
                    if (dateEl) period = dateEl.textContent.trim();
                    if (!period) {
                        var allText = el.textContent;
                        var dm = allText.match(
                            /\\d{4}[.\\-/]\\d{1,2}[.\\-/]\\d{1,2}\\s*~\\s*\\d{4}[.\\-/]\\d{1,2}[.\\-/]\\d{1,2}/
                        );
                        if (dm) period = dm[0];
                    }

                    /* 상태 */
                    var status = '';
                    var statusEl = el.querySelector(
                        '[class*="status"], [class*="state"], [class*="badge"]'
                    );
                    if (statusEl) status = statusEl.textContent.trim();

                    items.push({
                        name: title.substring(0, 200),
                        detail_url: link ? link.href : '',
                        image_url: imgEl ? imgEl.src : '',
                        period: period.substring(0, 50),
                        status: status.substring(0, 20),
                        category: 'event'
                    });
                }
                if (items.length >= 2) return items;
            } catch(e) {}
        }
        return [];
    }
}"""


# ══════════════════════════════════════════════════════════════════
# JS: 항목 상세 페이지에서 정보 추출
# ══════════════════════════════════════════════════════════════════

_JS_EXTRACT_ITEM_DETAIL = """(() => {
    var desc = '';
    var metaDesc = document.querySelector('meta[name="description"]');
    if (metaDesc) desc = metaDesc.content || '';
    if (!desc || desc.length < 20) {
        var main = document.querySelector(
            '[class*="detail"], [class*="content"], article, main'
        );
        if (main) desc = main.innerText.substring(0, 2000);
    }

    /* 기간 */
    var period = '';
    var dateEl = document.querySelector(
        '[class*="date"], [class*="period"], [class*="term"], time'
    );
    if (dateEl) period = dateEl.textContent.trim();

    /* 상태 */
    var status = '';
    var statusEl = document.querySelector(
        '[class*="status"], [class*="state"]'
    );
    if (statusEl) status = statusEl.textContent.trim();

    /* 브랜드 수 (디렉토리 상세) */
    var brandCount = 0;
    var listItems = document.querySelectorAll(
        '[class*="brand"] [class*="item"], [class*="brand"] li'
    );
    if (listItems.length > 0) brandCount = listItems.length;

    return {
        description: desc,
        period: period.substring(0, 100),
        status: status.substring(0, 30),
        brand_count: brandCount
    };
})()"""


# ══════════════════════════════════════════════════════════════════
# 유틸리티
# ══════════════════════════════════════════════════════════════════

def _log(msg: str):
    print(f"{_TAG} {msg}")


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _find_list_array(data, list_type: str, depth: int = 0) -> list | None:
    """JSON에서 목록 배열을 재귀 탐색한다."""
    if depth > 5:
        return None

    if isinstance(data, list) and len(data) >= 2:
        if isinstance(data[0], dict):
            if list_type == "brand_directory":
                if _looks_like_brand(data[0]):
                    return data
            else:
                if _looks_like_event(data[0]):
                    return data

    if isinstance(data, dict):
        for val in data.values():
            result = _find_list_array(val, list_type, depth + 1)
            if result:
                return result

    return None


def _looks_like_brand(obj: dict) -> bool:
    keys = " ".join(str(k) for k in obj.keys()).lower()
    return bool(re.search(r"name|brand|title", keys))


def _looks_like_event(obj: dict) -> bool:
    keys = " ".join(str(k) for k in obj.keys()).lower()
    has_name = bool(re.search(r"name|title|subject", keys))
    has_date = bool(re.search(r"date|period|start|end|term", keys))
    return has_name and has_date


def _normalize_item(raw: dict, list_type: str) -> dict:
    """API 응답 항목을 표준 포맷으로 변환한다."""
    item = {}

    # 이름
    for k in ("name", "brandName", "brand_name", "title", "subject",
              "brandNm", "eventTitle", "event_title"):
        if raw.get(k):
            item["name"] = str(raw[k]).strip()
            break

    # 카테고리
    for k in ("category", "categoryName", "category_name", "cateName", "type"):
        if raw.get(k):
            item["category"] = str(raw[k]).strip()
            break

    # URL
    for k in ("url", "link", "detailUrl", "detail_url", "brandUrl", "eventUrl"):
        if raw.get(k):
            item["detail_url"] = str(raw[k]).strip()
            break

    if list_type == "event_list":
        # 기간
        for k in ("period", "dateText", "date_text"):
            if raw.get(k):
                item["period"] = str(raw[k]).strip()
                break
        else:
            start = raw.get("startDate") or raw.get("start_date") or ""
            end = raw.get("endDate") or raw.get("end_date") or ""
            if start:
                item["period"] = f"{start} ~ {end}".strip()

        # 상태
        for k in ("status", "state", "eventStatus"):
            if raw.get(k):
                item["status"] = str(raw[k]).strip()
                break

        # 이미지
        for k in ("imageUrl", "image_url", "imgUrl", "thumbnail", "image"):
            if raw.get(k):
                item["image_url"] = str(raw[k]).strip()
                break

    return item
