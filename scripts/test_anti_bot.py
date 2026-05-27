"""봇 차단 대응 로직 단위 테스트"""
import sys
sys.path.insert(0, "D:\\crawling")

from core.base_agent import (
    _extract_domain, _record_rate_limit, _record_success,
    _rate_limit_state, ADAPTIVE_BACKOFF, HUMAN_BEHAVIOR,
)
from agents.product.engine import ProductAgent

print("=== 봇 차단 대응 로직 테스트 ===\n")

# 1. 도메인 추출
print("1. 도메인 추출:", end=" ")
assert _extract_domain("https://brand.naver.com/test") == "brand.naver.com"
assert _extract_domain("https://www.musinsa.com/main") == "www.musinsa.com"
assert _extract_domain("invalid") == "unknown"
print("OK")

# 2. 레이트 리밋 상태 관리
print("2. 레이트 리밋 상태:", end=" ")
_rate_limit_state.clear()
_record_rate_limit("test.com")
assert _rate_limit_state["test.com"]["consecutive_429"] == 1
assert _rate_limit_state["test.com"]["total_429"] == 1
_record_rate_limit("test.com")
assert _rate_limit_state["test.com"]["consecutive_429"] == 2
_record_success("test.com")
assert _rate_limit_state["test.com"]["consecutive_429"] == 0
assert _rate_limit_state["test.com"]["total_429"] == 2
print("OK")

# 3. 백오프 대기 시간 계산
print("3. 백오프 대기 시간:", end=" ")
_rate_limit_state.clear()
pa = ProductAgent.__new__(ProductAgent)

# attempt 0: ~120초 (기본)
wait0 = pa._calc_backoff_wait("new.com", 0)
assert 60 <= wait0 <= 200, f"attempt 0: {wait0:.0f}초 (범위 60~200)"

# attempt 1: ~240초 (2배)
wait1 = pa._calc_backoff_wait("new.com", 1)
assert 120 <= wait1 <= 400, f"attempt 1: {wait1:.0f}초 (범위 120~400)"

# attempt 2: ~480초 (4배, 최대 600 제한)
wait2 = pa._calc_backoff_wait("new.com", 2)
assert 200 <= wait2 <= 600, f"attempt 2: {wait2:.0f}초 (범위 200~600)"

# 연속 429 이력이 있으면 더 길게
_record_rate_limit("history.com")
_record_rate_limit("history.com")
_record_rate_limit("history.com")
wait_h = pa._calc_backoff_wait("history.com", 0)
assert wait_h > wait0 * 1.3, f"이력 반영: {wait_h:.0f} > {wait0:.0f}"

print("OK")
print(f"  attempt 0: {wait0:.0f}초")
print(f"  attempt 1: {wait1:.0f}초")
print(f"  attempt 2: {wait2:.0f}초")
print(f"  with history(3): {wait_h:.0f}초")

# 4. 쿠키 도메인 추출
print("4. 쿠키 도메인:", end=" ")
assert ProductAgent._get_cookie_domain("https://brand.naver.com/test") == "brand.naver.com"
assert ProductAgent._get_cookie_domain("https://www.musinsa.com") == "www.musinsa.com"
print("OK")

# 5. 인간형 딜레이 범위 확인
print("5. 인간형 딜레이 범위:", end=" ")
assert HUMAN_BEHAVIOR["nav_delay_mean"] == 3.5
assert HUMAN_BEHAVIOR["nav_delay_min"] >= 1.5
assert HUMAN_BEHAVIOR["nav_delay_max"] <= 8.0
print("OK")
print(f"  평균: {HUMAN_BEHAVIOR['nav_delay_mean']}초")
print(f"  범위: {HUMAN_BEHAVIOR['nav_delay_min']}~{HUMAN_BEHAVIOR['nav_delay_max']}초")

# 6. 쿠키 파일 경로
print("6. 쿠키 파일 경로:", end=" ")
from core.browser import _cookie_file_path
path = _cookie_file_path("brand.naver.com")
assert "brand_naver_com" in path
assert path.endswith(".json")
print(f"OK → {path}")

_rate_limit_state.clear()
print("\n=== 모든 테스트 통과! ===")
