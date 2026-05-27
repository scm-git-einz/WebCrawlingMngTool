"""
OCR 엔진 통합 모듈 (Document Parse + Tesseract)

이미지에서 텍스트를 추출하는 이중화 구조:
  1차: Upstage Document Parse API (구조 보존, 좌표 정보)
  2차: Tesseract OCR (로컬, 무료, fallback)

Document Parse 실패 시 (429 Rate Limit, 네트워크 에러 등)
자동으로 Tesseract로 전환하여 추출을 시도한다.

반환값에 사용한 엔진 정보(engine)를 포함하여
호출측에서 어떤 OCR을 사용했는지 추적할 수 있다.

사용법:
  ocr = OCRManager()
  result = ocr.extract(image_url)
  # result = {"text": "...", "elements": [...], "engine": "document-parse"}
"""
import io
import os
import time

import requests


# ─── Tesseract 설정 ──────────────────────────────────────────────

_TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
_TESSERACT_LANG = "kor+eng"

# Tesseract 사용 가능 여부 (모듈 로드 시 한 번만 체크)
_tesseract_available = False
try:
    import pytesseract
    from PIL import Image
    if os.path.exists(_TESSERACT_CMD):
        pytesseract.pytesseract.tesseract_cmd = _TESSERACT_CMD
        _tesseract_available = True
except ImportError:
    pass


# ─── Upstage Document Parse 설정 ────────────────────────────────

_API_URL = "https://api.upstage.ai/v1/document-digitization"
_MODEL = "document-parse"
_TIMEOUT = 120


# ─── 엔진 이름 상수 ─────────────────────────────────────────────

ENGINE_DOCUMENT_PARSE = "document-parse"
ENGINE_TESSERACT = "tesseract"


