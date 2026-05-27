"""29CM API 응답 구조 진단"""
import sys
import json
import urllib.request

url = "https://display-bff-api.29cm.co.kr/api/v1/plp/best/items"
body = json.dumps({
    "pageRequest": {"page": 1, "size": 3},
    "userSegment": {"gender": "F", "age": "THIRTIES"},
    "facets": {
        "periodFacetInput": {"type": "HOURLY", "order": "DESC"},
        "rankingFacetInput": {"type": "POPULARITY"},
    },
}).encode("utf-8")

req = urllib.request.Request(
    url,
    data=body,
    headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
    method="POST",
)

try:
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        print("=== 응답 최상위 키 ===")
        print(list(data.keys()) if isinstance(data, dict) else type(data))

        if isinstance(data, dict) and "data" in data:
            d = data["data"]
            print(f"\n=== data 키 ===")
            print(list(d.keys()) if isinstance(d, dict) else type(d))

            if isinstance(d, dict) and "list" in d:
                items = d["list"]
                print(f"\n=== list 길이: {len(items)} ===")
                if items:
                    item = items[0]
                    print(f"\n=== 첫 번째 아이템 키 ===")
                    print(list(item.keys()) if isinstance(item, dict) else type(item))
                    print(f"\n=== 첫 번째 아이템 전체 ===")
                    print(json.dumps(item, indent=2, ensure_ascii=False)[:2000])
except Exception as e:
    print(f"Error: {e}")
