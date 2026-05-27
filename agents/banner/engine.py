"""
배너/비주얼 수집 에이전트 (v2)

경쟁사 메인 페이지의 배너(히어로, 서브, 팝업) 영역에서
이미지·텍스트·링크를 수집한다.

수집 파이프라인:
  1. config 로드 + 정규화
  2. 브라우저 시작 + 페이지 접속
  3. 배너 영역 탐지 (슬라이더/히어로/대형 이미지)
  4. 배너 데이터 수집 (슬라이드 순회 포함)
  5. (선택) 스크린샷 캡처
  6. 저장 (DB + JSON + 이미지)
"""
import json
import os
import time
from datetime import datetime

from core.base_agent import BaseAgent, DEFAULT_SETTINGS


_TAG = "[banner]"


class BannerAgent(BaseAgent):
    """배너/비주얼 수집 에이전트"""

    @property
    def agent_type(self) -> str:
        return "banner"

    # ══════════════════════════════════════════════════════════════
    # UI → Agent config 변환
    # ══════════════════════════════════════════════════════════════

    def _normalize_config(self, crawl_cfg: dict) -> dict:
        """UI crawl_config → Agent 내부 config 변환.

        UI 필드:
          banner_areas       → 리스트 (공백 구분 문자열도 허용)
          extra_fields       → URL 분석으로 발견된 추가 필드
          capture_screenshot, download_images, include_text, max_slides
        """
        cfg = dict(crawl_cfg)

        # banner_areas: 공백 구분 문자열이면 리스트로 변환
        val = cfg.get("banner_areas")
        if isinstance(val, str):
            cfg["banner_areas"] = val.split() if val.strip() else ["hero"]

        cfg.setdefault("banner_areas", ["hero"])
        cfg.setdefault("capture_screenshot", True)
        cfg.setdefault("download_images", False)
        cfg.setdefault("include_text", True)
        cfg.setdefault("max_slides", 10)
        cfg.setdefault("extra_fields", [])

        if isinstance(cfg["max_slides"], str):
            cfg["max_slides"] = int(cfg["max_slides"]) if cfg["max_slides"].isdigit() else 10

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

        _log(f"배너 수집 시작: {site['site_name']}  "
             f"areas={cfg['banner_areas']}")

        try:
            cookie_domain = self._get_cookie_domain(url)
            self.page = self.browser_mgr.create(cookie_domain=cookie_domain)

            resp = self._safe_goto(url)
            if self._is_blocked(resp):
                raise RuntimeError(f"차단됨 (HTTP {resp.status})")

            self.page.wait_for_timeout(DEFAULT_SETTINGS["initial_wait_ms"])
            self._human_dwell()

            # 팝업 닫기 시도
            self._close_popups()

            # 배너 영역 탐지 + 수집
            banners = self._collect_banners(cfg)

            # 스크린샷 캡처
            if cfg.get("capture_screenshot") and banners:
                self._capture_banner_screenshots(site, banners)

            # 이미지 다운로드
            if cfg.get("download_images") and banners:
                self._download_banner_images(site, banners)

            elapsed = time.time() - t0
            self.db.update_result(
                result_id, status="success",
                store_info={"site_name": site["site_name"]},
                products=banners,
                product_count=len(banners),
                elapsed_sec=elapsed,
            )
            self._save_json(site, banners)
            _log(f"배너 수집 완료: {len(banners)}개, {elapsed:.1f}초")

        except Exception as e:
            elapsed = time.time() - t0
            self.db.update_result(
                result_id, status="failed",
                error_msg=str(e), elapsed_sec=elapsed,
            )
            _log(f"배너 수집 실패: {e}")

        finally:
            self.browser_mgr.close()
            self.page = None

    # ══════════════════════════════════════════════════════════════
    # 팝업 닫기
    # ══════════════════════════════════════════════════════════════

    def _close_popups(self):
        """페이지 로드 후 나타나는 팝업/모달을 닫는다."""
        close_selectors = [
            "[class*='popup'] [class*='close']",
            "[class*='modal'] [class*='close']",
            "[class*='layer'] [class*='close']",
            "button[class*='close']",
            "[class*='popup'] button",
            ".btn_close", ".btnClose", ".ico_close",
        ]
        for sel in close_selectors:
            try:
                btns = self.page.query_selector_all(sel)
                for btn in btns[:3]:
                    if btn.is_visible():
                        btn.click()
                        self.page.wait_for_timeout(500)
            except Exception:
                continue

    # ══════════════════════════════════════════════════════════════
    # 배너 수집
    # ══════════════════════════════════════════════════════════════

    def _collect_banners(self, cfg: dict) -> list:
        """설정된 배너 영역에서 배너 데이터를 수집한다."""
        target_areas = cfg.get("banner_areas", ["hero"])
        max_slides = cfg.get("max_slides", 10)
        include_text = cfg.get("include_text", True)
        all_banners = []

        # 1단계: 배너 영역 탐지
        detected = self.page.evaluate(_JS_DETECT_BANNER_AREAS)
        if not detected:
            _log("배너 영역 탐지 실패")
            return []

        _log(f"탐지된 배너 영역: {len(detected)}개")

        for area in detected:
            area_type = area.get("type", "unknown")
            if area_type not in target_areas and "all" not in target_areas:
                continue

            is_slider = area.get("is_slider", False)

            if is_slider:
                slides = self._collect_slider_banners(
                    area, max_slides, include_text
                )
                all_banners.extend(slides)
            else:
                banner = {
                    "area_type": area_type,
                    "position": len(all_banners) + 1,
                    "image_url": area.get("image_url", ""),
                    "link_url": area.get("link_url", ""),
                    "width": area.get("width", 0),
                    "height": area.get("height", 0),
                    "collected_at": _now(),
                }
                if include_text:
                    banner["text"] = area.get("text", "")
                all_banners.append(banner)

        _log(f"총 배너 {len(all_banners)}개 수집")
        return all_banners

    def _collect_slider_banners(self, area: dict, max_slides: int,
                                include_text: bool) -> list:
        """슬라이더/캐러셀에서 각 슬라이드 배너를 수집한다."""
        selector = area.get("selector", "")
        if not selector:
            return []

        banners = []
        seen_images = set()

        # 첫 번째 슬라이드 수집
        first = self._extract_current_slide(selector, area.get("type", "hero"),
                                            include_text)
        if first and first.get("image_url"):
            seen_images.add(first["image_url"])
            first["position"] = 1
            banners.append(first)

        # 다음 슬라이드 순회
        next_selectors = [
            f"{selector} [class*='next']",
            f"{selector} [class*='Next']",
            f"{selector} .swiper-button-next",
            f"{selector} .slick-next",
            f"{selector} [class*='btn_next']",
            f"{selector} [class*='arrow_right']",
            f"{selector} [class*='right']",
            f"{selector} button:last-child",
        ]

        for slide_idx in range(1, max_slides):
            clicked = False
            for sel in next_selectors:
                try:
                    btn = self.page.query_selector(sel)
                    if btn and btn.is_visible():
                        btn.click()
                        self.page.wait_for_timeout(1000)
                        clicked = True
                        break
                except Exception:
                    continue

            if not clicked:
                break

            slide = self._extract_current_slide(
                selector, area.get("type", "hero"), include_text
            )
            if not slide or not slide.get("image_url"):
                continue

            if slide["image_url"] in seen_images:
                break
            seen_images.add(slide["image_url"])
            slide["position"] = slide_idx + 1
            banners.append(slide)

        return banners

    def _extract_current_slide(self, selector: str, area_type: str,
                               include_text: bool) -> dict | None:
        """현재 보이는 슬라이드에서 배너 데이터를 추출한다."""
        try:
            result = self.page.evaluate(
                _JS_EXTRACT_SLIDE, {"selector": selector}
            )
            if not result:
                return None

            banner = {
                "area_type": area_type,
                "image_url": result.get("image_url", ""),
                "link_url": result.get("link_url", ""),
                "width": result.get("width", 0),
                "height": result.get("height", 0),
                "collected_at": _now(),
            }
            if include_text:
                banner["text"] = result.get("text", "")
            return banner
        except Exception:
            return None

    # ══════════════════════════════════════════════════════════════
    # 스크린샷 / 이미지 다운로드
    # ══════════════════════════════════════════════════════════════

    def _capture_banner_screenshots(self, site: dict, banners: list):
        """배너 영역의 전체 스크린샷을 캡처한다."""
        output_dir = self._get_output_dir(site)
        ss_dir = os.path.join(output_dir, "screenshots")
        os.makedirs(ss_dir, exist_ok=True)

        try:
            path = os.path.join(
                ss_dir, f"banner_full_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            )
            self.page.screenshot(path=path, full_page=False)
            _log(f"스크린샷 저장: {path}")
            for b in banners:
                b["screenshot_path"] = path
        except Exception as e:
            _log(f"스크린샷 실패: {e}")

    def _download_banner_images(self, site: dict, banners: list):
        """배너 이미지를 파일로 다운로드한다."""
        output_dir = self._get_output_dir(site)
        img_dir = os.path.join(output_dir, "images")
        os.makedirs(img_dir, exist_ok=True)

        for i, banner in enumerate(banners):
            img_url = banner.get("image_url", "")
            if not img_url or not img_url.startswith("http"):
                continue

            try:
                resp = self.page.request.get(img_url)
                if resp.ok:
                    ext = _guess_ext(img_url)
                    path = os.path.join(img_dir, f"banner_{i+1}{ext}")
                    with open(path, "wb") as f:
                        f.write(resp.body())
                    banner["local_image_path"] = path
                    _log(f"이미지 다운로드: banner_{i+1}{ext}")
            except Exception as e:
                _log(f"이미지 다운로드 실패 [{i+1}]: {e}")

    # ══════════════════════════════════════════════════════════════
    # 결과 저장
    # ══════════════════════════════════════════════════════════════

    def _save_json(self, site: dict, banners: list):
        output_dir = self._get_output_dir(site)
        os.makedirs(output_dir, exist_ok=True)

        result = {
            "crawl_meta": {
                "site_name": site["site_name"],
                "site_url": site["site_url"],
                "crawl_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "agent_type": "banner",
                "agent_version": "v2",
            },
            "banners": banners,
            "total_banners": len(banners),
        }

        for path, data in [
            (os.path.join(output_dir, "banners.json"), banners),
            (os.path.join(output_dir, "crawl_result.json"), result),
        ]:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

        _log(f"파일 저장: {output_dir}")

    @staticmethod
    def _get_output_dir(site: dict) -> str:
        site_name = site["site_name"].replace(" ", "_")
        return os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "output", f"{site['id']}_{site_name}",
        )


