"""
브랜드 공식홈페이지 수집 에이전트 공통 베이스

각 브랜드 에이전트는 이 클래스를 상속받아
브랜드별로 다른 부분(SKU 추출, DOM 셀렉터)만 정의하면 된다.

공통 수집 전략 (우선순위 순):
  1. JSON-LD  — schema.org/Product
  2. 네트워크 API — 페이지 로드 중 캡처된 JSON 응답
  3. DOM fallback — 브랜드별 가격 셀렉터
"""
import json
import os
import re
from abc import abstractmethod
from datetime import datetime

from core.base_agent import BaseAgent
from core.network_interceptor import NetworkInterceptor


# ── 공통 JS: JSON-LD 파싱 ────────────────────────────────────────
_JS_EXTRACT_JSONLD = """(() => {
    const scripts = document.querySelectorAll('script[type="application/ld+json"]');
    for (const s of scripts) {
        try {
            const data = JSON.parse(s.textContent);
            const candidates = Array.isArray(data) ? data : [data];
            for (const item of candidates) {
                if (!item) continue;
                const type = item['@type'] || '';
                const hasOffers = item.offers || item.Offers;
                if (type === 'Product' || (hasOffers && item.name)) {
                    const offers = item.offers || item.Offers || {};
                    const offerList = Array.isArray(offers) ? offers[0] : offers;
                    return {
                        name: item.name || '',
                        sku: item.sku || item.mpn || item.productID || '',
                        price: String(offerList.price || offerList.lowPrice || ''),
                        currency: offerList.priceCurrency || 'KRW',
                        availability: offerList.availability || '',
                    };
                }
            }
        } catch(e) {}
    }
    return null;
})()"""

# ── 공통 JS: window 전역변수 탐색 (진단용) ──────────────────────
_JS_EXTRACT_WINDOW_STATE = """(() => {
    const GLOBALS = [
        'pageContext', 'digitalData',
        '__PRELOADED_STATE__', '__NEXT_DATA__', '__INITIAL_STATE__',
        '__pinia', '__remixContext', '__NUXT__',
    ];
    for (const g of GLOBALS) {
        try {
            if (!window[g]) continue;
            const text = JSON.stringify(window[g]);
            if (text.includes('"price"') || text.includes('"Price"') || text.includes('"amount"')) {
                return { source: g, keys: Object.keys(window[g]).slice(0, 20) };
            }
        } catch(e) {}
    }
    return null;
})()"""

# ── 기본 DOM 가격 탐색 JS (브랜드별로 오버라이드 가능) ───────────
_JS_DOM_PRICE_DEFAULT = """(() => {
    const results = [];
    const selectors = [
        '[itemprop="price"]',
        '[class*="price"][class*="sales"]',
        '[class*="price"][class*="value"]',
        '[data-price]',
        '.price .value',
        '.price',
    ];
    for (const sel of selectors) {
        const el = document.querySelector(sel);
        if (!el) continue;
        const text = (
            el.getAttribute('content') ||
            el.getAttribute('data-price') ||
            el.innerText || el.textContent || ''
        ).trim();
        if (text && /[\\d,]+/.test(text) && text.length < 50) {
            results.push({ selector: sel, text: text });
            break;
        }
    }
    if (results.length === 0) {
        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        let node;
        while ((node = walker.nextNode())) {
            const t = node.textContent.trim();
            if (/[\\d,]{4,}\\s*원/.test(t) && t.length < 30) {
                const parent = node.parentElement;
                results.push({
                    selector: parent ? (parent.className.slice(0, 60) || parent.tagName) : 'text',
                    text: t,
                });
                if (results.length >= 3) break;
            }
        }
    }
    return results;
})()"""


