"""카페 크롤링 결과 요약"""
import json

with open("output/9_꼬냑클럽/posts.json", encoding="utf-8") as f:
    posts = json.load(f)

print(f"=== 꼬냑클럽 인기글 수집 결과 ({len(posts)}개) ===\n")

for i, p in enumerate(posts):
    title = p["title"][:55]
    try:
        title = title.encode("cp949", errors="replace").decode("cp949")
    except Exception:
        pass
    author = p.get("author", "")
    try:
        author = author.encode("cp949", errors="replace").decode("cp949")
    except Exception:
        pass
    category = p.get("category", "")
    try:
        category = category.encode("cp949", errors="replace").decode("cp949")
    except Exception:
        pass

    body_len = len(p.get("body", ""))
    prices = p.get("prices", [])
    prod_links = p.get("product_links", [])
    other_links = p.get("other_links", [])
    images = p.get("images", [])

    print(f"[{i+1:2d}] {title}")
    print(f"     {author} | {p.get('date','')} | {p.get('views','')}")
    print(f"     [{category}]")
    print(f"     body={body_len}chars  prices={len(prices)}  "
          f"prod_links={len(prod_links)}  images={len(images)}")
    if prices:
        sample = prices[:4]
        print(f"     prices: {sample}")
    if prod_links:
        for pl in prod_links[:2]:
            print(f"     -> {pl['url'][:80]}")
    print()

# 요약
total_body = sum(1 for p in posts if p.get("body"))
total_products = sum(1 for p in posts if p.get("prices") or p.get("product_links"))
total_prices = sum(len(p.get("prices", [])) for p in posts)
total_prod_links = sum(len(p.get("product_links", [])) for p in posts)
total_images = sum(len(p.get("images", [])) for p in posts)

print(f"{'='*50}")
print(f"Total: {len(posts)} posts, {total_body} with body")
print(f"  product info: {total_products} posts")
print(f"  prices found: {total_prices}")
print(f"  product links: {total_prod_links}")
print(f"  images: {total_images}")
