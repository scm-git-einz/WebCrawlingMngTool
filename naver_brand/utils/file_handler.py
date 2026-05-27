"""
JSON 파일 저장/로드 유틸리티
"""
import json
import os
from datetime import datetime

import config.settings as settings


def save_json(data: dict | list, filename: str) -> str:
    """
    data 를 OUTPUT_DIR/{filename} 에 JSON 으로 저장하고 저장 경로를 반환한다.

    - 디렉토리가 없으면 자동 생성
    - 한글 깨짐 방지 (ensure_ascii=False)
    - 보기 좋게 들여쓰기 (indent=2)
    """
    os.makedirs(settings.OUTPUT_DIR, exist_ok=True)
    filepath = os.path.join(settings.OUTPUT_DIR, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"[file] 저장 완료: {filepath}")
    return filepath


def load_json(filename: str) -> dict | list | None:
    """OUTPUT_DIR/{filename} 에서 JSON 을 읽어 반환한다. 파일이 없으면 None."""
    filepath = os.path.join(settings.OUTPUT_DIR, filename)

    if not os.path.exists(filepath):
        print(f"[file] 파일 없음: {filepath}")
        return None

    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def get_timestamp() -> str:
    """현재 시각을 ISO 형식 문자열로 반환한다."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
