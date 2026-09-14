"""형님이 준비한 "{N월} 이벤트 현황_MMDD.xlsx" 템플릿을 그 자리에서 채운다.

첫 시트(기본값 "금호")의 각 행에 있는 카페 게시판 URL에서 지정 날짜(연/월/일)에
올라온 게시글을 찾아 조회수/좋아요/댓글수를 같은 행에 써넣고, 그 게시글들의
댓글(=응모자)을 전부 모아 둘째 시트(기본값 "응모자")에 이어서 쓴다.

이 스크립트는 워크북의 기존 헤더 위치를 그대로 읽어서 맞춰 쓴다 (row 3 헤더,
row 4부터 데이터) — 새로 시트를 만들지 않고 형님이 만든 템플릿 그대로 쓴다는
점에서 crawl_kumho_event.py(T-06, 제목 매칭 + 새 워크북 생성)와 다르다.

사용 예:
    python scripts/fill_event_status_by_date.py \\
        --xlsx "9월 이벤트 현황_0914.xlsx" --year 2026 --month 9 --day 7
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import openpyxl  # noqa: E402

from naver_cafe_crawler.event_status_report import (  # noqa: E402
    collect_event_comments,
    find_cafe_link_result,
)

LINK_HEADER_ROW = 3
LINK_FIRST_DATA_ROW = 4
LINK_COL_NAME = 7  # G: 카페명
LINK_COL_URL = 9  # I: URL
LINK_COL_VIEWS = 10  # J: 조회수
LINK_COL_LIKES = 11  # K: 좋아요
LINK_COL_COMMENTS = 12  # L: 댓글
LINK_COL_NOTE = 13  # M: 비고

COMMENT_HEADER_ROW = 3
COMMENT_FIRST_DATA_ROW = 4
COMMENT_COL_NO = 2  # B
COMMENT_COL_CAFE1 = 3  # C: 카페명
COMMENT_COL_NICK = 4  # D: 별명
COMMENT_COL_CAFE2 = 5  # E: 카페명 (템플릿 헤더가 실제로 중복돼 있어 그대로 채움)
COMMENT_COL_CONTENT = 6  # F: 댓글
COMMENT_COL_TIME = 7  # G: 응모시간


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xlsx", required=True, help="대상 워크북 경로 (제자리에서 수정)")
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=int, required=True)
    parser.add_argument("--day", type=int, required=True)
    parser.add_argument("--link-sheet", default="금호")
    parser.add_argument("--comment-sheet", default="응모자")
    parser.add_argument("--delay", type=float, default=0.2, help="카페 간 요청 간격(초)")
    args = parser.parse_args()

    wb = openpyxl.load_workbook(args.xlsx)
    link_ws = wb[args.link_sheet]
    comment_ws = wb[args.comment_sheet]

    rows = []
    for row in range(LINK_FIRST_DATA_ROW, link_ws.max_row + 1):
        url = link_ws.cell(row, LINK_COL_URL).value
        name = link_ws.cell(row, LINK_COL_NAME).value
        if not url or "cafe.naver.com" not in str(url):
            continue  # 블로그/티스토리/카카오톡 등 카페 게시판이 아닌 행은 스킵
        rows.append((row, name, url))

    print(f"{len(rows)}개 카페 게시판에서 {args.year}-{args.month:02d}-{args.day:02d} 게시글 검색 중...", file=sys.stderr)

    results = []
    for i, (row, name, url) in enumerate(rows, start=1):
        r = find_cafe_link_result(name, url, args.year, args.month, args.day)
        results.append((row, r))
        if r.found:
            a = r.article
            note = f"게시글 {r.ambiguous_matches}건 중 조회수 최다 선택" if r.ambiguous_matches else None
            print(f"  [{i}/{len(rows)}] {name}: 조회수={a.read_count} 좋아요={a.like_count} 댓글={a.comment_count}", file=sys.stderr)
            link_ws.cell(row, LINK_COL_VIEWS, a.read_count)
            link_ws.cell(row, LINK_COL_LIKES, a.like_count)
            link_ws.cell(row, LINK_COL_COMMENTS, a.comment_count)
            if note:
                link_ws.cell(row, LINK_COL_NOTE, note)
        elif r.error:
            print(f"  [{i}/{len(rows)}] {name}: [실패] {r.error}", file=sys.stderr)
            link_ws.cell(row, LINK_COL_NOTE, f"크롤링 실패: {r.error}")
        else:
            print(f"  [{i}/{len(rows)}] {name}: {args.day}일 게시글 없음", file=sys.stderr)
            link_ws.cell(row, LINK_COL_NOTE, f"{args.month}/{args.day} 게시글 없음")
        time.sleep(args.delay)

    found_results = [r for _, r in results if r.found]
    print(f"\n{len(found_results)}/{len(rows)}개 카페에서 게시글 발견, 댓글 수집 시작...", file=sys.stderr)

    comments, restricted = collect_event_comments(found_results)
    print(f"댓글 {len(comments)}건 수집 (회원전용 제외 {restricted}건)", file=sys.stderr)

    for i, c in enumerate(comments, start=1):
        r = COMMENT_FIRST_DATA_ROW + i - 1
        comment_ws.cell(r, COMMENT_COL_NO, i)
        comment_ws.cell(r, COMMENT_COL_CAFE1, c.cafe_name)
        comment_ws.cell(r, COMMENT_COL_NICK, c.writer)
        comment_ws.cell(r, COMMENT_COL_CAFE2, c.cafe_name)
        comment_ws.cell(r, COMMENT_COL_CONTENT, c.content)
        comment_ws.cell(r, COMMENT_COL_TIME, c.submitted_at)

    wb.save(args.xlsx)
    print(f"\n저장 완료: {args.xlsx}", file=sys.stderr)


if __name__ == "__main__":
    main()