# ══════════════════════════════════════════════════════════════════
# JS: 배너 영역 탐지
# ══════════════════════════════════════════════════════════════════

_JS_DETECT_BANNER_AREAS = """(() => {
    var results = [];
    var vpW = window.innerWidth;

    /* 슬라이더 프레임워크 탐지 */
    var sliderSelectors = [
        '.swiper-container', '.swiper', '[class*="swiper"]',
        '.slick-slider', '[class*="slick"]',
        '[class*="carousel"]', '[class*="Carousel"]',
        '[class*="slider"]', '[class*="Slider"]',
        '[class*="banner_slide"]', '[class*="bnr_slide"]',
        '[class*="main_visual"]', '[class*="mainVisual"]',
        '[class*="hero_slide"]', '[class*="heroSlide"]',
    ];

    for (var si = 0; si < sliderSelectors.length; si++) {
        try {
            var els = document.querySelectorAll(sliderSelectors[si]);
            for (var ei = 0; ei < els.length; ei++) {
                var el = els[ei];
                var rect = el.getBoundingClientRect();
                if (rect.width < vpW * 0.5 || rect.height < 100) continue;
                if (rect.top > window.innerHeight * 1.5) continue;

                var areaType = rect.top < 300 ? 'hero' : 'sub_banner';
                var img = el.querySelector('img[src]');
                var link = el.querySelector('a[href]');

                results.push({
                    type: areaType,
                    is_slider: true,
                    selector: sliderSelectors[si],
                    image_url: img ? img.src : '',
                    link_url: link ? link.href : '',
                    text: '',
                    width: Math.round(rect.width),
                    height: Math.round(rect.height)
                });
            }
        } catch(e) {}
    }

    /* 히어로 배너 (비-슬라이더 대형 이미지) */
    var heroSelectors = [
        '[class*="hero"]', '[class*="Hero"]',
        '[class*="main_banner"]', '[class*="mainBanner"]',
        '[class*="key_visual"]', '[class*="keyVisual"]',
        '[class*="top_banner"]', '[class*="topBanner"]',
        'header [class*="banner"]',
    ];

    for (var hi = 0; hi < heroSelectors.length; hi++) {
        try {
            var hels = document.querySelectorAll(heroSelectors[hi]);
            for (var hei = 0; hei < hels.length; hei++) {
                var hel = hels[hei];
                var hr = hel.getBoundingClientRect();
                if (hr.width < vpW * 0.5 || hr.height < 100) continue;

                var already = results.some(function(r) {
                    return Math.abs(r.width - Math.round(hr.width)) < 50 &&
                           Math.abs(r.height - Math.round(hr.height)) < 50;
                });
                if (already) continue;

                var himg = hel.querySelector('img[src]');
                var hlink = hel.querySelector('a[href]');
                var htext = '';
                var htEl = hel.querySelector('h1,h2,h3,[class*="title"],[class*="text"]');
                if (htEl) htext = htEl.textContent.trim().substring(0, 200);

                results.push({
                    type: 'hero',
                    is_slider: false,
                    selector: heroSelectors[hi],
                    image_url: himg ? himg.src : '',
                    link_url: hlink ? hlink.href : '',
                    text: htext,
                    width: Math.round(hr.width),
                    height: Math.round(hr.height)
                });
            }
        } catch(e) {}
    }

    /* 서브 배너 (중간 영역 대형 이미지) */
    var subSelectors = [
        '[class*="sub_banner"]', '[class*="subBanner"]',
        '[class*="mid_banner"]', '[class*="midBanner"]',
        '[class*="event_banner"]', '[class*="eventBanner"]',
        '[class*="promo_banner"]', '[class*="promoBanner"]',
    ];

    for (var sbi = 0; sbi < subSelectors.length; sbi++) {
        try {
            var sbels = document.querySelectorAll(subSelectors[sbi]);
            for (var sbei = 0; sbei < sbels.length; sbei++) {
                var sbel = sbels[sbei];
                var sbr = sbel.getBoundingClientRect();
                if (sbr.width < vpW * 0.3 || sbr.height < 80) continue;

                var sbAlready = results.some(function(r) {
                    return Math.abs(r.width - Math.round(sbr.width)) < 50 &&
                           Math.abs(r.height - Math.round(sbr.height)) < 50;
                });
                if (sbAlready) continue;

                var sbImg = sbel.querySelector('img[src]');
                var sbLink = sbel.querySelector('a[href]');
                var sbText = '';
                var sbTEl = sbel.querySelector('h1,h2,h3,[class*="title"],[class*="text"]');
                if (sbTEl) sbText = sbTEl.textContent.trim().substring(0, 200);

                results.push({
                    type: 'sub_banner',
                    is_slider: false,
                    selector: subSelectors[sbi],
                    image_url: sbImg ? sbImg.src : '',
                    link_url: sbLink ? sbLink.href : '',
                    text: sbText,
                    width: Math.round(sbr.width),
                    height: Math.round(sbr.height)
                });
            }
        } catch(e) {}
    }

    return results.length > 0 ? results : null;
})()"""