class BrandAgent(BaseAgent):
    """브랜드 공식홈페이지 수집 에이전트 공통 베이스.

    서브클래스에서 정의할 것:
      - agent_type (property)     : 에이전트 식별자
      - _TAG (class var)          : 로그 접두사  예) "[longchamp]"
      - _sku_from_url(url)        : URL → SKU 추출 로직
      - _DOM_PRICE_JS (class var) : 브랜드별 DOM 가격 추출 JS (선택)
    """

    _TAG: str = "[brand]"
    _DOM_PRICE_JS: str = _JS_DOM_PRICE_DEFAULT

    # ── 필수 구현 ─────────────────────────────────────────────────

    @property
    @abstractmethod
    def agent_type(self) -> str: ...

    def _sku_from_url(self, url: str) -> str:
        """URL에서 SKU를 추출한다. 브랜드별로 오버라이드."""
        return ""

    # ── 공통 구현 ─────────────────────────────────────────────────

    def enable_proxy(self):
        """브랜드 에이전트는 단건 조회라 프록시 미사용."""
        pass

    def _normalize_config(self, crawl_cfg: dict) -> dict:
        return crawl_cfg

    def run_site(self, site_id: int):
        """DB에서 검색어(SKU) 목록을 읽어 가격을 수집하고 결과를 DB와 JSON에 저장한다."""
        import time
        from core.db import CrawlDB

        db = CrawlDB()
        try:
            site = db.get_site(site_id)
            keywords = db.get_active_keywords(site_id)
        finally:
            db.close()

        if not site:
            self._log(f"site_id={site_id} 를 찾을 수 없음")
            return

        if not keywords:
            self._log("등록된 검색어(SKU)가 없습니다. 설정 > 검색어 관리에서 SKU를 추가하세요.")
            return

        if not hasattr(self, 'fetch_by_sku'):
            self._log("fetch_by_sku 미구현 에이전트 — 수집 불가")
            return

        crawl_cfg = json.loads(site.get("crawl_config") or "{}")
        self._search_url_template = crawl_cfg.get("search_url_template", "")
        if self._search_url_template:
            self._log(f"검색 URL 템플릿 로드: {self._search_url_template}")

        self._log(f"수집 시작: {site['site_name']} | SKU {len(keywords)}개")
        start = time.time()

        db = CrawlDB()
        result_id = db.create_result(site_id)
        db.close()

        results = []
        try:
            for i, sku in enumerate(keywords, 1):
                self._log(f"[{i}/{len(keywords)}] SKU: {sku}")
                try:
                    result = self.fetch_by_sku(sku)
                except Exception as e:
                    self._log(f"  오류: {e}")
                    result = {"sku": sku, "error": str(e), "source": "failed"}
                results.append(result)
                name = result.get("name", "")
                price = result.get("price", "")
                src = result.get("source", "")
                self._log(f"  → {name} / {price} ({src})")

            success = [r for r in results if not r.get("error")]
            elapsed = round(time.time() - start, 1)

            # JSON 파일 저장
            site_name = site["site_name"].replace(" ", "_")
            output_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                "output", f"{site_id}_{site_name}",
            )
            os.makedirs(output_dir, exist_ok=True)
            out_path = os.path.join(output_dir, "brand_prices.json")
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            self._log(f"JSON 저장: {out_path}")

            # DB 결과 기록
            db = CrawlDB()
            db.update_result(
                result_id,
                status="success",
                products=results,
                product_count=len(success),
                elapsed_sec=elapsed,
            )
            db.close()
            self._log(f"완료: {len(success)}/{len(keywords)}건 성공 ({elapsed}초)")

        except Exception as e:
            elapsed = round(time.time() - start, 1)
            self._log(f"수집 중 오류: {e}")
            db = CrawlDB()
            db.update_result(result_id, status="failed", error_msg=str(e), elapsed_sec=elapsed)
            db.close()

    def _extract_extra(self, result: dict) -> dict:
        """추가 필드 추출 훅. 서브클래스에서 오버라이드하여 브랜드별 필드를 추가한다.
        페이지가 열려 있는 상태에서 호출된다."""
        return {}

    def fetch_product(self, url: str) -> dict:
        """상품 상세 페이지 URL에서 가격 정보를 수집한다."""
        result = {
            "url": url,
            "sku": self._sku_from_url(url),
            "name": "",
            "price": "",
            "currency": "KRW",
            "source": "failed",
            "raw_api_url": "",
            "error": "",
        }

        try:
            cookie_domain = self._get_cookie_domain(url)
            interceptor = NetworkInterceptor()

            self.enable_proxy()
            self.page = self._create_page(cookie_domain=cookie_domain, headless=True)
            interceptor.start(self.page)

            self._log("페이지 접속 중...")
            resp = self._safe_goto(url, wait_until="domcontentloaded", timeout=60000)

            if self._is_blocked(resp):
                status = resp.status if resp else "N/A"
                result["error"] = f"차단됨 (HTTP {status})"
                self._log(f"차단 감지: {result['error']}")
                self._log_block_diagnosis(resp)
                return result

            self._log(f"페이지 로드 완료 (HTTP {resp.status if resp else '?'})")
            self.page.wait_for_timeout(5000)
            self._human_dwell()

            interceptor.stop(self.page)
            captured = list(interceptor.captured)
            self._log(f"네트워크 응답 {len(captured)}건 캡처")
            for entry in captured[:5]:
                self._log(f"  └ {entry.get('method','?')} {entry.get('url','')[:100]}")

            # 1단계: JSON-LD
            self._log("JSON-LD 파싱 시도...")
            jsonld = self.page.evaluate(_JS_EXTRACT_JSONLD)
            if jsonld and jsonld.get("price"):
                result.update({
                    "source": "json-ld",
                    "name": jsonld.get("name", ""),
                    "price": jsonld.get("price", ""),
                    "currency": jsonld.get("currency", "KRW"),
                })
                if not result["sku"] and jsonld.get("sku"):
                    result["sku"] = jsonld["sku"]
                self._log(f"JSON-LD 성공: {result['name']} / {result['price']} {result['currency']}")
                result.update(self._extract_extra(result))
                return result
            self._log("JSON-LD에서 가격 없음")

            # 2단계: 네트워크 API
            self._log("캡처된 API 응답에서 가격 탐색...")
            api_result = self._search_api_for_price(captured, result["sku"])
            if api_result:
                result.update(api_result)
                self._log(f"API 성공: {result['name']} / {result['price']} {result['currency']}")
                self._log(f"  └ API URL: {result['raw_api_url']}")
                result.update(self._extract_extra(result))
                return result
            self._log("API 응답에서 가격 없음")

            # 3단계: window 전역변수 (진단용)
            self._log("window 전역변수 탐색...")
            state = self.page.evaluate(_JS_EXTRACT_WINDOW_STATE)
            if state:
                self._log(f"전역변수 발견: {state['source']} (keys: {state['keys'][:5]})")

            # 4단계: DOM fallback
            self._log("DOM 가격 요소 탐색...")
            dom_prices = self.page.evaluate(self._DOM_PRICE_JS)
            if dom_prices:
                best = dom_prices[0]
                result.update({"source": "dom", "price": best["text"]})
                self._log(f"DOM 성공: {best['text']}  (selector: {best['selector']})")
                if len(dom_prices) > 1:
                    self._log(f"  └ 전체 후보: {dom_prices}")
                result.update(self._extract_extra(result))
                return result
            self._log("DOM에서도 가격 요소 없음")

            result["error"] = "모든 추출 방법 실패"

        except Exception as e:
            result["error"] = str(e)
            self._log(f"오류: {e}")
        finally:
            try:
                self.browser_mgr.close()
            except Exception:
                pass
            self.page = None

        return result

    def _search_api_for_price(self, captured: list, sku: str) -> dict | None:
        for entry in captured:
            body = entry.get("body_parsed")
            if not isinstance(body, dict):
                continue
            text = json.dumps(body, ensure_ascii=False)
            if "price" not in text.lower() and "amount" not in text.lower():
                continue
            price = _dig_price(body, sku)
            if price:
                return {
                    "source": "api",
                    "name": price.get("name", ""),
                    "price": str(price.get("price", "")),
                    "currency": price.get("currency", "KRW"),
                    "raw_api_url": entry.get("url", ""),
                }
        return None

    def _log(self, msg: str):
        print(f"{self._TAG} {msg}", flush=True)

    def _log_block_diagnosis(self, resp):
        """차단 시 페이지 상태를 진단하여 로그로 출력한다."""
        self._log("── 차단 진단 시작 ──────────────────────────")
        try:
            # 최종 URL (리다이렉트 후)
            final_url = self.page.url
            self._log(f"  최종 URL   : {final_url}")

            # 페이지 타이틀
            title = self.page.title()
            self._log(f"  페이지 제목: {title or '(없음)'}")

            # 페이지 텍스트 앞 300자
            body_text = self.page.evaluate(
                "() => (document.body?.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 300)"
            )
            self._log(f"  페이지 텍스트: {body_text or '(없음)'}")

            # 응답 헤더 중 보안 관련
            if resp:
                headers = {}
                try:
                    headers = resp.headers
                except Exception:
                    pass
                for key in ("cf-ray", "cf-mitigated", "x-frame-options", "server", "location"):
                    val = headers.get(key, "")
                    if val:
                        self._log(f"  Header [{key}]: {val}")

        except Exception as e:
            self._log(f"  진단 중 오류: {e}")
        self._log("── 차단 진단 끝 ────────────────────────────")


# ── 유틸 ─────────────────────────────────────────────────────────

def _dig_price(data, sku: str = "", depth: int = 0) -> dict | None:
    if depth > 6:
        return None
    if isinstance(data, dict):
        keys_lower = {k.lower(): k for k in data.keys()}
        price_key = keys_lower.get("price") or keys_lower.get("amount")
        name_key = (keys_lower.get("name") or keys_lower.get("displayname")
                    or keys_lower.get("productname"))
        if price_key:
            raw_price = data[price_key]
            if isinstance(raw_price, (int, float)) or (
                isinstance(raw_price, str) and re.search(r"\d", raw_price)
            ):
                currency_key = keys_lower.get("currency") or keys_lower.get("pricecurrency")
                return {
                    "price": raw_price,
                    "name": data.get(name_key, "") if name_key else "",
                    "currency": data.get(currency_key, "KRW") if currency_key else "KRW",
                }
        for v in data.values():
            found = _dig_price(v, sku, depth + 1)
            if found:
                return found
    elif isinstance(data, list):
        for item in data[:10]:
            found = _dig_price(item, sku, depth + 1)
            if found:
                return found
    return None
