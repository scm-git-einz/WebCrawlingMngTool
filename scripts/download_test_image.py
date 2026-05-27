"""게시글 이미지 다운로드 후 확인"""
import sys, io, json, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, "D:\\crawling")

from core.browser import BrowserManager

bm = BrowserManager()
page = bm.create()

url = "https://cafe.naver.com/ca-fe/cafes/14538121/articles/885130?fromPopular=true"
page.goto(url, wait_until="domcontentloaded", timeout=60000)
page.wait_for_timeout(5000)

# 이미지 URL 추출
images = page.evaluate(r"""() => {
    var container = document.querySelector('.se-main-container, .ContentRenderer, .article_viewer');
    if (!container) return [];
    var imgs = container.querySelectorAll('img');
    var results = [];
    for (var i = 0; i < imgs.length; i++) {
        var src = imgs[i].getAttribute('src') || '';
        var w = imgs[i].naturalWidth || imgs[i].width || 0;
        var h = imgs[i].naturalHeight || imgs[i].height || 0;
        if (w > 0 && w < 50 && h > 0 && h < 50) continue;
        results.push({src: src, w: w, h: h, alt: imgs[i].alt || ''});
    }
    return results;
}""")

print(f"이미지 수: {len(images)}")
for i, img in enumerate(images):
    print(f"[{i+1}] {img['w']}x{img['h']} | {img['src'][:120]}")

# 이미지 다운로드
import urllib.request
os.makedirs("scripts/test_images", exist_ok=True)
for i, img in enumerate(images):
    src = img['src']
    if not src.startswith('http'):
        continue
    fname = f"scripts/test_images/post_885130_img{i+1}.png"
    try:
        urllib.request.urlretrieve(src, fname)
        fsize = os.path.getsize(fname)
        print(f"  다운로드 완료: {fname} ({fsize:,} bytes)")
    except Exception as e:
        print(f"  다운로드 실패: {e}")

bm.close()
print("\nDone!")
