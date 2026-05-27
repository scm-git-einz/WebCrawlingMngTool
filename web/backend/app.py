"""크롤링 관리 웹 대시보드 — FastAPI 백엔드"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from web.backend.routes import sites, results, ocr

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


@app.get("/api/health")
def health():
    return {"status": "ok"}
