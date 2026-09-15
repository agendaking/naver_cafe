"""형님이 준비한 "{N월} 이벤트 현황_MMDD.xlsx" 템플릿을 그 자리에서 채운다.

첫 시트(기본값 "금호")의 각 행에 있는 게시판/게시물 URL에서 조회수/좋아요/댓글수를
같은 행에 써넣고, 그 게시글들의 댓글(=응모자)을 전부 모아 둘째 시트(기본값
"응모자")에 이어서 쓴다. URL 종류별로 다르게 처리한다:

- `cafe.naver.com` — 지정 날짜(연/월/일)에 그 게시판에 올라온 게시글을 찾는다
  (게시판당 한 달에 이벤트 게시글이 1건이라 날짜만으로 특정 가능).
- `pf.kakao.com` — 이미 URL 자체가 특정 게시물(소식)을 가리키므로 날짜 검색 없이
  바로 그 게시물의 좋아요/댓글수 + 댓글 원문을 가져온다. 조회수는 카카오톡 채널이
  게시물 단위로 공개하지 않는 값이라(화면에도 없음) 항상 비워두고 비고에 사유를
  남긴다 (2026-09-16 확인, src/naver_cafe_crawler/kakao_channel.py 참고).
- 그 외(네이버블로그/티스토리 등) — 현재 이 스크립트가 다루지 않는다. 좋아요/댓글
  "개수"는 blog.py의 fetch_naver_blog_stats/fetch_tistory_stats로 수집 가능하지만,
  댓글 "본문" 목록을 주는 공개 API를 아직 찾지 못했다 (blog.naver.com이 사내 브라우저
  정책상 막혀 있어 실제 네트워크 요청을 확인할 방법이 없었음, 2026-09-16). 잘못된
  응모자 데이터를 만드는 것보다 비워두는 쪽을 택했다 — 이 행들은 계속 스킵하고
  비고도 건드리지 않는다.

응모자 시트는 이 스크립트를 실행할 때마다 row 4부터 전체를 다시 쓴다(카페 →
카카오 순서로 이어붙임) — 기존 데이터 중간에 있는 빈 셀을 "다음 쓸 자리"로 오인해
덮어쓰는 사고(2026-09-16 실제 발생, No.83~167 카페 응모자가 카카오 댓글로 뒤집어
써졌던 사고)를 막기 위해 항상 처음부터 다시 쓰고 절대 기존 셀을 스캔해서 빈 곳을
찾지 않는다.

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
    EventComment,
    collect_event_comments,
    find_cafe_link_result,
)
from naver_cafe_crawler.kakao_channel import (  # noqa: E402
    KakaoFetchError,
    fetch_kakao_post_comments,
    fetch_kakao_post_meta,
    parse_kakao_post_url,
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
    kakao_rows = []
    for row in range(LINK_FIRST_DATA_ROW, link_ws.max_row + 1):
        url = link_ws.cell(row, LINK_COL_URL).value
        name = link_ws.cell(row, LINK_COL_NAME).value
        if not url:
            continue
        url = str(url)
        if "cafe.naver.com" in url:
            rows.append((row, name, url))
        elif "pf.kakao.com" in url:
            kakao_rows.append((row, name, url))
        # 그 외(네이버블로그/티스토리 등)는 스킵 — 모듈 docstring 참고

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

    if kakao_rows:
        print(f"\n카카오톡 채널 게시물 {len(kakao_rows)}건 수집 중...", file=sys.stderr)
    for row, name, url in kakao_rows:
        try:
            profile_id, post_id = parse_kakao_post_url(url)
            meta = fetch_kakao_post_meta(profile_id, post_id)
            kakao_comments = fetch_kakao_post_comments(profile_id, post_id)
        except (KakaoFetchError, ValueError) as e:
            print(f"  {name}: [실패] {e}", file=sys.stderr)
            link_ws.cell(row, LINK_COL_NOTE, f"크롤링 실패: {e}")
            continue
        print(f"  {name}: 좋아요={meta.like_count} 댓글={meta.comment_count} (수집 {len(kakao_comments)}건)", file=sys.stderr)
        link_ws.cell(row, LINK_COL_LIKES, meta.like_count)
        link_ws.cell(row, LINK_COL_COMMENTS, meta.comment_count)
        link_ws.cell(row, LINK_COL_NOTE, "조회수는 카카오톡 채널이 게시물별로 공개하지 않음(공개 API/화면 모두 미노출)")
        comments.extend(
            EventComment(cafe_name=name, writer=c.writer, content=c.content, submitted_at=c.submitted_at)
            for c in kakao_comments
        )

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