class OCRManager:
    """OCR 이중화 매니저

    Document Parse를 우선 사용하고, 실패 시 Tesseract로 fallback.
    각 호출 결과에 사용한 엔진 정보를 포함한다.
    """

    def __init__(self, api_key: str | None = None):
        """
        Args:
            api_key: Upstage API 키. None이면 환경변수 UPSTAGE_API_KEY 사용.
                     키가 없으면 Document Parse 비활성 → Tesseract만 사용.
        """
        self.api_key = api_key or os.environ.get("UPSTAGE_API_KEY", "")
        self._dp_available = bool(self.api_key)
        self._tesseract_available = _tesseract_available

        if not self._dp_available and not self._tesseract_available:
            raise ValueError(
                "사용 가능한 OCR 엔진이 없습니다. "
                "UPSTAGE_API_KEY를 설정하거나 "
                "Tesseract를 설치하세요."
            )

        engines = []
        if self._dp_available:
            engines.append("document-parse")
        if self._tesseract_available:
            engines.append("tesseract")
        print(f"[ocr] 사용 가능 엔진: {', '.join(engines)}")

    def extract(self, image_url: str) -> dict:
        """이미지 URL에서 텍스트를 추출한다.

        Document Parse 우선 → 실패 시 Tesseract fallback.

        Args:
            image_url: 이미지 URL

        Returns:
            {
                "text": str,          # 추출된 텍스트
                "elements": list,     # Document Parse 요소 (Tesseract는 [])
                "engine": str,        # 사용한 엔진 이름
                "status": str,        # "success" | "fail" | "rate_limit"
                "elapsed_ms": int,    # 처리 시간 (ms)
                "error": str,         # 에러 메시지 (성공 시 "")
            }
        """
        empty = {
            "text": "", "elements": [], "engine": "",
            "status": "fail", "elapsed_ms": 0, "error": "",
        }

        if not image_url:
            return empty

        # ── 이미지 다운로드 ──
        try:
            img_resp = requests.get(image_url, timeout=30)
            if img_resp.status_code != 200:
                return {
                    **empty,
                    "error": f"이미지 다운로드 실패: HTTP {img_resp.status_code}",
                }
            img_data = img_resp.content
        except requests.exceptions.Timeout:
            return {**empty, "error": "이미지 다운로드 타임아웃"}
        except Exception as e:
            return {**empty, "error": f"이미지 다운로드 실패: {e}"}

        # Content-Type에서 확장자 추론
        content_type = img_resp.headers.get("Content-Type", "")
        ext = ".png"
        if "jpeg" in content_type or "jpg" in content_type:
            ext = ".jpg"
        elif "webp" in content_type:
            ext = ".webp"

        # ── 1차: Document Parse ──
        if self._dp_available:
            result = self._try_document_parse(img_data, ext)
            if result["status"] == "success":
                return result
            # rate_limit 또는 fail → Tesseract fallback
            dp_error = result["error"]
            dp_status = result["status"]
        else:
            dp_error = "API 키 없음"
            dp_status = "fail"

        # ── 2차: Tesseract fallback ──
        if self._tesseract_available:
            result = self._try_tesseract(img_data)
            if result["status"] == "success":
                # Document Parse 실패 사유 기록
                result["dp_fallback_reason"] = dp_error
                return result
            return result

        # 둘 다 실패
        return {
            **empty,
            "engine": ENGINE_DOCUMENT_PARSE,
            "status": dp_status,
            "error": dp_error,
        }

    def _try_document_parse(
        self, img_data: bytes, ext: str,
    ) -> dict:
        """Upstage Document Parse API를 시도한다."""
        t0 = time.time()
        filename = f"image{ext}"

        headers = {"Authorization": f"Bearer {self.api_key}"}
        files = {"document": (filename, img_data)}
        data = {"model": _MODEL, "output_formats": '["text"]'}

        try:
            resp = requests.post(
                _API_URL, headers=headers,
                files=files, data=data, timeout=_TIMEOUT,
            )
        except Exception as e:
            elapsed = int((time.time() - t0) * 1000)
            return {
                "text": "", "elements": [],
                "engine": ENGINE_DOCUMENT_PARSE,
                "status": "fail",
                "elapsed_ms": elapsed,
                "error": f"API 요청 실패: {e}",
            }

        elapsed = int((time.time() - t0) * 1000)

        if resp.status_code == 429:
            return {
                "text": "", "elements": [],
                "engine": ENGINE_DOCUMENT_PARSE,
                "status": "rate_limit",
                "elapsed_ms": elapsed,
                "error": "API Rate Limit (429)",
            }

        if resp.status_code != 200:
            return {
                "text": "", "elements": [],
                "engine": ENGINE_DOCUMENT_PARSE,
                "status": "fail",
                "elapsed_ms": elapsed,
                "error": f"API 에러 {resp.status_code}: {resp.text[:200]}",
            }

        result = resp.json()

        # ── 텍스트 추출 ──
        text = ""
        content = result.get("content", {})
        if isinstance(content, dict):
            text = content.get("text", "")
        if not text:
            text = result.get("text", "")
        if not text:
            pages = result.get("pages", [])
            page_texts = [p["text"] for p in pages if "text" in p]
            text = "\n".join(page_texts)

        # ── 요소(elements) 추출 ──
        elements = []
        for elem in result.get("elements", []):
            ec = elem.get("content", {})
            if isinstance(ec, dict):
                elem_text = ec.get("text", "")
            elif isinstance(ec, str):
                elem_text = ec
            else:
                elem_text = ""

            coords = elem.get("coordinates", [])
            if coords and len(coords) >= 2:
                x1 = coords[0].get("x", 0)
                y1 = coords[0].get("y", 0)
                x2 = coords[2].get("x", 0) if len(coords) > 2 else x1
                y2 = coords[2].get("y", 0) if len(coords) > 2 else y1
            else:
                x1 = y1 = x2 = y2 = 0

            elements.append({
                "text": elem_text,
                "category": elem.get("category", ""),
                "x": x1, "y": y1, "x2": x2, "y2": y2,
            })

        return {
            "text": text.strip(),
            "elements": elements,
            "engine": ENGINE_DOCUMENT_PARSE,
            "status": "success",
            "elapsed_ms": elapsed,
            "error": "",
        }

    def _try_tesseract(self, img_data: bytes) -> dict:
        """Tesseract OCR을 시도한다."""
        t0 = time.time()
        try:
            image = Image.open(io.BytesIO(img_data))
            text = pytesseract.image_to_string(
                image, lang=_TESSERACT_LANG,
            )
            elapsed = int((time.time() - t0) * 1000)
            return {
                "text": text.strip(),
                "elements": [],  # Tesseract는 요소 정보 없음
                "engine": ENGINE_TESSERACT,
                "status": "success",
                "elapsed_ms": elapsed,
                "error": "",
            }
        except Exception as e:
            elapsed = int((time.time() - t0) * 1000)
            print(f"[ocr] Tesseract 실패: {e}")
            return {
                "text": "", "elements": [],
                "engine": ENGINE_TESSERACT,
                "status": "fail",
                "elapsed_ms": elapsed,
                "error": str(e),
            }


# ─── 하위 호환 별칭 ─────────────────────────────────────────────
# 기존 코드에서 UpstageOCR 이름으로 import하는 경우를 위한 별칭
UpstageOCR = OCRManager