# ══════════════════════════════════════════════════════════════════
# JS: 현재 슬라이드에서 배너 데이터 추출
# ══════════════════════════════════════════════════════════════════

_JS_EXTRACT_SLIDE = """(args) => {
    var sel = args.selector;
    var container = document.querySelector(sel);
    if (!container) return null;

    /* 현재 활성 슬라이드 찾기 */
    var activeSelectors = [
        '.swiper-slide-active', '.slick-active', '.slick-current',
        '[class*="active"]', '[class*="current"]',
        '[aria-hidden="false"]'
    ];

    var slide = null;
    for (var i = 0; i < activeSelectors.length; i++) {
        slide = container.querySelector(activeSelectors[i]);
        if (slide) break;
    }
    if (!slide) {
        /* 폴백: 보이는 첫 번째 자식 */
        var children = container.children;
        for (var ci = 0; ci < children.length; ci++) {
            var r = children[ci].getBoundingClientRect();
            if (r.width > 0 && r.height > 0) {
                slide = children[ci];
                break;
            }
        }
    }
    if (!slide) return null;

    var img = slide.querySelector('img[src]');
    var link = slide.querySelector('a[href]');
    var rect = slide.getBoundingClientRect();

    /* 텍스트 추출 */
    var text = '';
    var textEl = slide.querySelector(
        'h1,h2,h3,[class*="title"],[class*="text"],[class*="desc"]'
    );
    if (textEl) text = textEl.textContent.trim().substring(0, 200);

    /* 배경 이미지 폴백 */
    var imageUrl = '';
    if (img) {
        imageUrl = img.src;
    } else {
        var bgEl = slide.querySelector('[style*="background-image"]') || slide;
        var bg = getComputedStyle(bgEl).backgroundImage;
        var m = bg.match(/url\\(["']?([^"'\\)]+)/);
        if (m) imageUrl = m[1];
    }

    return {
        image_url: imageUrl,
        link_url: link ? link.href : '',
        text: text,
        width: Math.round(rect.width),
        height: Math.round(rect.height)
    };
}"""


# ══════════════════════════════════════════════════════════════════
# 유틸리티
# ══════════════════════════════════════════════════════════════════

def _log(msg: str):
    print(f"{_TAG} {msg}")


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _guess_ext(url: str) -> str:
    lower = url.lower().split("?")[0]
    for ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".avif"):
        if lower.endswith(ext):
            return ext
    return ".jpg"
