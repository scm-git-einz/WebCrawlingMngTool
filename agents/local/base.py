"""로컬 e커머스 상품 상세 수집 에이전트 공통 베이스

각 로컬 에이전트는 이 클래스를 상속받아
사이트별 DOM 셀렉터(_JS_EXTRACT_DOM)만 오버라이드하면 된다.

수집 항목: 브랜드, 상품명, 정상가, 할인율, 할인가
payload:  상품 상세 페이지 URL (DB keywords에 저장)
"""
import json
import os
from abc import abstractmethod

from core.base_agent import BaseAgent


# ── 공통 JS: JSON-LD 파싱 ─────────────────────────────
_JS_EXTRACT_JSONLD = """(() => {
    const scripts = document.querySelectorAll('script[type="application/ld+json"]');
    for (const s of scripts) {
        try {
            const data = JSON.parse(s.textContent);
            const items = Array.isArray(data) ? data : [data];
            for (const item of items) {
                if (!item || item['@type'] !== 'Product') continue;
                const offers = item.offers || {};
                const offer  = Array.isArray(offers) ? offers[0] : offers;
                const brand  = item.brand?.name || (typeof item.brand === 'string' ? item.brand : '');
                return {
                    brand:            brand,
                    name:             item.name || '',
                    regular_price:    String(offer.highPrice || offer.price || ''),
                    discounted_price: String(offer.lowPrice  || offer.price || ''),
                    currency:         offer.priceCurrency || 'KRW',
                };
            }
        } catch(e) {}
    }
    return null;
})()"""

# ── 기본 DOM fallback (서브클래스에서 오버라이드) ─────
_JS_EXTRACT_DOM_DEFAULT = """(() => {
    const get = (sels) => {
        for (const sel of sels) {
            const el = document.querySelector(sel);
            if (!el) continue;
            const t = (el.getAttribute('content') || el.innerText || el.textContent || '').trim();
            if (t) return t;
        }
        return '';
    };
    return {
        brand:            get(['.brand a', '[class*="brand"] a']),
        name:             get(['.prd-name', 'h1']),
        regular_price:    get(['.price-1 .tx-num', '.price-1', 'del[class*="price"]']),
        discounted_price: get(['.price-2 .tx-num', '.price-2', '[class*="sale-price"]']),
        discount_rate:    get(['.price-3 .tx-num', '.discount-rate', '[class*="discount-rate"]']),
    };
})()"""


