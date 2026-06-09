"""
크롤링 에이전트 통합 CLI

에이전트 타입:
  - product: 상품 크롤링 (기본)
  - news:    뉴스 기사 수집

사용법:
  python main.py add --name "에스티로더" --url "https://brand.naver.com/esteelauderkorea"
  python main.py add --name "IT뉴스" --url "https://news.example.com" --agent news
  python main.py add --name "KREAM" --url "https://kream.co.kr" \\
      --config '{"collect_details": false, "max_products": 50}'
  python main.py list
  python main.py run                     # 전체 활성 사이트 수집
  python main.py run --id 1              # 특정 사이트만 수집
  python main.py run --id 8 --keywords "해외여행,환율"  # 일회성 키워드 지정
  python main.py run --agent product     # 특정 에이전트 타입만 수집
  python main.py config --id 1 --set '{"collect_details": false}'
  python main.py result --id 1           # 최신 수집 결과 확인
  python main.py keyword list --id 8                       # 키워드 목록
  python main.py keyword add --id 8 -k "AI" -k "반도체"   # 키워드 추가
  python main.py keyword remove --id 8 -k "AI"            # 키워드 삭제
  python main.py keyword on --id 8 -k "환율"              # 키워드 활성화
  python main.py keyword off --id 8 -k "환율"             # 키워드 비활성화
  python main.py deactivate --id 1       # 사이트 비활성화
  python main.py activate --id 1         # 사이트 활성화
"""
import argparse
import json
import os
import sys

# 패키지 경로 설정
sys.path.insert(0, os.path.dirname(__file__))

# .env 파일 로드 (python-dotenv 가 있으면 사용)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
except ImportError:
    pass

from core.db import CrawlDB
from agents import get_agent, AGENT_REGISTRY


def cmd_add(args):
    """사이트 등록"""
    db = CrawlDB()
    agent_type = args.agent or "product"

    # 에이전트 타입 검증
    if agent_type not in AGENT_REGISTRY:
        print(f"알 수 없는 에이전트 타입: {agent_type}")
        print(f"사용 가능: {list(AGENT_REGISTRY.keys())}")
        db.close()
        return

    # crawl_config 파싱
    crawl_config = {}
    if args.config:
        try:
            crawl_config = json.loads(args.config)
        except json.JSONDecodeError as e:
            print(f"crawl_config JSON 파싱 오류: {e}")
            db.close()
            return

    site_id = db.add_site(
        args.name, args.url,
        agent_type=agent_type,
        crawl_config=crawl_config,
    )
    print(f"사이트 등록 완료: ID={site_id}, 이름={args.name}")
    print(f"  URL: {args.url}")
    print(f"  에이전트: {agent_type}")
    if crawl_config:
        print(f"  crawl_config: {json.dumps(crawl_config, ensure_ascii=False)}")
    db.close()


def cmd_list(args):
    """등록된 사이트 목록"""
    db = CrawlDB()
    sites = db.get_all_sites()

    if not sites:
        print("등록된 사이트가 없습니다.")
        db.close()
        return

    print(f"\n{'ID':<5} {'상태':<6} {'에이전트':<10} {'이름':<20} "
          f"{'플랫폼':<5} {'URL'}")
    print("-" * 90)
    for s in sites:
        status = "활성" if s["is_active"] else "비활성"
        platform_id = s.get("platform_id") or "-"
        agent_type = s.get("agent_type", "product")
        name = s["site_name"][:18]
        print(f"{s['id']:<5} {status:<6} {agent_type:<10} {name:<20} "
              f"{platform_id:<5} {s['site_url']}")

    # crawl_config 가 있는 사이트 표시
    has_config = [s for s in sites if s.get("crawl_config", "{}") != "{}"]
    if has_config:
        print(f"\ncrawl_config 설정된 사이트:")
        for s in has_config:
            cfg = s.get("crawl_config", "{}")
            print(f"  ID={s['id']} {s['site_name']}: {cfg}")

    # 플랫폼 목록
    platforms = db.get_all_platforms()
    if platforms:
        print(f"\n등록된 플랫폼:")
        for p in platforms:
            tmpl_count = len(db.get_templates_for_platform(p["id"]))
            print(f"  ID={p['id']} {p['display_name']} ({p['name']}) "
                  f"- 템플릿 {tmpl_count}개")

    db.close()


