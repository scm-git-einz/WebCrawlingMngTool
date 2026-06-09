"""수집 대상 사이트 관리 API"""
import json
import signal
import subprocess
import sys
import os
from datetime import datetime
from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from core.db import CrawlDB

_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..")
_PYTHON = os.path.join(_ROOT, ".venv", "Scripts", "python.exe")
_LOGS_DIR = os.path.join(os.path.abspath(_ROOT), "logs")

router = APIRouter(tags=["sites"])


class SiteCreate(BaseModel):
    site_name: str
    site_url: str
    agent_type: str = "product"
    category: str = ""
    crawl_config: dict | None = None


class SiteConfigUpdate(BaseModel):
    crawl_config: dict


class SiteUpdate(BaseModel):
    site_name: str | None = None
    site_url: str | None = None
    agent_type: str | None = None
    category: str | None = None


class UrlAnalyzeRequest(BaseModel):
    url: str


def _db():
    return CrawlDB()


def _site_to_dict(row) -> dict:
    d = dict(row)
    for key in ("crawl_config", "detection", "browser"):
        if key in d and isinstance(d[key], str):
            try:
                d[key] = json.loads(d[key])
            except (json.JSONDecodeError, TypeError):
                pass
    return d


@router.get("/sites")
def list_sites():
    db = _db()
    try:
        cur = db.conn.cursor()
        cur.execute("""
            SELECT id, site_name, site_url, is_active, platform_id,
                   agent_type, crawl_config, category, crawl_schedule,
                   created_at, updated_at
            FROM crawl_sites
            ORDER BY category, site_name
        """)
        return [_site_to_dict(r) for r in cur.fetchall()]
    finally:
        db.close()


@router.get("/sites/categories")
def list_categories():
    db = _db()
    try:
        cur = db.conn.cursor()
        cur.execute("""
            SELECT category, COUNT(*) as cnt,
                   SUM(CASE WHEN is_active=1 THEN 1 ELSE 0 END) as active_cnt
            FROM crawl_sites
            GROUP BY category
            ORDER BY category
        """)
        return [dict(r) for r in cur.fetchall()]
    finally:
        db.close()


@router.get("/sites/{site_id}")
def get_site(site_id: int):
    db = _db()
    try:
        row = db.get_site(site_id)
        if not row:
            raise HTTPException(404, "사이트를 찾을 수 없습니다")
        site = _site_to_dict(row)
        site["crawl_config"] = db.get_crawl_config(site_id)
        keywords = db.get_keywords(site_id)
        site["keywords"] = [dict(k) for k in keywords]
        site["credentials"] = db.get_credentials(site_id)
        return site
    finally:
        db.close()


@router.post("/sites/analyze-url")
def analyze_url_endpoint(body: UrlAnalyzeRequest):
    """URL을 방문하여 수집 가능한 데이터를 분석한다."""
    from core.url_analyzer import analyze_url
    try:
        result = analyze_url(body.url, timeout_sec=30)
        return result
    except Exception as e:
        return {"status": "error", "error": str(e)[:200]}


@router.post("/sites")
def create_site(body: SiteCreate):
    db = _db()
    try:
        site_id = db.add_site(
            site_name=body.site_name,
            site_url=body.site_url,
            agent_type=body.agent_type,
            crawl_config=body.crawl_config,
        )
        if body.category:
            cur = db.conn.cursor()
            cur.execute(
                "UPDATE crawl_sites SET category=? WHERE id=?",
                (body.category, site_id),
            )
            db.conn.commit()
        return {"id": site_id, "message": "사이트가 추가되었습니다"}
    finally:
        db.close()


