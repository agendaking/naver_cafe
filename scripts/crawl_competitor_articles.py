"""T-03/T-04: 경쟁사(한국타이어/넥센타이어) 게시글 + 댓글 크롤러.

config/cafes.yaml의 official_accounts 화이트리스트로 공식 계정 게시글만
남기고(카페별 필터링 전/후 게시글 수를 로그로 남김 — T-03 승인 기준), 그
필터링된 게시글의 댓글을 "같은 배치"에서 함께 모은다(PRD 3.1 — T-04).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import openpyxl  # noqa: E402

from naver_cafe_crawler.articles import write_brand_sheet  # noqa: E402
from naver_cafe_crawler.comments import write_comment_sheet  # noqa: E402
from naver_cafe_crawler.crawl import (  # noqa: E402
    fetch_comments_for_article,
    fetch_raw_articles_for_month,
    filter_official_accounts,
    raw_to_article_records,
)
from naver_cafe_crawler.naver_api import CommentsRestrictedError, parse_cafe_menu_ids  # noqa: E402
from naver_cafe_crawler.roster import load_raw  # noqa: E402

BRAND_LABELS = {"hankook": "한국타이어", "nexen": "넥센타이어"}
GUBUN_LABELS = {"hankook": "한국", "nexen": "넥센"}


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
    gubun = GUBUN_LABELS[args.brand]
    print(f"공식 계정 화이트리스트: {official_accounts}", file=sys.stderr)

    all_articles = []
    all_comments = []
    total_before = 0
    total_after = 0
    total_restricted = 0
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

        # 필터링된(공식 계정) 게시글의 댓글만 같은 배치에서 함께 수집.
        # 게시글 하나에서 실패해도 전체 배치는 죽지 않게 스킵하고 로그만 남긴다.
        for a in filtered:
            if a.comment_count == 0:
                continue
            try:
                all_comments.extend(
                    fetch_comments_for_article(
                        cafe_id,
                        a.article_id,
                        gubun=gubun,
                        cafe_name=cafe["name"],
                        article_title=a.subject,
                    )
                )
            except CommentsRestrictedError as e:
                print(f"  [회원전용] {cafe['name']} / {a.subject[:30]!r}: {e.reason}", file=sys.stderr)
                total_restricted += a.comment_count
            except Exception as e:  # noqa: BLE001
                print(
                    f"  [SKIP 댓글] {cafe['name']} / {a.subject[:30]!r} 실패: {e}",
                    file=sys.stderr,
                )
        time.sleep(args.delay)

    print(f"전체: {total_before} -> {total_after} (공식 계정 필터링 후)", file=sys.stderr)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = BRAND_LABELS[args.brand]
    write_brand_sheet(ws, brand_data["label"], all_articles)

    comment_ws = wb.create_sheet("댓글")
    write_comment_sheet(comment_ws, all_comments)

    wb.save(args.out)
    total_comments_sheet = sum(a.comments for a in all_articles)
    print(f"Wrote {args.out}: {len(all_articles)} articles, {len(all_comments)} comment rows")

    gubun_filtered = [c for c in all_comments if c.gubun == gubun]
    expected = total_comments_sheet - total_restricted
    if len(gubun_filtered) != expected:
        print(
            f"[검증 실패] 댓글 시트 행수(구분='{gubun}' 필터, {len(gubun_filtered)}) != "
            f"{brand_data['label']} 시트 댓글 합계 - 회원전용 제외"
            f"({expected} = {total_comments_sheet} - {total_restricted})",
            file=sys.stderr,
        )
        sys.exit(1)
    print(
        f"[검증 통과] 댓글 시트 행수(구분='{gubun}') == "
        f"{brand_data['label']} 시트 댓글 합계 - 회원전용({total_restricted}) == {expected}"
    )


if __name__ == "__main__":
    main()
