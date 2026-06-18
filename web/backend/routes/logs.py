"""로그 모니터링 API"""
import os
import re
from datetime import datetime
from fastapi import APIRouter, HTTPException
from core.db import CrawlDB

_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..")
_LOGS_DIR = os.path.join(os.path.abspath(_ROOT), "logs")

router = APIRouter(tags=["logs"])


def _db():
    return CrawlDB()


# ── 로그 라인 파싱 ──

_LINE_RE = re.compile(
    r"(?:\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]\s*)?\[(\w+)\]\s*(.*)"
)

# 단계 감지: (regex_pattern, phase_id, default_label, mergeable)
_PHASE_RULES = [
    (re.compile(r"^={5,}"),                    "separator",       None,              True),
    (re.compile(r"수집 시작:|배너 수집 시작:|목록 수집 시작:|주문서 수집:"),
                                               "init",            None,              False),
    (re.compile(r"^브라우저 시작|^Stealth Chromium"),
                                               "browser_init",    "브라우저 초기화",   True),
    (re.compile(r"^쿠키 로드|^브라우저 준비"),    "browser_init",    "브라우저 초기화",   True),
    (re.compile(r"로그인 페이지|로그인 시도|로그인 성공|로그인 상태"),
                                               "login",           "로그인 처리",       True),
    (re.compile(r"탐지 결과:|탐지된 배너|카테고리 탭|DOM 탐지:"),
                                               "detection",       None,              False),
    (re.compile(r"네트워크 요청.*캡처"),          "detection",       None,              True),
    (re.compile(r"^스크롤 \d+:"),               "scroll",          "페이지 스크롤",     True),
    (re.compile(r"^더보기:"),                    "pagination",      "더보기 로딩",       True),
    (re.compile(r"상세 수집 대상:"),              "detail_start",    None,              False),
    (re.compile(r"^--- \[\d+/\d+\]"),           "item_progress",   None,              False),
    (re.compile(r"^\[\d+/\d+\]"),               "detail_progress", "상세 수집 진행",    True),
    (re.compile(r"상세 수집 완료"),               "detail_done",     "상세 수집 완료",    False),
    (re.compile(r"상품 코드.*순회 시작"),          "item_start",      None,              False),
    (re.compile(r"이벤트 쿠폰.*건너뜀"),          "coupon_skip",     "이벤트 쿠폰 건너뜀", False),
    (re.compile(r"파일 저장:|결과 저장:"),         "save",            None,              False),
    (re.compile(r"수집 완료:|배너 수집 완료:|목록 수집 완료:"),
                                               "complete",        None,              False),
    (re.compile(r"^쿠키 저장|^브라우저 종료"),     "browser_close",   "브라우저 종료",     True),
    (re.compile(r"^\[시스템\]"),                 "system",          None,              False),
]

_DEFAULT_EXPANDED = {
    "init", "detection", "detail_start", "detail_done",
    "save", "complete", "system", "header", "item_start",
}


def _detect_phase(agent_type: str | None, message: str):
    """메시지에서 단계를 감지. (phase, label, mergeable) 또는 None."""
    text = message.strip()
    if not text:
        return None

    for pattern, phase, default_label, mergeable in _PHASE_RULES:
        if pattern.search(text):
            label = default_label or text[:80]
            return phase, label, mergeable
    return None


def parse_log_sections(lines: list[str]) -> list[dict]:
    """텍스트 로그 라인을 단계별 섹션으로 파싱."""
    sections = []
    current = None

    def _flush():
        if current:
            current["agent_types"] = sorted(current["agent_types"])
            current["line_count"] = len(current["lines"])
            current["default_expanded"] = current["phase"] in _DEFAULT_EXPANDED
            sections.append(current)

    for i, raw_line in enumerate(lines):
        stripped = raw_line.rstrip("\n\r")
        m = _LINE_RE.match(stripped)
        if m:
            timestamp, agent_type, message = m.group(1), m.group(2), m.group(3)
        else:
            # --- [1/5] 같은 패턴 (agent 접두사 없는 라인)
            agent_type = None
            message = stripped
            timestamp = None

        detected = _detect_phase(agent_type, message)

        if detected:
            phase, label, mergeable = detected
            # separator는 독립 섹션으로 만들지 않고 다음 섹션에 병합
            if phase == "separator":
                if current:
                    current["lines"].append(stripped)
                continue

            # 병합 가능한 phase이고 현재 섹션과 같은 phase면 병합
            if mergeable and current and current["phase"] == phase:
                current["lines"].append(stripped)
                if agent_type:
                    current["agent_types"].add(agent_type)
                continue

            # 새 섹션 시작
            _flush()
            current = {
                "id": len(sections),
                "phase": phase,
                "label": label,
                "start_line": i,
                "lines": [stripped],
                "agent_types": {agent_type} if agent_type else set(),
            }
        else:
            # phase 감지 안 됨 — 현재 섹션에 추가
            if current is None:
                current = {
                    "id": 0,
                    "phase": "init",
                    "label": "시작",
                    "start_line": 0,
                    "lines": [],
                    "agent_types": set(),
                }
            current["lines"].append(stripped)
            if agent_type:
                current["agent_types"].add(agent_type)

    _flush()
    return sections