def _prompt_news_keywords(db, site: dict) -> list[str] | None:
    """
    뉴스 사이트 수집 전, 사용자에게 키워드 입력을 받는다.

    Returns:
        입력된 키워드 리스트 또는 None (등록된 키워드 사용)
    """
    site_id = site["id"]
    site_name = site["site_name"]

    # 등록된 활성 키워드 조회
    active_kws = db.get_active_keywords(site_id)

    print(f"\n{'─'*50}")
    print(f"  [뉴스 키워드 설정] {site_name}")
    print(f"{'─'*50}")

    if active_kws:
        kw_display = ", ".join(active_kws)
        print(f"  등록된 활성 키워드 ({len(active_kws)}개): {kw_display}")
    else:
        # crawl_config fallback 확인
        config = db.get_crawl_config(site_id)
        config_kws = config.get("search_keywords", [])
        if config_kws:
            kw_display = ", ".join(config_kws)
            print(f"  설정된 키워드 ({len(config_kws)}개): {kw_display}")
        else:
            print("  등록된 키워드 없음")

    print()
    print("  수집할 키워드를 입력하세요 (쉼표 구분):")
    print("    Enter  → 등록된 키워드 사용")
    print("    키워드  → 입력한 키워드로 수집")

    try:
        user_input = input("\n  > ")
        # BOM / 서로게이트 등 인코딩 노이즈 제거
        user_input = user_input.strip().strip("﻿").strip("\x00")
    except (EOFError, KeyboardInterrupt):
        print("\n  취소됨")
        return []  # 빈 리스트 → 수집 스킵

    if not user_input:
        # Enter → 등록된 키워드 사용 (None 반환)
        return None

    # 사용자 입력 파싱
    keywords = [k.strip() for k in user_input.split(",") if k.strip()]
    if keywords:
        kw_display = ", ".join(keywords)
        print(f"  → {len(keywords)}개 키워드로 수집: {kw_display}")
    return keywords


def cmd_run(args):
    """수집 실행"""
    db = CrawlDB()

    # --keywords 파싱 (일회성 키워드 override, 비대화형)
    override_keywords = None
    if getattr(args, "keywords", None):
        override_keywords = [
            k.strip() for k in args.keywords.split(",") if k.strip()
        ]

    use_proxy = getattr(args, "proxy", False)

    try:
        if args.id:
            # 특정 사이트 수집 → 해당 사이트의 agent_type 사용
            site = db.get_site(args.id)
            if not site:
                print(f"사이트 ID={args.id} 를 찾을 수 없습니다")
                return
            agent_type = site.get("agent_type", "product")
            agent = get_agent(agent_type, db=db)
            if use_proxy:
                agent.enable_proxy()

            if agent_type == "news":
                # DB 등록 키워드를 기본 사용. --keywords 가 있을 때만 override.
                if override_keywords:
                    agent.run_site(args.id, override_keywords=override_keywords)
                else:
                    agent.run_site(args.id)
            else:
                agent.run_site(args.id)

        elif args.agent:
            # 특정 에이전트 타입의 모든 사이트 수집
            agent = get_agent(args.agent, db=db)
            if use_proxy:
                agent.enable_proxy()
            agent.run_all()

        else:
            # 전체 활성 사이트 수집 (에이전트 타입별 그룹핑)
            sites = db.get_active_sites()
            if not sites:
                print("활성 사이트가 없습니다")
                return

            # 에이전트 타입별 분류
            by_type = {}
            for site in sites:
                at = site.get("agent_type", "product")
                by_type.setdefault(at, []).append(site)

            print(f"전체 {len(sites)}개 사이트 수집 시작")
            for at in sorted(by_type.keys()):
                print(f"\n{'='*60}")
                print(f"  에이전트: {at} ({len(by_type[at])}개 사이트)")
                print(f"{'='*60}")
                agent = get_agent(at, db=db)
                if use_proxy:
                    agent.enable_proxy()
                agent.run_all()

    finally:
        db.close()


def cmd_config(args):
    """사이트의 crawl_config 조회/수정"""
    db = CrawlDB()

    site = db.get_site(args.id)
    if not site:
        print(f"사이트 ID={args.id} 를 찾을 수 없습니다")
        db.close()
        return

    if args.reset:
        # 설정 초기화
        db.update_crawl_config(args.id, {})
        print(f"crawl_config 초기화 완료 (기본값)")
        db.close()
        return

    if args.set:
        # 설정 업데이트 (기존 설정과 병합)
        try:
            new_config = json.loads(args.set)
        except json.JSONDecodeError as e:
            print(f"JSON 파싱 오류: {e}")
            db.close()
            return

        current = db.get_crawl_config(args.id)
        current.update(new_config)
        db.update_crawl_config(args.id, current)
        print(f"crawl_config 업데이트 완료:")
        print(f"  {json.dumps(current, ensure_ascii=False, indent=2)}")
    else:
        # 현재 설정 조회
        current = db.get_crawl_config(args.id)
        print(f"사이트: {site['site_name']} (ID={args.id})")
        print(f"에이전트: {site.get('agent_type', 'product')}")
        print(f"crawl_config:")
        if current:
            print(f"  {json.dumps(current, ensure_ascii=False, indent=2)}")
        else:
            print("  (기본값 - 전체 수집)")
        print(f"\n사용 가능한 설정 키:")
        print(f"  collect_store:       매장 정보 수집 여부 (기본: true)")
        print(f"  collect_products:    상품 목록 수집 여부 (기본: true)")
        print(f"  collect_details:     상세 페이지 수집 여부 (기본: true)")
        print(f"  max_products:        최대 상품 수 (기본: 무제한)")
        print(f"  max_detail_pages:    상세 페이지 최대 수 (기본: 20)")
        print(f"  max_articles:        최대 기사 수 (뉴스, 기본: 100)")
        print(f"  collect_body:        기사 본문 수집 여부 (뉴스, 기본: true)")
        print(f"  keywords:            키워드 필터 (뉴스, 예: [\"AI\"])")

    db.close()


