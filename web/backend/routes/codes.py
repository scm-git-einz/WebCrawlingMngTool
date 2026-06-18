"""시스템 코드 관리 API"""
from fastapi import APIRouter, Query
from core.db import CrawlDB

router = APIRouter(tags=["codes"])


def _db():
    return CrawlDB()


@router.get("/codes")
def list_codes(group: str = Query("", description="그룹코드 필터 (빈값=전체)")):
    db = _db()
    try:
        rows = db.get_system_codes(group_code=group or None)
        return rows
    finally:
        db.close()


@router.get("/codes/grouped")
def grouped_codes():
    db = _db()
    try:
        rows = db.get_system_codes()
        result = {}
        for r in rows:
            g = r["group_code"]
            if g not in result:
                result[g] = []
            result[g].append(r)
        return result
    finally:
        db.close()
