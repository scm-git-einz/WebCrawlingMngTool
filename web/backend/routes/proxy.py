"""프록시 관리 API"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from fastapi import APIRouter
from core.proxy_manager import get_proxy_manager

router = APIRouter(tags=["proxy"])


@router.get("/proxy/status")
def proxy_status():
    """프록시 풀 상태 조회"""
    try:
        mgr = get_proxy_manager(auto_fetch=False)
        return {
            "total": mgr.total_count,
            "available": mgr.available_count,
            "has_proxies": mgr.total_count > 0,
        }
    except Exception as e:
        return {"total": 0, "available": 0, "has_proxies": False, "error": str(e)}


@router.post("/proxy/refresh")
def proxy_refresh():
    """프록시 목록 갱신 (새로 수집 + 검증)"""
    try:
        mgr = get_proxy_manager(auto_fetch=False)
        mgr.refresh()
        return {
            "status": "ok",
            "total": mgr.total_count,
            "available": mgr.available_count,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/proxy/list")
def proxy_list():
    """현재 프록시 목록 조회"""
    try:
        mgr = get_proxy_manager(auto_fetch=False)
        proxies = []
        for p in mgr._proxies:
            proxies.append({
                "server": p["server"],
                "source": p.get("source", ""),
                "protocol": p.get("protocol", "http"),
                "blacklisted": p["server"] in mgr._blacklist,
            })
        return {"proxies": proxies, "count": len(proxies)}
    except Exception as e:
        return {"proxies": [], "count": 0, "error": str(e)}
