"""크롤링 관리 웹 대시보드 — FastAPI 백엔드"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
except ImportError:
    pass

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from web.backend.routes import sites, results, ocr, proxy, llm, logs, failures, codes

app = FastAPI(title="크롤링 관리 대시보드", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sites.router, prefix="/api")
app.include_router(results.router, prefix="/api")
app.include_router(ocr.router, prefix="/api")
app.include_router(proxy.router, prefix="/api")
app.include_router(llm.router, prefix="/api")
app.include_router(logs.router, prefix="/api")
app.include_router(failures.router)
app.include_router(codes.router, prefix="/api")


@app.on_event("startup")
def _cleanup_stale_running():
    """서버 시작 시 이전 세션에서 남은 running 상태를 stopped로 정리한다."""
    try:
        from core.db import CrawlDB
        db = CrawlDB()
        changed = db.mark_running_as_stopped()
        db.close()
        if changed:
            print(f"[startup] 잔여 running 상태 {changed}건 → stopped 전환")
    except Exception as e:
        print(f"[startup] running 상태 정리 실패: {e}")


@app.get("/api/health")
def health():
    return {"status": "ok"}
