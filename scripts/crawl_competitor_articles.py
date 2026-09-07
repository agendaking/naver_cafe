"""T-03: 경쟁사(한국타이어/넥센타이어) 게시글 크롤러.

config/cafes.yaml의 official_accounts 화이트리스트로 공식 계정 게시글만
남긴다. 카페별로 필터링 전/후 게시글 수를 로그로 남긴다 (승인 기준).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import openpyxl  # noqa: E402

from naver_cafe_crawler.articles import write_brand_sheet  # noqa: E402
from naver_cafe_crawler.crawl import (  # noqa: E402
    fetch_raw_articles_for_month,
    filter_official_accounts,
    raw_to_article_records,
)
from naver_cafe_crawler.naver_api import parse_cafe_menu_ids  # noqa: E402
from naver_cafe_crawler.roster import load_raw  # noqa: E402

BRAND_LABELS = {"hankook": "한국타이어", "nexen": "넥센타이어"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--brand", required=True, choices=["hankook", "nexen"])
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=int, required=True)
    parser.add_argument("--config", default=str(Path(__file__).resolve().parents[1] / "config" / "cafes.yaml"))
    parser.add_argument("--out", required=True)
    parser.add_argument("--delay", type=float, default=0.3)
    args = parser.parse_args()

    data = load_raw(args.config)
    brand_data = data["brands"][args.brand]
    official_accounts = brand_data.get("official_accounts") or []
    print(f"공식 계정 화이트리스트: {official_accounts}", file=sys.stderr)

    all_articles = []
    total_before = 0
    total_after = 0
    all_cafes = [c for g in brand_data["groups"] for c in g["cafes"]]

    for i, cafe in enumerate(all_cafes, start=1):
        cafe_id, menu_id = parse_cafe_menu_ids(cafe["url"])
        try:
            raw = fetch_raw_articles_for_month(cafe_id, menu_id, args.year, args.month)
        except Exception as e:  # noqa: BLE001
            print(f"[{i}/{len(all_cafes)}] [SKIP] {cafe['name']} 실패: {e}", file=sys.stderr)
            continue

        filtered = filter_official_accounts(raw, official_accounts)
        print(
            f"[{i}/{len(all_cafes)}] {cafe['name']}: {len(raw)} -> {len(filtered)} "
            f"(공식 계정 필터링 후)",
            file=sys.stderr,
        )
        total_before += len(raw)
        total_after += len(filtered)

        records = raw_to_article_records(filtered, cafe_name=cafe["name"], group=cafe["car_model"])
        all_articles.extend(records)
        time.sleep(args.delay)

    print(f"전체: {total_before} -> {total_after} (공식 계정 필터링 후)", file=sys.stderr)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = BRAND_LABELS[args.brand]
    write_brand_sheet(ws, brand_data["label"], all_articles)
    wb.save(args.out)
    print(f"Wrote {args.out}: {len(all_articles)} articles")


if __name__ == "__main__":
    main()
