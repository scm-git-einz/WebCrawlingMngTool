"""뉴스 키워드 입력 프롬프트 기능 테스트"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.db import CrawlDB


def test_db_keywords():
    """DB 키워드 CRUD 테스트"""
    db = CrawlDB()

    site_id = 8  # 네이버뉴스검색

    # 1. 활성 키워드 조회
    active = db.get_active_keywords(site_id)
    print(f"[1] 활성 키워드: {active}")
    assert len(active) == 6, f"Expected 6, got {len(active)}"

    # 2. 키워드 비활성화
    db.set_keyword_active(site_id, "중국", False)
    db.set_keyword_active(site_id, "세관", False)
    active2 = db.get_active_keywords(site_id)
    print(f"[2] 비활성 후: {active2}")
    assert len(active2) == 4
    assert "중국" not in active2
    assert "세관" not in active2

    # 3. 키워드 재활성화
    db.set_keyword_active(site_id, "중국", True)
    db.set_keyword_active(site_id, "세관", True)
    active3 = db.get_active_keywords(site_id)
    print(f"[3] 재활성 후: {active3}")
    assert len(active3) == 6

    # 4. 임시 키워드 추가/삭제
    db.add_keyword(site_id, "테스트키워드")
    active4 = db.get_active_keywords(site_id)
    print(f"[4] 추가 후: {active4}")
    assert "테스트키워드" in active4

    db.remove_keyword(site_id, "테스트키워드")
    active5 = db.get_active_keywords(site_id)
    print(f"[5] 삭제 후: {active5}")
    assert "테스트키워드" not in active5
    assert len(active5) == 6

    # 5. 중복 추가 테스트
    result = db.add_keyword(site_id, "환율")
    print(f"[6] 중복 추가 결과: {result}")
    assert result is None  # 이미 존재

    db.close()
    print("\n=== 모든 DB 키워드 테스트 통과 ===")


def test_resolve_keywords():
    """NewsAgent 키워드 우선순위 테스트"""
    from agents.news.engine import NewsAgent

    db = CrawlDB()
    agent = NewsAgent(db=db)
    site = db.get_site(8)
    crawl_cfg = agent.get_crawl_config(site)

    # 1. override 최우선
    result1 = agent._resolve_keywords(8, crawl_cfg, ["A", "B"])
    print(f"\n[우선순위1] CLI override: {result1}")
    assert result1 == ["A", "B"]

    # 2. DB 키워드 (override 없을 때)
    result2 = agent._resolve_keywords(8, crawl_cfg, None)
    print(f"[우선순위2] DB 키워드: {result2}")
    assert len(result2) == 6
    assert "해외여행" in result2

    # 3. 빈 override → falsy이므로 DB fallback (실제 flow에서는 cmd_run이 조기리턴)
    result3 = agent._resolve_keywords(8, crawl_cfg, [])
    print(f"[우선순위3] 빈 override → DB fallback: {result3}")
    assert len(result3) == 6  # DB 키워드로 fallback

    db.close()
    print("\n=== 모든 우선순위 테스트 통과 ===")


if __name__ == "__main__":
    test_db_keywords()
    test_resolve_keywords()
    print("\n[OK] 전체 테스트 완료")
