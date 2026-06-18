"""
LLM API 호출 클라이언트 — 토큰 사용량 자동 추적

사용 예시:
    from core.llm_client import LLMClient

    llm = LLMClient(agent_type="product", site_id=5)
    result = llm.ask(
        task_type="description_summary",
        prompt="다음 상품 설명을 3줄로 요약해줘: ...",
    )
    print(result["text"])       # LLM 응답 텍스트
    print(result["tokens"])     # {"prompt": 500, "completion": 120, "total": 620}
    print(result["cost_usd"])   # 0.0023

모든 호출은 자동으로 DB llm_usage 테이블에 기록됨.
"""

import os
import time
from datetime import datetime

# ── 모델별 토큰 단가 (USD per 1K tokens) ──
MODEL_PRICING = {
    # Anthropic Claude
    "claude-sonnet-4-20250514":    {"input": 0.003,  "output": 0.015},
    "claude-haiku-4-20250414":     {"input": 0.0008, "output": 0.004},
    "claude-opus-4-20250514":      {"input": 0.015,  "output": 0.075},
    # OpenAI (참고용)
    "gpt-4o":                      {"input": 0.005,  "output": 0.015},
    "gpt-4o-mini":                 {"input": 0.00015,"output": 0.0006},
    # 기본값 (알 수 없는 모델)
    "_default":                    {"input": 0.003,  "output": 0.015},
}

# 기본 모델
DEFAULT_MODEL = "claude-sonnet-4-20250514"


def _calc_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """모델별 토큰 단가로 비용(USD)을 계산한다."""
    pricing = MODEL_PRICING.get(model, MODEL_PRICING["_default"])
    cost = (prompt_tokens / 1000) * pricing["input"] + \
           (completion_tokens / 1000) * pricing["output"]
    return round(cost, 6)


class LLMClient:
    """LLM API 호출 + 토큰 추적 클라이언트.

    Args:
        agent_type: 호출하는 에이전트 유형 (product, news 등)
        site_id:    관련 사이트 ID (선택)
        model:      사용할 모델명 (기본: claude-sonnet-4-20250514)
    """

    def __init__(
        self,
        agent_type: str,
        site_id: int | None = None,
        model: str = DEFAULT_MODEL,
    ):
        self.agent_type = agent_type
        self.site_id = site_id
        self.model = model
        self._api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    def ask(
        self,
        task_type: str,
        prompt: str,
        system: str = "",
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> dict:
        """LLM에 질문하고 응답 + 토큰 사용량을 반환한다.

        Args:
            task_type:   작업 유형 (structure_detection, description_summary 등)
            prompt:      사용자 프롬프트
            system:      시스템 프롬프트 (선택)
            max_tokens:  최대 출력 토큰
            temperature: 온도 (0.0 = 결정적)

        Returns:
            {
                "text": "응답 텍스트",
                "tokens": {"prompt": N, "completion": N, "total": N},
                "cost_usd": 0.0023,
                "model": "claude-sonnet-4-20250514",
                "elapsed_ms": 1234,
            }
        """
        start = time.time()

        try:
            text, prompt_tokens, completion_tokens = self._call_api(
                prompt=prompt,
                system=system,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        except Exception as e:
            # API 호출 실패 시에도 기록
            elapsed = int((time.time() - start) * 1000)
            self._log_usage(
                task_type=task_type,
                prompt_tokens=0,
                completion_tokens=0,
                cost_usd=0.0,
                input_preview=prompt[:100],
                output_preview=f"ERROR: {str(e)[:80]}",
                elapsed_ms=elapsed,
            )
            raise

        elapsed = int((time.time() - start) * 1000)
        cost = _calc_cost(self.model, prompt_tokens, completion_tokens)

        # DB에 사용량 기록
        self._log_usage(
            task_type=task_type,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost,
            input_preview=prompt[:100],
            output_preview=text[:100] if text else "",
            elapsed_ms=elapsed,
        )

        return {
            "text": text,
            "tokens": {
                "prompt": prompt_tokens,
                "completion": completion_tokens,
                "total": prompt_tokens + completion_tokens,
            },
            "cost_usd": cost,
            "model": self.model,
            "elapsed_ms": elapsed,
        }

    def _call_api(
        self,
        prompt: str,
        system: str,
        max_tokens: int,
        temperature: float,
    ) -> tuple[str, int, int]:
        """실제 LLM API 호출. (text, prompt_tokens, completion_tokens) 반환.

        현재는 Anthropic Messages API 사용.
        API 키가 없으면 에러를 발생시킨다.
        """
        if not self._api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다. "
                "LLM 기능을 사용하려면 API 키를 설정해주세요."
            )

        import anthropic

        client = anthropic.Anthropic(api_key=self._api_key)
        kwargs = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system

        response = client.messages.create(**kwargs)

        text = ""
        for block in response.content:
            if hasattr(block, "text"):
                text += block.text

        prompt_tokens = response.usage.input_tokens
        completion_tokens = response.usage.output_tokens

        return text, prompt_tokens, completion_tokens

    def _log_usage(
        self,
        task_type: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: float,
        input_preview: str,
        output_preview: str,
        elapsed_ms: int,
    ):
        """DB에 LLM 사용량을 기록한다."""
        try:
            from core.db import CrawlDB
            db = CrawlDB()
            db.add_llm_usage(
                agent_type=self.agent_type,
                task_type=task_type,
                model=self.model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=cost_usd,
                site_id=self.site_id,
                input_preview=input_preview,
                output_preview=output_preview,
                elapsed_ms=elapsed_ms,
            )
            db.close()
        except Exception:
            pass  # 로깅 실패가 메인 로직을 중단시키면 안 됨


# ── 작업 유형(task_type) 상수 ──
# 에이전트에서 사용할 때 이 상수를 참조
TASK_TYPES = {
    "structure_detection":    "페이지 구조 분석",
    "description_summary":    "상품 설명 요약",
    "category_classification":"카테고리 자동 분류",
    "news_relevance":         "뉴스 관련성 분석",
    "news_sentiment":         "뉴스 감성 분석",
    "ocr_correction":         "OCR 결과 보정",
    "field_extraction":       "필드 추출",
    "data_cleaning":          "데이터 정제",
}
