"""가격 포함 게시글의 본문에서 가격-상품명 패턴 분석"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import json
import re

posts = json.load(open("output/9_꼬냑클럽/posts.json", "r", encoding="utf-8"))
price_posts = [p for p in posts if p.get("prices")]

print(f"=== 가격 포함 게시글: {len(price_posts)}개 ===\n")

for i, p in enumerate(price_posts):
    print(f"\n{'='*60}")
    print(f"[{i+1}] {p['title'][:80]}")
    print(f"  prices: {p['prices'][:6]}")

    # 가격이 포함된 줄(line) 전후 컨텍스트 분석
    body = p.get("body", "")
    lines = body.split("\n")

    print(f"\n  --- 가격이 포함된 줄 (전후 1줄 포함) ---")
    for j, line in enumerate(lines):
        line_stripped = line.strip()
        # 가격 패턴이 있는 줄 찾기
        if re.search(r'\d{1,3}(?:,\d{3})+\s*원|\d{1,3}(?:,\d{3})+', line_stripped):
            # 숫자만 있는 줄은 건너뛰기 (1000 미만)
            nums = re.findall(r'\d{1,3}(?:,\d{3})+', line_stripped)
            has_big_num = any(int(n.replace(",","")) >= 1000 for n in nums) if nums else False
            if not has_big_num:
                continue

            prev_line = lines[j-1].strip() if j > 0 else ""
            next_line = lines[j+1].strip() if j < len(lines)-1 else ""

            print(f"    L{j-1}: '{prev_line}'")
            print(f"  > L{j}:  '{line_stripped}'")
            print(f"    L{j+1}: '{next_line}'")
            print()

    if i >= 14:
        print("\n... (상위 15개만 분석)")
        break
