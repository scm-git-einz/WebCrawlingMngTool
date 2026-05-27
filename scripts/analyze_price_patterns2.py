"""가격 포함 게시글의 본문 패턴 분석 (15~25번)"""
import sys, io, json, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

posts = json.load(open("output/9_꼬냑클럽/posts.json", "r", encoding="utf-8"))
price_posts = [p for p in posts if p.get("prices")]

for i, p in enumerate(price_posts):
    if i < 15:
        continue
    print(f"\n{'='*60}")
    print(f"[{i+1}] {p['title'][:80]}")
    print(f"  prices: {p['prices'][:6]}")

    body = p.get("body", "")
    lines = body.split("\n")

    print(f"\n  --- 가격이 포함된 줄 (전후 1줄 포함) ---")
    for j, line in enumerate(lines):
        line_stripped = line.strip()
        if re.search(r'\d{1,3}(?:,\d{3})+\s*원|\d{1,3}(?:,\d{3})+', line_stripped):
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
