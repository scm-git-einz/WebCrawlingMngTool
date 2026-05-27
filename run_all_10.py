"""
전체 사이트 10건 제한 수집 실행 스크립트

모든 등록 사이트에 대해 10건씩만 데이터를 추출한다.
- Product: max_detail_pages=10
- News: max_articles_per_keyword=10, max_articles=10
- Cafe: max_pages=2 (약 10건 내외)

각 사이트를 별도 스레드에서 실행 (스레드별 독립 DB 연결).
타임아웃 초과 시 브라우저 강제 종료 후 다음 사이트로 진행.

사용법:
  python run_all_10.py
"""
import json
import os
import sys
import time
import traceback
import threading

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from core.db import CrawlDB
from agents import get_agent

# ─── 에이전트별 10건 제한 설정 ─────────────────────────────
LIMIT_CONFIGS = {
    "product": {
        "product_limit_type": "n",
        "product_limit_count": 10,
        "crawl_mode": "single",
    },
    "news": {
        "max_articles_per_keyword": 10,
        "max_articles": 10,
        "collect_body": False,
    },
    "cafe": {
        "max_pages": 2,
        "collect_body": True,
        "collect_links": True,
        "collect_images": False,
        "collect_ocr": False,
    },
}

# 사이트별 타임아웃 (초)
SITE_TIMEOUT = {
    "product": 300,
    "news": 180,
    "cafe": 600,
}

BACKUP_FILE = os.path.join(BASE_DIR, "data", "_config_backup.json")


def log(msg):
    """즉시 플러시되는 로그 출력"""
    print(msg, flush=True)


def backup_configs(db, sites):
    """기존 crawl_config를 JSON 파일로 백업한다."""
    backup = {}
    for site in sites:
        site_id = site["id"]
        existing = db.get_crawl_config(site_id)
        backup[str(site_id)] = dict(existing) if existing else {}

    os.makedirs(os.path.dirname(BACKUP_FILE), exist_ok=True)
    with open(BACKUP_FILE, "w", encoding="utf-8") as f:
        json.dump(backup, f, ensure_ascii=False, indent=2)

    log(f"[backup] {len(backup)}개 사이트 config 백업 -> {BACKUP_FILE}")
    return backup


def restore_configs(db, backup):
    """백업된 config를 DB로 복원한다."""
    count = 0
    for site_id_str, cfg in backup.items():
        try:
            db.update_crawl_config(int(site_id_str), cfg)
            count += 1
        except Exception as e:
            log(f"  [WARN] site_id={site_id_str} config 복원 실패: {e}")
    log(f"[restore] {count}개 사이트 config 복원 완료")


def restore_from_file(db):
    """백업 파일에서 config를 복원한다 (크래시 복구용)."""
    if not os.path.exists(BACKUP_FILE):
        log("[restore] 백업 파일 없음, 복원 스킵")
        return False
    with open(BACKUP_FILE, "r", encoding="utf-8") as f:
        backup = json.load(f)
    restore_configs(db, backup)
    os.remove(BACKUP_FILE)
    log("[restore] 백업 파일 삭제 완료")
    return True


def apply_limits(db, sites):
    """10건 제한 config를 적용한다."""
    for site in sites:
        site_id = site["id"]
        agent_type = site["agent_type"] or "product"
        existing = db.get_crawl_config(site_id)
        limit_cfg = LIMIT_CONFIGS.get(agent_type, LIMIT_CONFIGS["product"])
        merged = {**existing, **limit_cfg}
        db.update_crawl_config(site_id, merged)
    log(f"[config] {len(sites)}개 사이트에 10건 제한 적용 완료")


def run_site_with_timeout(site_id, agent_type, timeout_sec):
    """사이트를 별도 스레드에서 실행한다.

    스레드 내부에서 독립 CrawlDB 연결을 생성하여 SQLite 스레드 제약을 회피.

    Returns:
        (success: bool, error_msg: str or None)
    """
    result = {"success": False, "error": None}
    agent_ref = {"agent": None}

    def _run():
        thread_db = None
        try:
            thread_db = CrawlDB()
            agent = get_agent(agent_type, db=thread_db)
            agent_ref["agent"] = agent
            agent.run_site(site_id)
            result["success"] = True
        except Exception as e:
            result["error"] = str(e)
            traceback.print_exc()
        finally:
            if thread_db:
                try:
                    thread_db.close()
                except Exception:
                    pass

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    thread.join(timeout=timeout_sec)

    if thread.is_alive():
        # 타임아웃 — 브라우저 강제 종료 시도
        log(f"  [TIMEOUT] {timeout_sec}s 초과 - 브라우저 정리 중...")
        agent = agent_ref.get("agent")
        if agent:
            try:
                if hasattr(agent, 'browser_mgr'):
                    agent.browser_mgr.close()
                if hasattr(agent, 'page'):
                    agent.page = None
            except Exception:
                pass
        return False, f"TIMEOUT ({timeout_sec}s)"

    if result["success"]:
        return True, None
    else:
        return False, result["error"]


