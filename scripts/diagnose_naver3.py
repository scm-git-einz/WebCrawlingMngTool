"""네이버 스마트스토어 심층 진단 3 - 페이지 로딩/렌더링 문제"""
import sys
import json
sys.path.insert(0, "D:\\crawling")

from core.browser import BrowserManager
from core.network_interceptor import NetworkInterceptor

bm = BrowserManager()
interceptor = NetworkInterceptor()
page = bm.create()
interceptor.start(page)

url = "https://brand.naver.com/esteelauder"
print(f"[diag] Loading: {url}")

# networkidle 대신 domcontentloaded + 긴 대기
resp = page.goto(url, wait_until="domcontentloaded", timeout=60000)
print(f"[diag] Response status: {resp.status if resp else 'None'}")
print(f"[diag] Response headers:")
if resp:
    for k, v in list(resp.headers.items())[:15]:
        print(f"  {k}: {v[:100]}")

page.wait_for_timeout(8000)

# 스크롤 트리거
for i in range(5):
    page.evaluate("window.scrollBy(0, window.innerHeight)")
    page.wait_for_timeout(1000)

# 추가 대기
page.wait_for_timeout(3000)

interceptor.stop(page)

# 1) HTML 길이와 주요 내용
html_len = page.evaluate("() => document.documentElement.outerHTML.length")
body_len = page.evaluate("() => (document.body.innerHTML || '').length")
print(f"\n[diag] HTML length: {html_len}, Body innerHTML length: {body_len}")

# 2) iframe 확인
iframes = page.evaluate("""() => {
    var frames = document.querySelectorAll('iframe');
    var result = [];
    for (var i = 0; i < frames.length; i++) {
        result.push({
            src: frames[i].src || '',
            id: frames[i].id || '',
            name: frames[i].name || '',
            width: frames[i].width || '',
            height: frames[i].height || '',
        });
    }
    return result;
}""")
print(f"\n[diag] Iframes: {len(iframes)}")
for f in iframes[:5]:
    print(f"  src={f['src'][:100]}, id={f['id']}, name={f['name']}")

# 3) 네트워크 캡처 결과
captured = list(interceptor.captured)
print(f"\n[diag] Captured network requests: {len(captured)}")
for req in captured[:20]:
    url_short = req.get("url", "")[:120]
    status = req.get("status", "")
    content_type = req.get("content_type", "")
    body_len_cap = len(req.get("body", "")) if req.get("body") else 0
    print(f"  [{status}] {content_type[:30]:30s} body={body_len_cap:>8} {url_short}")

# 4) 실제 body 내 텍스트
body_text = page.evaluate("() => (document.body.innerText || '').substring(0, 2000)")
print(f"\n[diag] Body text (first 2000 chars):")
# Windows-safe print
try:
    print(body_text[:2000])
except:
    print(body_text.encode('ascii', errors='replace').decode('ascii')[:2000])

# 5) 주요 DOM 구조 확인
dom_structure = page.evaluate("""() => {
    var body = document.body;
    if (!body) return 'no body';
    var children = body.children;
    var result = [];
    for (var i = 0; i < children.length && i < 20; i++) {
        var el = children[i];
        var childCount = el.querySelectorAll('*').length;
        result.push({
            tag: el.tagName,
            id: el.id || '',
            cls: (el.className || '').toString().substring(0, 80),
            childCount: childCount,
            textLen: (el.innerText || '').length,
        });
    }
    return result;
}""")
print(f"\n[diag] Body direct children:")
for el in dom_structure:
    print(f"  <{el['tag']} id='{el['id']}' class='{el['cls']}'> children={el['childCount']}, text={el['textLen']}")

# 6) 현재 URL (리다이렉트 확인)
print(f"\n[diag] Final URL: {page.url}")
print(f"[diag] Title: {page.title()}")

bm.close()
print("\n[diag] Done")