# ── 헬퍼 ──

def _parse_filename(fname: str):
    """crawl_{site_id}_{YYYYMMDD_HHMMSS}.log 에서 site_id, 시작 시각 추출."""
    m = re.match(r"crawl_(\d+)_(\d{8}_\d{6})\.log$", fname)
    if not m:
        return None, None
    site_id = int(m.group(1))
    try:
        started_at = datetime.strptime(m.group(2), "%Y%m%d_%H%M%S").strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    except ValueError:
        started_at = m.group(2)
    return site_id, started_at


def _get_running_processes():
    """sites.py의 _running_processes를 임포트."""
    try:
        from web.backend.routes.sites import _running_processes, _is_process_alive, _cleanup_finished
        return _running_processes, _is_process_alive, _cleanup_finished
    except ImportError:
        return {}, lambda pid: False, lambda pid: None


def _is_file_running(filename: str) -> bool:
    procs, is_alive, cleanup = _get_running_processes()
    for pid, info in list(procs.items()):
        if info.get("log_file") == filename:
            if is_alive(pid):
                return True
            else:
                cleanup(pid)
    return False


# ── API 엔드포인트 ──

@router.get("/logs/files")
def list_log_files(agent_type: str = "", site_id: int = 0, limit: int = 50):
    """로그 파일 목록 조회 (최신순)."""
    if not os.path.isdir(_LOGS_DIR):
        return []

    files = sorted(
        [f for f in os.listdir(_LOGS_DIR) if f.startswith("crawl_") and f.endswith(".log")],
        reverse=True,
    )

    # site 메타데이터 조인
    db = _db()
    try:
        sites_map = {}
        cur = db._cur()
        cur.execute("SELECT id, site_name, agent_type FROM crawl_sites")
        for row in cur.fetchall():
            sites_map[row["id"]] = row

        result = []
        for fname in files:
            sid, started_at = _parse_filename(fname)
            if sid is None:
                continue
            if site_id and sid != site_id:
                continue

            site_info = sites_map.get(sid, {})
            at = site_info.get("agent_type", "")
            if agent_type and at != agent_type:
                continue

            fpath = os.path.join(_LOGS_DIR, fname)
            result.append({
                "filename": fname,
                "site_id": sid,
                "site_name": site_info.get("site_name", f"사이트#{sid}"),
                "agent_type": at,
                "started_at": started_at,
                "is_running": _is_file_running(fname),
                "file_size": os.path.getsize(fpath),
            })
            if len(result) >= limit:
                break

        return result
    finally:
        db.close()


@router.get("/logs/files/{filename}")
def get_log_file(filename: str, tail: int = 1000):
    """특정 로그 파일의 파싱된 내용 반환."""
    # 보안: 경로 순회 방지
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(400, "잘못된 파일명")

    fpath = os.path.join(_LOGS_DIR, filename)
    if not os.path.exists(fpath):
        raise HTTPException(404, "로그 파일 없음")

    sid, started_at = _parse_filename(filename)

    # 사이트 메타데이터
    site_name = f"사이트#{sid}" if sid else ""
    at = ""
    if sid:
        db = _db()
        try:
            site = db.get_site(sid)
            if site:
                site_name = site["site_name"]
                at = site.get("agent_type", "")
        finally:
            db.close()

    # 파일 읽기
    with open(fpath, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    total = len(lines)
    target_lines = lines[-tail:] if tail < total else lines

    sections = parse_log_sections(target_lines)

    return {
        "filename": filename,
        "site_id": sid,
        "site_name": site_name,
        "agent_type": at,
        "started_at": started_at,
        "is_running": _is_file_running(filename),
        "total_lines": total,
        "sections": sections,
    }


@router.get("/logs/running")
def list_running_logs():
    """실행 중인 크롤링의 로그 미리보기."""
    procs, is_alive, cleanup = _get_running_processes()
    result = []

    for pid, info in list(procs.items()):
        if not is_alive(pid):
            cleanup(pid)
            continue

        preview_lines = []
        log_path = info.get("log_path", "")
        if log_path and os.path.exists(log_path):
            try:
                with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                    all_lines = f.readlines()
                preview_lines = [l.rstrip("\n\r") for l in all_lines[-10:]]
            except Exception:
                pass

        result.append({
            "site_id": info["site_id"],
            "site_name": info.get("site_name", ""),
            "pid": pid,
            "log_file": info.get("log_file", ""),
            "started_at": info.get("started_at", ""),
            "preview_lines": preview_lines,
        })

    return result
