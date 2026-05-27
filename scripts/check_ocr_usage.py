"""OCR 사용 이력 조회 스크립트"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, "D:\\crawling")
from core.db import CrawlDB

db = CrawlDB()

# 1. 엔진별 요약
print("=" * 70)
print("  OCR 사용 이력 요약 (Site 9)")
print("=" * 70)

summary = db.get_ocr_usage_summary(site_id=9)
if not summary:
    print("  이력 없음")
else:
    for s in summary:
        print(f"\n  [{s['engine']}]")
        print(f"    총 호출:       {s['total']}회")
        print(f"    성공:          {s['success_count']}회")
        print(f"    실패:          {s['fail_count']}회")
        print(f"    Rate Limit:    {s['rate_limit_count']}회")
        print(f"    총 텍스트:     {s['total_text_length']:,}자")
        print(f"    총 가격 추출:  {s['total_price_count']}건")
        print(f"    평균 처리시간: {s['avg_elapsed_ms']}ms")
        print(f"    최초 사용:     {s['first_used']}")
        print(f"    최종 사용:     {s['last_used']}")

# 2. 상세 이력 (최근 20건)
print(f"\n{'=' * 70}")
print("  최근 이력 (20건)")
print("=" * 70)

details = db.get_ocr_usage_detail(site_id=9, limit=20)
for d in details:
    engine = d['engine'][:12]
    status = d['status'][:10]
    tlen = d['text_length']
    pc = d['price_count']
    ms = d['elapsed_ms']
    err = d.get('error_msg', '')[:40] if d.get('error_msg') else ''
    url_short = d.get('image_url', '')[:50]
    print(f"  {engine:12s} | {status:10s} | "
          f"text={tlen:5d} | prices={pc:3d} | "
          f"{ms:5d}ms | {err or url_short}")

db.close()
print("\nDone!")
