"""W Concept API 응답 구조 진단"""
import sys
import json
import urllib.request

url = "https://api-display.wconcept.co.kr/display/api/v2/category/products/M33439436/001"
body = json.dumps({
    "custNo": "",
    "gender": "All",
    "sort": "WCK",
    "pageNo": 1,
    "pageSize": 5,
    "bcds": [],
    "colors": [],
    "benefits": [],
    "discounts": [],
    "status": ["01"],
    "shopCds": [],
    "domainType": "pc",
}).encode("utf-8")

req = urllib.request.Request(
    url,
    data=body,
    headers={
        "Content-Type": "application/json; charset=UTF-8",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    },
    method="POST",
)

try:
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        print("=== 응답 최상위 키 ===")
        if isinstance(data, dict):
            print(list(data.keys()))
            if "data" in data:
                d = data["data"]
                print(f"\n=== data 키 ===")
                if isinstance(d, dict):
                    print(list(d.keys()))
                    if "productList" in d:
                        pl = d["productList"]
                        print(f"\n=== productList 키 ===")
                        if isinstance(pl, dict):
                            print(list(pl.keys()))
                            content = pl.get("content", [])
                            print(f"\n=== content 길이: {len(content)} ===")
                            if content:
                                item = content[0]
                                print(f"\n=== 첫 번째 아이템 키 ===")
                                print(list(item.keys()))
                                print(f"\n=== 첫 번째 아이템 ===")
                                print(json.dumps(item, indent=2, ensure_ascii=False)[:2000])
except Exception as e:
    print(f"Error: {e}")
