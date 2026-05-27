"""
LLM 기반 사이트 구조 분석기

사이트 구조 정보를 LLM API에 전달하여
플랫폼 감지 규칙과 추출 템플릿을 자동 생성한다.

흐름:
  1. structure_collector 가 수집한 구조 정보를 프롬프트에 주입
  2. LLM API 호출 → JSON 응답 수신
  3. 응답 파싱 → 테스트 추출 → 성공 시 DB 저장
  4. 실패 시 재분석 프롬프트로 재시도 (최대 MAX_RETRY 회)
"""
import json
import os
import re

import anthropic

from core.prompts import SYSTEM_PROMPT, ANALYSIS_PROMPT, RETRY_PROMPT


# ─── 설정 ────────────────────────────────────────────────────────

MAX_RETRY = 3
LLM_MODEL = "claude-sonnet-4-20250514"
LLM_MAX_TOKENS = 8192


# ═══════════════════════════════════════════════════════════════════
# LLM 분석기 클래스
# ═══════════════════════════════════════════════════════════════════

class LLMAnalyzer:
    """LLM 을 활용하여 사이트 구조를 분석하고 추출 템플릿을 생성한다."""

    def __init__(self):
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다. "
                ".env 파일 또는 환경변수를 확인하세요."
            )
        self.client = anthropic.Anthropic(api_key=api_key)

    # ─── 공개 메서드 ──────────────────────────────────────────────

    def analyze(self, structure: dict) -> dict | None:
        """
        사이트 구조 정보를 분석하여 플랫폼 + 템플릿 JSON 을 반환한다.

        Args:
            structure: structure_collector.collect_site_structure() 의 반환값

        Returns:
            {"platform": {...}, "templates": [...]} 또는 실패 시 None
        """
        prompt = ANALYSIS_PROMPT.format(
            site_url=structure.get("site_url", ""),
            page_title=structure.get("page_title", ""),
            js_global_vars=structure.get("js_global_vars", "없음"),
            state_structure=structure.get("state_structure", "없음"),
            dom_patterns=structure.get("dom_patterns", "없음"),
            network_requests=structure.get("network_requests", "없음"),
            meta_tags=structure.get("meta_tags", "없음"),
        )

        print("[llm] 사이트 구조 분석 요청 중...")
        result = self._call_llm(prompt)

        if result is None:
            print("[llm] 분석 실패: LLM 응답을 파싱할 수 없습니다")
            return None

        # 기본 검증
        if "platform" not in result or "templates" not in result:
            print("[llm] 분석 실패: 응답에 platform 또는 templates 키 없음")
            return None

        if not isinstance(result["templates"], list) or len(result["templates"]) == 0:
            print("[llm] 분석 실패: templates 가 비어있습니다")
            return None

        print(f"[llm] 분석 완료: 플랫폼={result['platform'].get('name', '?')}, "
              f"템플릿 {len(result['templates'])}개")
        return result

    def retry_analyze(
        self,
        structure: dict,
        previous_result: dict,
        failed_target: str,
        error_type: str,
        error_message: str,
        actual_data: str,
    ) -> dict | None:
        """
        이전 분석 결과가 실패했을 때 재분석을 요청한다.

        Args:
            structure:       원본 구조 정보
            previous_result: 이전 LLM 응답 JSON
            failed_target:   실패한 추출 대상 (store / product_list 등)
            error_type:      오류 유형
            error_message:   오류 메시지
            actual_data:     실제 데이터 샘플 문자열

        Returns:
            수정된 {"platform": {...}, "templates": [...]} 또는 None
        """
        prompt = RETRY_PROMPT.format(
            site_url=structure.get("site_url", ""),
            platform_name=previous_result.get("platform", {}).get("name", "unknown"),
            previous_template=json.dumps(
                previous_result, ensure_ascii=False, indent=2,
            ),
            failed_target=failed_target,
            error_type=error_type,
            error_message=error_message,
            actual_data=actual_data,
        )

        print(f"[llm] 재분석 요청: {failed_target} 실패 → 수정 요청")
        result = self._call_llm(prompt)

        if result and "platform" in result and "templates" in result:
            print("[llm] 재분석 완료")
            return result

        print("[llm] 재분석 실패")
        return None

    # ─── 내부 메서드 ──────────────────────────────────────────────

    def _call_llm(self, user_prompt: str) -> dict | None:
        """
        LLM API 를 호출하고 응답 JSON 을 파싱하여 반환한다.

        Returns:
            파싱된 dict 또는 실패 시 None
        """
        try:
            response = self.client.messages.create(
                model=LLM_MODEL,
                max_tokens=LLM_MAX_TOKENS,
                system=SYSTEM_PROMPT,
                messages=[
                    {"role": "user", "content": user_prompt},
                ],
            )

            # 응답 텍스트 추출
            text = ""
            for block in response.content:
                if block.type == "text":
                    text += block.text

            if not text.strip():
                print("[llm] 빈 응답 수신")
                return None

            return self._parse_json(text)

        except anthropic.APIError as e:
            print(f"[llm] API 오류: {e}")
            return None
        except Exception as e:
            print(f"[llm] 예상치 못한 오류: {e}")
            return None

    @staticmethod
    def _parse_json(text: str) -> dict | None:
        """
        LLM 응답 텍스트에서 JSON 을 추출하여 파싱한다.
        코드 블록(```json ... ```)이 있으면 내부만 추출.
        """
        # 1차: 코드 블록 내부 JSON 추출 시도
        code_block = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
        if code_block:
            try:
                return json.loads(code_block.group(1).strip())
            except json.JSONDecodeError:
                pass

        # 2차: 전체 텍스트에서 JSON 객체 추출 시도
        # 첫 번째 { 부터 마지막 } 까지
        brace_start = text.find("{")
        brace_end = text.rfind("}")
        if brace_start != -1 and brace_end > brace_start:
            try:
                return json.loads(text[brace_start:brace_end + 1])
            except json.JSONDecodeError:
                pass

        # 3차: 전체 텍스트를 그대로 파싱 시도
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            print(f"[llm] JSON 파싱 실패. 응답 앞부분: {text[:200]}")
            return None
