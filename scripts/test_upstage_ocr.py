"""Upstage OCR API 테스트 - 게시글 이미지에서 상품명/가격 추출"""
import sys, io, os, json, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, "D:\\crawling")

from dotenv import load_dotenv
load_dotenv(os.path.join("D:\\crawling", ".env"))

UPSTAGE_API_KEY = os.environ.get("UPSTAGE_API_KEY", "")
if not UPSTAGE_API_KEY:
    print("ERROR: UPSTAGE_API_KEY 환경변수가 설정되지 않았습니다.")
    print("  .env 파일에 UPSTAGE_API_KEY=your-key 를 추가하세요.")
    sys.exit(1)

print(f"API Key: {UPSTAGE_API_KEY[:8]}...{UPSTAGE_API_KEY[-4:]}")

import requests

# 1. 이미지 파일로 OCR 호출
image_path = "scripts/test_images/post_885130_img1.png"
print(f"\n이미지: {image_path} ({os.path.getsize(image_path):,} bytes)")

url = "https://api.upstage.ai/v1/document-digitization"
headers = {
    "Authorization": f"Bearer {UPSTAGE_API_KEY}",
}

with open(image_path, "rb") as f:
    files = {"document": (os.path.basename(image_path), f, "image/png")}
    data = {"model": "ocr"}
    print("\nUpstage OCR API 호출 중...")
    resp = requests.post(url, headers=headers, files=files, data=data, timeout=60)

print(f"응답 코드: {resp.status_code}")

if resp.status_code == 200:
    result = resp.json()

    # 전체 응답 구조 확인
    print(f"\n응답 키: {list(result.keys())}")

    # 텍스트 추출
    if "text" in result:
        ocr_text = result["text"]
        print(f"\n=== OCR 추출 텍스트 ===\n{ocr_text}")
    elif "pages" in result:
        print(f"\n페이지 수: {len(result['pages'])}")
        for pi, page in enumerate(result["pages"]):
            print(f"\n--- 페이지 {pi+1} ---")
            if "text" in page:
                print(page["text"])
            elif "words" in page:
                words = [w.get("text", "") for w in page["words"]]
                print(" ".join(words))
    else:
        # 전체 응답 출력 (구조 파악)
        print(f"\n=== 전체 응답 ===")
        print(json.dumps(result, ensure_ascii=False, indent=2)[:3000])

    # 결과 저장
    with open("scripts/test_images/ocr_result.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print("\n결과 저장: scripts/test_images/ocr_result.json")
else:
    print(f"에러: {resp.text[:500]}")

print("\nDone!")
