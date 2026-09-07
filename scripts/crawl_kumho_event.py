"""T-06: 금호 이벤트 참여 현황 크롤러.

형님이 --event-title로 지정한 게시글(제목 기준, 크로스포스팅 정규화 매칭)을
config/cafes.yaml의 kumho 로스터 전체에서 찾아 조회수/좋아요/댓글과 고유
참여자수(근사치)를 집계한다.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import openpyxl  # noqa: E402

from naver_cafe_crawler.events import (  # noqa: E402
    collect_event_comments,
    find_event_across_cafes,
    summarize,
    write_event_sheet,
)
from naver_cafe_crawler.roster import load_raw  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event-title", required=True, help="추적할 이벤트 게시글 제목")
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=int, required=True)
    parser.add_argument("--config", default=str(Path(__file__).resolve().parents[1] / "config" / "cafes.yaml"))
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    data = load_raw(args.config)
    kumho = data["brands"]["kumho"]
    all_cafes = []
    for group in kumho["groups"]:
        for cafe in group["cafes"]:
            c = dict(cafe)
            c["board_group"] = group["board_group"]
            all_cafes.append(c)

    print(f"{len(all_cafes)}개 카페에서 '{args.event_title}' 검색 중...", file=sys.stderr)
    results = find_event_across_cafes(all_cafes, args.event_title, args.year, args.month)
    found = [r for r in results if r.found]
    print(f"{len(found)}/{len(results)}개 카페에서 발견", file=sys.stderr)
    for r in found:
        print(f"  {r.cafe_name}: 조회수={r.views} 좋아요={r.likes} 댓글={r.comments}", file=sys.stderr)

    comments, restricted = collect_event_comments(results, gubun="금호")
    summary = summarize(results, comments, restricted)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "금호"
    write_event_sheet(ws, args.event_title, results, summary)
    wb.save(args.out)

    print(
        f"Wrote {args.out}: 총조회수={summary.total_views} 총좋아요={summary.total_likes} "
        f"총댓글={summary.total_comments} 고유참여자수={summary.unique_participant_count} "
        f"(회원전용 제외 {summary.restricted_comment_count}건)"
    )


if __name__ == "__main__":
    main()