def main():
    db = CrawlDB()

    try:
        # 이전 크래시 백업 파일 확인
        if os.path.exists(BACKUP_FILE):
            log("[!] 이전 실행의 미복원 백업 파일 발견 -> 먼저 복원합니다")
            restore_from_file(db)

        # 활성 사이트 조회
        cur = db.conn.cursor()
        cur.execute("""
            SELECT id, site_name, site_url, agent_type, crawl_config
            FROM crawl_sites
            WHERE is_active = 1
            ORDER BY agent_type, id
        """)
        sites = [dict(r) for r in cur.fetchall()]

        log(f"\n{'='*60}")
        log(f"  전체 사이트 10건 제한 수집 시작")
        log(f"  대상: {len(sites)}개 사이트")
        log(f"  실행 방식: in-process (스레드별 독립 DB + 타임아웃)")
        log(f"{'='*60}\n")

        # 1단계: config 백업 (파일) + 10건 제한 적용
        backup = backup_configs(db, sites)
        apply_limits(db, sites)

        # 메인 DB 닫기 (이후 각 스레드가 독립 DB 사용)
        db.close()

        # 2단계: 사이트별 순차 실행
        results = {"success": [], "failed": [], "timeout": []}
        total_start = time.time()

        for i, site in enumerate(sites, 1):
            site_id = site["id"]
            site_name = site["site_name"]
            agent_type = site["agent_type"] or "product"
            timeout = SITE_TIMEOUT.get(agent_type, 300)

            log(f"\n{'---':->60}")
            log(f"  [{i}/{len(sites)}] {site_name}")
            log(f"  유형: {agent_type} | 타임아웃: {timeout}s")
            log(f"  URL: {site['site_url'][:60]}")
            log(f"{'---':->60}")

            start = time.time()

            try:
                success, error = run_site_with_timeout(
                    site_id, agent_type, timeout,
                )
                elapsed = time.time() - start

                if success:
                    results["success"].append((site_name, elapsed))
                    log(f"  [OK] {site_name} ({elapsed:.0f}s)")
                elif error and error.startswith("TIMEOUT"):
                    results["timeout"].append((site_name, timeout))
                    log(f"  [TIMEOUT] {site_name} ({timeout}s 초과)")
                else:
                    results["failed"].append((site_name, error or "unknown"))
                    log(f"  [FAIL] {site_name} ({elapsed:.0f}s): {(error or 'unknown')[:80]}")

            except Exception as e:
                elapsed = time.time() - start
                results["failed"].append((site_name, str(e)))
                log(f"  [FAIL] {site_name} ({elapsed:.0f}s): {e}")
                traceback.print_exc()

        total_elapsed = time.time() - total_start

        # 3단계: config 복원 (새 DB 연결)
        db = CrawlDB()
        log(f"\n[restore] 원래 crawl_config 복원 중...")
        restore_configs(db, backup)

        # 백업 파일 삭제
        if os.path.exists(BACKUP_FILE):
            os.remove(BACKUP_FILE)
            log("[restore] 백업 파일 삭제 완료")

        # 결과 요약
        log(f"\n{'='*60}")
        log(f"  수집 결과 요약 (총 {total_elapsed:.0f}초)")
        log(f"{'='*60}")
        log(f"  성공: {len(results['success'])}개")
        for name, sec in results["success"]:
            log(f"    [OK] {name} ({sec:.0f}s)")
        if results["timeout"]:
            log(f"  타임아웃: {len(results['timeout'])}개")
            for name, sec in results["timeout"]:
                log(f"    [TIMEOUT] {name} ({sec}s)")
        if results["failed"]:
            log(f"  실패: {len(results['failed'])}개")
            for name, err in results["failed"]:
                log(f"    [FAIL] {name}: {err[:80]}")
        log(f"{'='*60}\n")

        db.close()

    except KeyboardInterrupt:
        log("\n\n[!] 사용자에 의해 중단되었습니다.")
        log("[restore] 백업 파일에서 config 복원 시도...")
        try:
            restore_db = CrawlDB()
            restore_from_file(restore_db)
            restore_db.close()
        except Exception:
            pass

    except Exception as e:
        log(f"\n[!] 예상치 못한 오류: {e}")
        traceback.print_exc()
        log("[restore] 백업 파일에서 config 복원 시도...")
        try:
            restore_db = CrawlDB()
            restore_from_file(restore_db)
            restore_db.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
