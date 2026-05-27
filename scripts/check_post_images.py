"""게시글 885130의 이미지 정보 확인"""
import sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

posts = json.load(open("output/9_꼬냑클럽/posts.json", "r", encoding="utf-8"))
post = next((p for p in posts if p["article_id"] == "885130"), None)

if post:
    print(f"제목: {post['title']}")
    print(f"본문 일부:\n{post.get('body', '')[:500]}")
    print(f"\n이미지 수: {len(post.get('images', []))}")
    for i, img in enumerate(post.get('images', []), 1):
        print(f"  [{i}] src: {img['src'][:120]}")
        print(f"       alt: {img.get('alt', '')}")
    print(f"\nprices: {post.get('prices', [])}")
else:
    print("게시글 없음")