@router.put("/sites/{site_id}")
def update_site(site_id: int, body: SiteUpdate):
    db = _db()
    try:
        site = db.get_site(site_id)
        if not site:
            raise HTTPException(404, "사이트를 찾을 수 없습니다")
        cur = db.conn.cursor()
        updates = []
        params = []
        if body.site_name is not None:
            updates.append("site_name = ?")
            params.append(body.site_name)
        if body.site_url is not None:
            updates.append("site_url = ?")
            params.append(body.site_url)
        if body.agent_type is not None:
            updates.append("agent_type = ?")
            params.append(body.agent_type)
        if body.category is not None:
            updates.append("category = ?")
            params.append(body.category)
        if updates:
            updates.append("updated_at = datetime('now','localtime')")
            params.append(site_id)
            cur.execute(
                f"UPDATE crawl_sites SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            db.conn.commit()
        return {"message": "수정되었습니다"}
    finally:
        db.close()


@router.put("/sites/{site_id}/config")
def update_config(site_id: int, body: SiteConfigUpdate):
    db = _db()
    try:
        site = db.get_site(site_id)
        if not site:
            raise HTTPException(404, "사이트를 찾을 수 없습니다")
        db.update_crawl_config(site_id, body.crawl_config)
        return {"message": "설정이 수정되었습니다"}
    finally:
        db.close()


# ─── 뉴스 키워드 관리 ────────────────────────────────────────

class KeywordBody(BaseModel):
    keyword: str


@router.get("/sites/{site_id}/keywords")
def get_keywords(site_id: int):
    db = _db()
    try:
        rows = db.get_keywords(site_id)
        return [dict(r) for r in rows]
    finally:
        db.close()


@router.post("/sites/{site_id}/keywords")
def add_keyword(site_id: int, body: KeywordBody):
    db = _db()
    try:
        kw_id = db.add_keyword(site_id, body.keyword)
        if kw_id is None:
            return {"message": "이미 등록된 키워드입니다"}
        return {"id": kw_id, "message": f"'{body.keyword}' 키워드가 추가되었습니다"}
    finally:
        db.close()


@router.delete("/sites/{site_id}/keywords/{keyword}")
def remove_keyword(site_id: int, keyword: str):
    db = _db()
    try:
        ok = db.remove_keyword(site_id, keyword)
        if not ok:
            raise HTTPException(404, "키워드를 찾을 수 없습니다")
        return {"message": f"'{keyword}' 키워드가 삭제되었습니다"}
    finally:
        db.close()


# ─── 로그인 계정 관리 ────────────────────────────────────────

class CredentialBody(BaseModel):
    login_id: str
    login_pwd: str
    label: str = ""


class CredentialUpdate(BaseModel):
    login_id: str
    login_pwd: str
    label: str = ""


@router.get("/sites/{site_id}/credentials")
def get_credentials(site_id: int):
    db = _db()
    try:
        return db.get_credentials(site_id)
    finally:
        db.close()


@router.post("/sites/{site_id}/credentials")
def add_credential(site_id: int, body: CredentialBody):
    db = _db()
    try:
        site = db.get_site(site_id)
        if not site:
            raise HTTPException(404, "사이트를 찾을 수 없습니다")
        cred_id = db.add_credential(
            site_id, body.login_id, body.login_pwd, body.label,
        )
        return {"id": cred_id, "message": "계정이 추가되었습니다"}
    finally:
        db.close()


@router.put("/sites/credentials/{cred_id}")
def update_credential(cred_id: int, body: CredentialUpdate):
    db = _db()
    try:
        ok = db.update_credential(cred_id, body.login_id, body.login_pwd, body.label)
        if not ok:
            raise HTTPException(404, "계정을 찾을 수 없습니다")
        return {"message": "계정이 수정되었습니다"}
    finally:
        db.close()


@router.delete("/sites/credentials/{cred_id}")
def delete_credential(cred_id: int):
    db = _db()
    try:
        ok = db.delete_credential(cred_id)
        if not ok:
            raise HTTPException(404, "계정을 찾을 수 없습니다")
        return {"message": "계정이 삭제되었습니다"}
    finally:
        db.close()


@router.put("/sites/credentials/{cred_id}/toggle")
def toggle_credential(cred_id: int):
    db = _db()
    try:
        result = db.toggle_credential(cred_id)
        if not result:
            raise HTTPException(404, "계정을 찾을 수 없습니다")
        state = "활성화" if result["is_active"] else "비활성화"
        return {"is_active": result["is_active"], "message": f"계정이 {state}되었습니다"}
    finally:
        db.close()


# ─── 수집 주기 설정 ──────────────────────────────────────────

class ScheduleBody(BaseModel):
    schedule: str  # 'hourly' | 'daily' | 'weekly' | 'monthly' | ''


@router.put("/sites/batch/schedule")
def batch_update_schedule(body: dict):
    """여러 사이트의 수집 주기를 일괄 변경"""
    site_ids = body.get("site_ids", [])
    schedule = body.get("schedule", "")
    if not site_ids:
        raise HTTPException(400, "site_ids가 필요합니다")
    db = _db()
    try:
        cur = db.conn.cursor()
        placeholders = ",".join("?" for _ in site_ids)
        cur.execute(
            f"UPDATE crawl_sites SET crawl_schedule=?, updated_at=datetime('now','localtime') "
            f"WHERE id IN ({placeholders})",
            [schedule] + site_ids,
        )
        db.conn.commit()
        return {"message": f"{len(site_ids)}개 사이트 주기가 '{schedule}'로 설정되었습니다", "updated": len(site_ids)}
    finally:
        db.close()


@router.put("/sites/{site_id}/schedule")
def update_schedule(site_id: int, body: ScheduleBody):
    db = _db()
    try:
        site = db.get_site(site_id)
        if not site:
            raise HTTPException(404, "사이트를 찾을 수 없습니다")
        cur = db.conn.cursor()
        cur.execute(
            "UPDATE crawl_sites SET crawl_schedule=?, updated_at=datetime('now','localtime') WHERE id=?",
            (body.schedule, site_id),
        )
        db.conn.commit()
        return {"message": f"수집 주기가 '{body.schedule}'로 설정되었습니다"}
    finally:
        db.close()


# ─── 수집 실행 ──────────────────────────────────────────────

# 실행 중인 프로세스 추적 (PID → info dict)
# info에 "proc" (Popen 객체) 포함 → poll()로 정확한 종료 감지
_running_processes: dict[int, dict] = {}


def _is_process_alive(pid: int) -> bool:
    """프로세스가 실행 중인지 확인. Popen.poll() 우선, fallback으로 os.kill."""
    info = _running_processes.get(pid)
    if not info:
        return False
    proc = info.get("proc")
    if proc is not None:
        return proc.poll() is None  # None이면 아직 실행 중
    # Popen 객체 없으면 기존 방식 fallback
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _cleanup_finished(pid: int):
    """종료된 프로세스의 로그 핸들을 닫고 _running_processes에서 제거."""
    info = _running_processes.get(pid)
    if not info:
        return
    handle = info.get("log_handle")
    if handle and not handle.closed:
        handle.close()
    del _running_processes[pid]


@router.post("/crawl/run")
def run_crawl(body: dict):
    """크롤링 실행 (개별/다건)

    body: { "site_ids": [1,2,3], "use_proxy": false }
    """
    site_ids = body.get("site_ids", [])
    use_proxy = body.get("use_proxy", False)
    if not site_ids:
        raise HTTPException(400, "site_ids가 필요합니다")

    db = _db()
    results = []
    try:
        for sid in site_ids:
            site = db.get_site(sid)
            if not site:
                results.append({"site_id": sid, "status": "error", "message": "사이트 없음"})
                continue

            # 이미 실행 중인지 확인
            already = False
            for pid, info in list(_running_processes.items()):
                if info["site_id"] == sid:
                    if _is_process_alive(pid):
                        already = True
                    else:
                        _cleanup_finished(pid)

            if already:
                results.append({"site_id": sid, "status": "already_running", "message": f"{site['site_name']} 이미 실행 중"})
                continue

            # 크롤링 프로세스 시작 (로그 파일에 출력 저장)
            try:
                os.makedirs(_LOGS_DIR, exist_ok=True)
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                log_filename = f"crawl_{sid}_{ts}.log"
                log_path = os.path.join(_LOGS_DIR, log_filename)
                log_file = open(log_path, "w", encoding="utf-8", buffering=1)  # line-buffered
                env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
                cmd = [_PYTHON, "-u", "main.py", "run", "--id", str(sid)]
                if use_proxy:
                    cmd.append("--proxy")
                proc = subprocess.Popen(
                    cmd,
                    cwd=os.path.abspath(_ROOT),
                    stdin=subprocess.DEVNULL,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    env=env,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                )
                _running_processes[proc.pid] = {
                    "site_id": sid,
                    "site_name": site["site_name"],
                    "pid": proc.pid,
                    "proc": proc,  # Popen 객체 → poll()로 정확한 종료 감지
                    "log_file": log_filename,
                    "log_path": log_path,
                    "log_handle": log_file,
                    "started_at": ts,
                }
                results.append({
                    "site_id": sid,
                    "status": "started",
                    "pid": proc.pid,
                    "log_file": log_filename,
                    "message": f"{site['site_name']} 크롤링 시작 (PID: {proc.pid})",
                })
            except Exception as e:
                results.append({"site_id": sid, "status": "error", "message": str(e)})

        return {"results": results}
    finally:
        db.close()


@router.get("/crawl/status")
def crawl_status():
    """실행 중인 크롤링 프로세스 목록"""
    alive = []
    for pid, info in list(_running_processes.items()):
        if _is_process_alive(pid):
            safe = {k: v for k, v in info.items() if k not in ("log_handle", "proc")}
            alive.append(safe)
        else:
            _cleanup_finished(pid)
    return alive


@router.post("/crawl/stop")
def stop_crawl(body: dict):
    """실행 중인 크롤링 프로세스를 종료한다.

    body: { "site_ids": [1, 2, 3] }
    """
    site_ids = body.get("site_ids", [])
    if not site_ids:
        raise HTTPException(400, "site_ids가 필요합니다")

    results = []
    for sid in site_ids:
        found = False
        for pid, info in list(_running_processes.items()):
            if info["site_id"] == sid:
                found = True
                if not _is_process_alive(pid):
                    # 이미 종료됨
                    _cleanup_finished(pid)
                    results.append({
                        "site_id": sid,
                        "status": "already_stopped",
                        "message": f"{info['site_name']} 이미 종료됨",
                    })
                    break

                # 프로세스 종료 시도
                try:
                    if sys.platform == "win32":
                        subprocess.run(
                            ["taskkill", "/F", "/T", "/PID", str(pid)],
                            capture_output=True, timeout=10,
                        )
                    else:
                        os.kill(pid, signal.SIGTERM)

                    # 로그 핸들에 종료 메시지 기록
                    handle = info.get("log_handle")
                    if handle and not handle.closed:
                        try:
                            handle.write(f"\n[시스템] 사용자에 의해 크롤링이 중지되었습니다.\n")
                            handle.flush()
                        except Exception:
                            pass
                    _cleanup_finished(pid)
                    results.append({
                        "site_id": sid,
                        "status": "stopped",
                        "message": f"{info['site_name']} 크롤링 중지됨 (PID: {pid})",
                    })
                except Exception as e:
                    results.append({
                        "site_id": sid,
                        "status": "error",
                        "message": f"종료 실패: {e}",
                    })
                break

        if not found:
            results.append({
                "site_id": sid,
                "status": "not_running",
                "message": "실행 중인 크롤링이 없습니다",
            })

    return {"results": results}


@router.get("/crawl/logs/{site_id}")
def get_crawl_logs(site_id: int, tail: int = 200):
    """사이트의 최신 크롤링 로그 반환

    - 실행 중이면 현재 로그 파일을 읽음
    - 종료됐으면 가장 최근 로그 파일을 찾아 읽음
    - tail: 마지막 N줄만 반환 (기본 200)
    """
    # 1) 실행 중인 프로세스의 로그 파일 확인
    log_path = None
    is_running = False
    for pid, info in list(_running_processes.items()):
        if info["site_id"] == site_id:
            if _is_process_alive(pid):
                log_path = info.get("log_path")
                is_running = True
            else:
                log_path = info.get("log_path")
                _cleanup_finished(pid)
            break

    # 2) 실행 중인 게 없으면 가장 최근 로그 파일 찾기
    if not log_path:
        prefix = f"crawl_{site_id}_"
        candidates = sorted(
            [f for f in os.listdir(_LOGS_DIR) if f.startswith(prefix) and f.endswith(".log")],
            reverse=True,
        ) if os.path.isdir(_LOGS_DIR) else []
        if candidates:
            log_path = os.path.join(_LOGS_DIR, candidates[0])

    if not log_path or not os.path.exists(log_path):
        raise HTTPException(404, "로그 파일이 없습니다. 크롤링을 실행해 주세요.")

    # 3) 파일 읽기 (마지막 tail 줄)
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        total = len(lines)
        content = "".join(lines[-tail:]) if tail < total else "".join(lines)
        return {
            "site_id": site_id,
            "log_file": os.path.basename(log_path),
            "is_running": is_running,
            "total_lines": total,
            "showing_lines": min(tail, total),
            "content": content,
        }
    except Exception as e:
        raise HTTPException(500, f"로그 읽기 실패: {e}")


@router.get("/crawl/logs/{site_id}/raw")
def get_crawl_logs_raw(site_id: int, tail: int = 500):
    """로그를 plain text로 반환 (브라우저에서 직접 확인용)"""
    result = get_crawl_logs(site_id, tail)
    header = f"=== {result['log_file']} | {'실행 중' if result['is_running'] else '완료'} | {result['total_lines']}줄 ===\n\n"
    return PlainTextResponse(header + result["content"])


@router.put("/sites/{site_id}/toggle")
def toggle_site(site_id: int):
    db = _db()
    try:
        site = db.get_site(site_id)
        if not site:
            raise HTTPException(404, "사이트를 찾을 수 없습니다")
        if site["is_active"]:
            db.deactivate_site(site_id)
            return {"is_active": False, "message": "비활성화되었습니다"}
        else:
            db.activate_site(site_id)
            return {"is_active": True, "message": "활성화되었습니다"}
    finally:
        db.close()
