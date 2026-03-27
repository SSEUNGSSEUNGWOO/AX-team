"""
쿠팡 가격 모니터링 툴 — CLI 진입점
Commands: add / list / delete / run / status
"""

import sys
import argparse
from pathlib import Path

from monitor import ProductRepository, CoupangScraper, PriceMonitor, Product


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="coupang-monitor",
        description="쿠팡 상품 가격 모니터링 툴",
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    p_add = sub.add_parser("add", help="모니터링 상품 등록")
    p_add.add_argument("url",   type=str,   help="쿠팡 상품 URL")
    p_add.add_argument("price", type=int,   help="목표가 (원)")
    p_add.add_argument("--name", "-n", type=str, default="", help="상품 별칭")

    sub.add_parser("list", help="등록된 상품 목록 출력")

    p_del = sub.add_parser("delete", help="상품 삭제")
    p_del.add_argument("product_id", type=str, help="삭제할 상품 ID")

    p_run = sub.add_parser("run", help="가격 모니터링 실행 (주기적 폴링)")
    p_run.add_argument("--interval", "-i", type=int, default=3600, metavar="SECONDS")
    p_run.add_argument("--once", action="store_true", help="1회만 체크하고 종료")

    p_status = sub.add_parser("status", help="특정 상품의 현재 가격 즉시 조회")
    p_status.add_argument("product_id", type=str)

    return parser


def cmd_add(args: argparse.Namespace, store: ProductRepository) -> int:
    scraper = CoupangScraper()
    try:
        product_id = scraper.extract_product_id(args.url)
    except ValueError as e:
        print(f"[오류] {e}", file=sys.stderr)
        return 1

    name = args.name or f"상품-{product_id}"
    product = Product(product_id=product_id, url=args.url, name=name, target_price=args.price)
    try:
        store.add(product)
    except ValueError as e:
        print(f"[오류] {e}", file=sys.stderr)
        return 1

    print(f"[등록 완료]")
    print(f"  ID     : {product.product_id}")
    print(f"  이름   : {product.name}")
    print(f"  목표가 : {product.target_price:,}원")
    return 0


def cmd_list(args: argparse.Namespace, store: ProductRepository) -> int:
    products = store.all()
    if not products:
        print("등록된 상품이 없습니다. `add` 명령으로 추가하세요.")
        return 0

    header = f"{'ID':<15}  {'이름':<20}  {'목표가':>10}  {'최근가':>10}  {'상태'}"
    print(header)
    print("─" * len(header))
    for p in products:
        last_price = f"{p.last_price:,}원" if p.last_price is not None else "미조회"
        status     = "✅ 달성" if p.is_target_met() else "⏳ 대기"
        print(f"{p.product_id:<15}  {p.name:<20}  {p.target_price:>10,}원  {last_price:>10}  {status}")
    return 0


def cmd_delete(args: argparse.Namespace, store: ProductRepository) -> int:
    try:
        store.remove(args.product_id)
        print(f"[삭제 완료] {args.product_id}")
        return 0
    except KeyError as e:
        print(f"[오류] {e}", file=sys.stderr)
        return 1


def cmd_run(args: argparse.Namespace, store: ProductRepository) -> int:
    monitor = PriceMonitor(store=store)
    if args.once:
        print("[1회 체크 모드]")
        monitor.check_all()
        return 0

    print(f"[모니터링 시작] 폴링 주기: {args.interval}초  (종료: Ctrl+C)")
    try:
        monitor.run_loop(interval_seconds=args.interval)
    except KeyboardInterrupt:
        print("\n[모니터링 종료]")
    return 0


def cmd_status(args: argparse.Namespace, store: ProductRepository) -> int:
    product = store.get(args.product_id)
    if product is None:
        print(f"[오류] ID '{args.product_id}' 를 찾을 수 없습니다.", file=sys.stderr)
        return 1

    scraper = CoupangScraper()
    current_price = scraper.fetch_price(product.url)
    if current_price is None:
        print("[오류] 가격 조회 실패 — URL을 확인하세요.", file=sys.stderr)
        return 1

    gap    = current_price - product.target_price
    symbol = "🔻" if gap <= 0 else "🔺"
    print(f"[현재 가격 조회]")
    print(f"  상품   : {product.name}")
    print(f"  현재가 : {current_price:,}원")
    print(f"  목표가 : {product.target_price:,}원")
    print(f"  차이   : {symbol} {abs(gap):,}원")
    if gap <= 0:
        print("  ✅ 목표가 달성! 지금 구매를 고려하세요.")
    return 0


# ── 디스패처 ──────────────────────────────────────────────────────────────────
HANDLERS = {
    "add":    cmd_add,
    "list":   cmd_list,
    "delete": cmd_delete,
    "run":    cmd_run,
    "status": cmd_status,
}


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    store = ProductRepository()
    handler = HANDLERS.get(args.command)
    if handler is None:
        parser.print_help()
        sys.exit(1)
    sys.exit(handler(args, store))


if __name__ == "__main__":
    main()