def cmd_result(args):
    """수집 결과 조회"""
    db = CrawlDB()
    site = db.get_site(args.id)
    if not site:
        print(f"사이트 ID={args.id} 를 찾을 수 없습니다")
        db.close()
        return

    result = db.get_latest_result(args.id)
    if not result:
        print(f"'{site['site_name']}' 의 수집 결과가 없습니다")
        db.close()
        return

    agent_type = site.get("agent_type", "product")

    print(f"\n{'='*60}")
    print(f"  사이트: {site['site_name']}")
    print(f"  URL: {site['site_url']}")
    print(f"  에이전트: {agent_type}")
    print(f"{'='*60}")
    print(f"  수집일시: {result['crawl_date']}")
    print(f"  상태: {result['status']}")
    print(f"  상품/기사 수: {result['product_count']}")
    print(f"  소요 시간: {result.get('elapsed_sec', 0):.1f}초")

    if result.get("error_msg"):
        print(f"  오류: {result['error_msg']}")

    if result.get("store_info"):
        print(f"\n  [매장/사이트 정보]")
        store = result["store_info"]
        for k, v in store.items():
            print(f"    {k}: {str(v)[:60]}")

    if result.get("products"):
        items = result["products"]
        if agent_type == "news":
            print(f"\n  [기사 목록 - 상위 5개]")
            for a in items[:5]:
                title = a.get("title", "N/A")[:50]
                date = a.get("date", "")
                has_body = "본문O" if a.get("body") else "본문X"
                print(f"    - {title} | {date} | {has_body}")
        else:
            print(f"\n  [상품 목록 - 상위 5개]")
            for p in items[:5]:
                name = p.get("product_name", "N/A")[:40]
                price = p.get("selling_price", "N/A")
                print(f"    - {name} | {price}")

    db.close()


def cmd_keyword(args):
    """뉴스 키워드 관리"""
    db = CrawlDB()

    site = db.get_site(args.id)
    if not site:
        print(f"사이트 ID={args.id} 를 찾을 수 없습니다")
        db.close()
        return

    agent_type = site.get("agent_type", "product")
    if agent_type != "news":
        print(f"키워드 관리는 news 에이전트 사이트만 지원합니다 "
              f"(현재: {agent_type})")
        db.close()
        return

    action = args.action

    if action == "list":
        # 키워드 목록 조회
        keywords = db.get_keywords(args.id)
        if not keywords:
            # crawl_config 에서 마이그레이션 가능한지 확인
            config = db.get_crawl_config(args.id)
            config_kws = config.get("search_keywords", [])
            if config_kws:
                print(f"DB 키워드 없음. crawl_config에 {len(config_kws)}개 있음:")
                for kw in config_kws:
                    print(f"  - {kw}")
                print(f"\n'keyword add' 또는 크롤링 실행 시 자동 마이그레이션됩니다.")
            else:
                print("등록된 키워드가 없습니다.")
            db.close()
            return

        print(f"\n사이트: {site['site_name']} (ID={args.id})")
        print(f"{'ID':<5} {'상태':<6} {'키워드':<30} {'등록일'}")
        print("-" * 60)
        active_count = 0
        for kw in keywords:
            status = "활성" if kw["is_active"] else "비활성"
            if kw["is_active"]:
                active_count += 1
            print(f"{kw['id']:<5} {status:<6} {kw['keyword']:<30} "
                  f"{kw['created_at']}")
        print(f"\n총 {len(keywords)}개 (활성 {active_count}개)")

    elif action == "add":
        if not args.k:
            print("키워드를 지정하세요: -k \"키워드1\" -k \"키워드2\"")
            db.close()
            return
        added = db.add_keywords(args.id, args.k)
        reactivated = len(args.k) - added
        print(f"키워드 추가 완료: 신규 {added}개", end="")
        if reactivated > 0:
            print(f", 재활성화 {reactivated}개", end="")
        print()
        for kw in args.k:
            print(f"  + {kw}")

    elif action == "remove":
        if not args.k:
            print("삭제할 키워드를 지정하세요: -k \"키워드\"")
            db.close()
            return
        for kw in args.k:
            ok = db.remove_keyword(args.id, kw)
            if ok:
                print(f"  삭제: {kw}")
            else:
                print(f"  찾을 수 없음: {kw}")

    elif action == "on":
        if not args.k:
            print("활성화할 키워드를 지정하세요: -k \"키워드\"")
            db.close()
            return
        for kw in args.k:
            ok = db.set_keyword_active(args.id, kw, True)
            if ok:
                print(f"  활성화: {kw}")
            else:
                print(f"  찾을 수 없음: {kw}")

    elif action == "off":
        if not args.k:
            print("비활성화할 키워드를 지정하세요: -k \"키워드\"")
            db.close()
            return
        for kw in args.k:
            ok = db.set_keyword_active(args.id, kw, False)
            if ok:
                print(f"  비활성화: {kw}")
            else:
                print(f"  찾을 수 없음: {kw}")

    else:
        print(f"알 수 없는 액션: {action}")
        print("사용법: keyword {list|add|remove|on|off} --id <ID> -k \"키워드\"")

    db.close()