class LocalAgent(BaseAgent):
    """로컬 e커머스 상품 상세 수집 에이전트 베이스.

    서브클래스에서 정의할 것:
      - agent_type (property)       : 에이전트 식별자 (예: "local_oliveyoung")
      - _TAG (class var)            : 로그 접두사
      - _JS_EXTRACT_DOM (class var) : 사이트별 DOM 가격/상품 추출 JS
    """

    _TAG: str = "[local]"
    _JS_EXTRACT_DOM: str = _JS_EXTRACT_DOM_DEFAULT

    @property
    @abstractmethod
    def agent_type(self) -> str: ...

    def _normalize_config(self, crawl_cfg: dict) -> dict:
        return crawl_cfg

    def run_site(self, site_id: int):
        """DB keywords(상품 상세 URL)를 읽어 수집하고 결과를 저장한다."""
        import time
        from core.db import CrawlDB

        db = CrawlDB()
        try:
            site     = db.get_site(site_id)
            keywords = db.get_active_keywords(site_id)
        finally:
            db.close()

        if not site:
            self._log(f"site_id={site_id} 를 찾을 수 없음")
            return
        if not keywords:
            self._log("등록된 상품 URL이 없습니다. 설정 > URL 관리에서 상품 상세 URL을 추가하세요.")
            return

        self._log(f"수집 시작: {site['site_name']} | URL {len(keywords)}개")
        start = time.time()

        db = CrawlDB()
        result_id = db.create_result(site_id)
        db.close()

        # 브라우저를 루프 전에 한 번만 생성 — 쿠키/세션 유지
        first_url = keywords[0]
        cookie_domain = self._get_cookie_domain(first_url)
        self.page = self._create_page(cookie_domain=cookie_domain, headless=True)

        results = []
        try:
            for i, url in enumerate(keywords, 1):
                self._log(f"[{i}/{len(keywords)}] {url[:80]}")
                try:
                    result = self.fetch_product(url)
                except Exception as e:
                    self._log(f"  오류: {e}")
                    result = {"url": url, "error": str(e)}
                results.append(result)
                self._log(
                    f"  → [{result.get('brand', '')}] {result.get('name', '')} "
                    f"| 정상가:{result.get('regular_price', '')} "
                    f"할인율:{result.get('discount_rate', '')} "
                    f"할인가:{result.get('discounted_price', '')}"
                )
                if i < len(keywords):
                    self._delay()

            success = [r for r in results if not r.get("error")]
            elapsed = round(time.time() - start, 1)

            site_name  = site["site_name"].replace(" ", "_")
            output_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                "output", f"{site_id}_{site_name}",
            )
            os.makedirs(output_dir, exist_ok=True)
            out_path = os.path.join(output_dir, "local_products.json")
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            self._log(f"JSON 저장: {out_path}")

            db = CrawlDB()
            db.update_result(
                result_id, status="success", products=results,
                product_count=len(success), elapsed_sec=elapsed,
            )
            db.close()
            self._log(f"완료: {len(success)}/{len(keywords)}건 성공 ({elapsed}초)")

        except Exception as e:
            elapsed = round(time.time() - start, 1)
            self._log(f"수집 중 오류: {e}")
            db = CrawlDB()
            db.update_result(result_id, status="failed", error_msg=str(e), elapsed_sec=elapsed)
            db.close()

        finally:
            try:
                self.browser_mgr.close()
            except Exception:
                pass
            self.page = None

    def fetch_product(self, url: str) -> dict:
        """상품 상세 URL에서 브랜드/상품명/가격 정보를 수집한다.

        run_site()에서 브라우저를 열어 self.page를 세팅한 뒤 호출해야 한다.
        """
        result = {
            "url": url,
            "brand": "", "name": "",
            "regular_price": "", "discounted_price": "", "discount_rate": "",
            "currency": "KRW",
            "error": "",
        }

        self._log("페이지 접속 중...")
        resp = self._safe_goto(url, wait_until="domcontentloaded", timeout=60000)

        if self._is_blocked(resp):
            result["error"] = f"차단됨 (HTTP {resp.status if resp else 'N/A'})"
            self._log(f"차단 감지: {result['error']}")
            return result

        self._log(f"페이지 로드 완료 (HTTP {resp.status if resp else '?'})")
        self._human_dwell()
        self._human_scroll()

        # 1순위: JSON-LD
        self._log("JSON-LD 파싱 시도...")
        jsonld = self.page.evaluate(_JS_EXTRACT_JSONLD)
        if jsonld and jsonld.get("name"):
            result.update({"source": "json-ld", **jsonld})
            # discount_rate는 JSON-LD에 없으므로 DOM에서 보완
            dom = self.page.evaluate(self._JS_EXTRACT_DOM)
            if dom.get("discount_rate"):
                result["discount_rate"] = dom["discount_rate"]
            self._log(f"JSON-LD 성공: {result['name']}")
            return result
        self._log("JSON-LD에서 상품명 없음")

        # 2순위: DOM
        self._log("DOM 파싱 시도...")
        dom = self.page.evaluate(self._JS_EXTRACT_DOM)
        if dom.get("name"):
            result.update({"source": "dom", **dom})
            self._log(f"DOM 성공: {result['name']}")
            return result

        result["error"] = "모든 추출 방법 실패"
        self._log(result["error"])
        return result

    def _log(self, msg: str):
        print(f"{self._TAG} {msg}", flush=True)
