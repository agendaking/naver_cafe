"""T-02/T-04: 금호타이어 브랜드 게시글 + 댓글 크롤러.

config/cafes.yaml의 kumho 로스터 전체를 대상 월로 순회하며 게시글과 댓글을
"같은 배치"에서 함께 모아(PRD 3.1 필수 요건) `금호타이어` 시트와 `댓글` 시트를
한 파일에 생성한다.
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
from naver_cafe_crawler.crawl import fetch_cafe_articles_and_comments_for_month  # noqa: E402
from naver_cafe_crawler.roster import load_raw  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=int, required=True)
    parser.add_argument("--config", default=str(Path(__file__).resolve().parents[1] / "config" / "cafes.yaml"))
    parser.add_argument("--out", required=True)
    parser.add_argument("--delay", type=float, default=0.3, help="카페 간 요청 간격(초)")
    args = parser.parse_args()

    data = load_raw(args.config)
    kumho = data["brands"]["kumho"]

    all_articles = []
    all_comments = []
    total_restricted = 0
    total_cafes = sum(len(g["cafes"]) for g in kumho["groups"])
    done = 0
    for group in kumho["groups"]:
        for cafe in group["cafes"]:
            done += 1
            print(f"[{done}/{total_cafes}] {cafe['name']} ...", file=sys.stderr)
            try:
                articles, comments, restricted = fetch_cafe_articles_and_comments_for_month(
                    cafe["url"],
                    args.year,
                    args.month,
                    gubun="금호",
                    cafe_name=cafe["name"],
                    group=cafe["car_model"],
                )
                all_articles.extend(articles)
                all_comments.extend(comments)
                total_restricted += restricted
            except Exception as e:  # noqa: BLE001
                print(f"  [SKIP] {cafe['name']} 실패: {e}", file=sys.stderr)
            time.sleep(args.delay)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "금호타이어"
    write_brand_sheet(ws, "금호 타이어", all_articles)

    comment_ws = wb.create_sheet("댓글")
    write_comment_sheet(comment_ws, all_comments)

    wb.save(args.out)

    total_views = sum(a.views for a in all_articles)
    total_likes = sum(a.likes for a in all_articles)
    total_comments_sheet = sum(a.comments for a in all_articles)
    print(
        f"Wrote {args.out}: {len(all_articles)} articles, {len(all_comments)} comment rows, "
        f"합계 조회수={total_views} 좋아요={total_likes} 댓글={total_comments_sheet}"
    )

    gubun_filtered = [c for c in all_comments if c.gubun == "금호"]
    expected = total_comments_sheet - total_restricted
    if len(gubun_filtered) != expected:
        print(
            f"[검증 실패] 댓글 시트 행수(구분='금호' 필터, {len(gubun_filtered)}) != "
            f"금호타이어 시트 댓글 합계 - 회원전용 제외({expected} = {total_comments_sheet} - {total_restricted})",
            file=sys.stderr,
        )
        sys.exit(1)
    print(
        f"[검증 통과] 댓글 시트 행수(구분='금호') == 금호타이어 시트 댓글 합계 - 회원전용({total_restricted}) == {expected}"
    )


if __name__ == "__main__":
    main()
