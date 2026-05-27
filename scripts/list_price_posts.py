import sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
posts = json.load(open("output/9_꼬냑클럽/posts.json", "r", encoding="utf-8"))
pp = [p for p in posts if p.get("prices")]
for p in pp:
    print(f"{p['article_id']} | {p['title'][:60]} | prices={len(p['prices'])}")
