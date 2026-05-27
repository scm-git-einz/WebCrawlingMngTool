"""Upstage Document Parse API 테스트 - OCR과 비교"""
import sys, io, os, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from dotenv import load_dotenv
load_dotenv(os.path.join("D:\\crawling", ".env"))

import requests

UPSTAGE_API_KEY = os.environ.get("UPSTAGE_API_KEY", "")
image_path = "scripts/test_images/post_885130_img1.png"

print(f"이미지: {image_path} ({os.path.getsize(image_path):,} bytes)")

# Document Parse API 호출
url = "https://api.upstage.ai/v1/document-digitization"
headers = {"Authorization": f"Bearer {UPSTAGE_API_KEY}"}

with open(image_path, "rb") as f:
    files = {"document": (os.path.basename(image_path), f, "image/png")}
    data = {
        "model": "document-parse",
        "output_formats": '["html", "text"]',
    }
    print("\nDocument Parse API 호출 중...")
    resp = requests.post(url, headers=headers, files=files, data=data, timeout=120)

print(f"응답 코드: {resp.status_code}")

if resp.status_code == 200:
    result = resp.json()
    print(f"응답 키: {list(result.keys())}")

    # text 출력
    if "text" in result:
        print(f"\n=== text ({len(result['text'])}자) ===")
        print(result["text"][:2000])

    # HTML content 확인
    if "content" in result:
        content = result["content"]
        if isinstance(content, dict):
            print(f"\ncontent 키: {list(content.keys())}")
            if "html" in content:
                print(f"\n=== HTML ({len(content['html'])}자) ===")
                print(content["html"][:2000])
            if "text" in content:
                print(f"\n=== Content Text ({len(content['text'])}자) ===")
                print(content["text"][:2000])
        elif isinstance(content, str):
            print(f"\n=== content ({len(content)}자) ===")
            print(content[:2000])

    # pages 확인
    if "pages" in result:
        pages = result["pages"]
        print(f"\n페이지 수: {len(pages)}")
        for pi, page in enumerate(pages):
            print(f"\n--- 페이지 {pi+1} 키: {list(page.keys())} ---")
            if "content" in page:
                pc = page["content"]
                if isinstance(pc, dict):
                    for k, v in pc.items():
                        print(f"\n  [{k}] ({len(str(v))}자):")
                        print(f"  {str(v)[:500]}")
                else:
                    print(f"  {str(pc)[:500]}")
            if "text" in page:
                print(f"\n  [text]: {page['text'][:500]}")

    # elements 확인
    if "elements" in result:
        elements = result["elements"]
        print(f"\n요소 수: {len(elements)}")
        for ei, elem in enumerate(elements[:15]):
            etype = elem.get("type", elem.get("category", "?"))
            etext = elem.get("text", elem.get("content", ""))
            if isinstance(etext, dict):
                etext = etext.get("text", etext.get("html", str(etext)))
            print(f"  [{ei+1}] type={etype} | {str(etext)[:120]}")

    # 전체 결과 저장
    with open("scripts/test_images/parse_result.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print("\n결과 저장: scripts/test_images/parse_result.json")
else:
    print(f"에러: {resp.text[:500]}")

print("\nDone!")