def cmd_deactivate(args):
    """사이트 비활성화"""
    db = CrawlDB()
    db.deactivate_site(args.id)
    print(f"사이트 ID={args.id} 비활성화 완료")
    db.close()


def cmd_activate(args):
    """사이트 활성화"""
    db = CrawlDB()
    db.activate_site(args.id)
    print(f"사이트 ID={args.id} 활성화 완료")
    db.close()


def main():
    parser = argparse.ArgumentParser(
        description="크롤링 에이전트 - DB 기반 멀티사이트 수집",
    )
    sub = parser.add_subparsers(dest="command", help="실행할 명령")

    # add
    p_add = sub.add_parser("add", help="사이트 등록")
    p_add.add_argument("--name", required=True, help="사이트 이름")
    p_add.add_argument("--url", required=True, help="사이트 URL")
    p_add.add_argument(
        "--agent", default="product",
        help="에이전트 타입 (product, news)",
    )
    p_add.add_argument(
        "--config",
        help="crawl_config JSON 문자열 (예: '{\"max_products\": 50}')",
    )

    # list
    sub.add_parser("list", help="등록된 사이트 목록")

    # run
    p_run = sub.add_parser("run", help="수집 실행")
    p_run.add_argument("--id", type=int, help="특정 사이트 ID (미지정 시 전체)")
    p_run.add_argument(
        "--agent",
        help="특정 에이전트 타입만 수집 (product, news)",
    )
    p_run.add_argument(
        "--keywords",
        help="일회성 키워드 지정 (쉼표 구분, 뉴스 전용). "
             "예: --keywords \"해외여행,환율,면세\"",
    )
    p_run.add_argument(
        "--proxy", action="store_true",
        help="무료 프록시 IP 로테이션 활성화",
    )

    # config
    p_config = sub.add_parser("config", help="crawl_config 조회/수정")
    p_config.add_argument("--id", type=int, required=True, help="사이트 ID")
    p_config.add_argument(
        "--set",
        help="설정 JSON (예: '{\"collect_details\": false}')",
    )
    p_config.add_argument(
        "--reset", action="store_true",
        help="crawl_config 을 기본값으로 초기화",
    )

    # result
    p_result = sub.add_parser("result", help="수집 결과 조회")
    p_result.add_argument("--id", type=int, required=True, help="사이트 ID")

    # keyword
    p_kw = sub.add_parser("keyword", help="뉴스 키워드 관리")
    p_kw.add_argument(
        "action",
        choices=["list", "add", "remove", "on", "off"],
        help="키워드 액션 (list/add/remove/on/off)",
    )
    p_kw.add_argument("--id", type=int, required=True, help="사이트 ID")
    p_kw.add_argument(
        "-k", action="append",
        help="키워드 (복수 지정 가능: -k \"AI\" -k \"반도체\")",
    )

    # deactivate
    p_deact = sub.add_parser("deactivate", help="사이트 비활성화")
    p_deact.add_argument("--id", type=int, required=True, help="사이트 ID")

    # activate
    p_act = sub.add_parser("activate", help="사이트 활성화")
    p_act.add_argument("--id", type=int, required=True, help="사이트 ID")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    commands = {
        "add": cmd_add,
        "list": cmd_list,
        "run": cmd_run,
        "config": cmd_config,
        "result": cmd_result,
        "keyword": cmd_keyword,
        "deactivate": cmd_deactivate,
        "activate": cmd_activate,
    }

    commands[args.command](args)


if __name__ == "__main__":
    main()
