"""날짜 지정 이벤트 현황판 갱신.

형님이 매달 손으로 준비하는 "{N월} 이벤트 현황_MMDD.xlsx"는 카페별 게시판
URL 목록(첫 시트, 이미 로스터가 정리돼 있음)과 댓글 응모 현황(둘째 시트,
빈 템플릿)을 담는 실무용 워크북이다. events.py(T-06)는 제목을 알려줘야
크로스포스팅 게시글을 찾지만, 이 워크북은 카페별 URL이 이미 확정돼 있어서
제목 매칭이 필요 없다 — "이번 달 그 날짜에 이 게시판에 뭐가 올라왔는지"만
확인하면 된다 (2026-09-14 확인: 게시판당 한 달에 이벤트 게시글이 정확히
1건이라 날짜만으로 충분히 특정됨, 예: cafe_id=10124067/menu_id=3278에서
9/7 게시글이 유일하게 매칭).

PRD 3.2 `{N월}이벤트.xlsx`와는 별개의 산출물이며, 그 스키마를 따르지
않는다 — 이 리포트는 형님이 미리 만들어둔 템플릿 그대로 채우는 것이 목적.
"""

from __future__ import annotations

from dataclasses import dataclass

from .crawl import (
    FetchCommentPageFn,
    FetchPageFn,
    RawArticle,
    fetch_raw_articles_for_month,
    fetch_raw_comments_for_article,
)
from .naver_api import CommentsRestrictedError, fetch_article_page, fetch_comment_page, parse_cafe_menu_ids


@dataclass(frozen=True)
class CafeLinkResult:
    """워크북 첫 시트 한 행(카페 하나)에 대한 크롤링 결과."""

    cafe_name: str
    url: str
    found: bool
    article: RawArticle | None = None
    cafe_id: str | None = None
    ambiguous_matches: int = 0  # 그 날짜에 게시글이 2개 이상이면 개수 (조회수 최댓값을 채택)
    error: str | None = None


@dataclass(frozen=True)
class EventComment:
    cafe_name: str
    writer: str
    content: str
    submitted_at: str  # "2026.09.07 11:23"


def find_cafe_link_result(
    cafe_name: str,
    url: str,
    year: int,
    month: int,
    day: int,
    *,
    fetch_page: FetchPageFn = fetch_article_page,
) -> CafeLinkResult:
    """URL 하나(카페 게시판)에서 지정 날짜에 올라온 게시글을 찾는다.

    카페/게시판 ID 파싱 실패, 네트워크 실패 등은 예외로 배치를 죽이지 않고
    error 필드에 담아 반환한다 (crawl.py의 기존 실패 처리 관례를 따름).
    """
    try:
        cafe_id, menu_id = parse_cafe_menu_ids(url)
    except ValueError as e:
        return CafeLinkResult(cafe_name=cafe_name, url=url, found=False, error=str(e))

    try:
        raw = fetch_raw_articles_for_month(cafe_id, menu_id, year, month, fetch_page=fetch_page)
    except Exception as e:  # noqa: BLE001
        return CafeLinkResult(cafe_name=cafe_name, url=url, found=False, cafe_id=cafe_id, error=str(e))

    matches = [a for a in raw if a.write_datetime.day == day]
    if not matches:
        return CafeLinkResult(cafe_name=cafe_name, url=url, found=False, cafe_id=cafe_id)

    best = max(matches, key=lambda a: a.read_count) if len(matches) > 1 else matches[0]
    return CafeLinkResult(
        cafe_name=cafe_name,
        url=url,
        found=True,
        article=best,
        cafe_id=cafe_id,
        ambiguous_matches=len(matches) if len(matches) > 1 else 0,
    )


def collect_event_comments(
    results: list[CafeLinkResult],
    *,
    fetch_comment_page: FetchCommentPageFn = fetch_comment_page,
) -> tuple[list[EventComment], int]:
    """찾은 게시글들의 댓글(=응모자 목록)을 전부 모은다.

    반환값의 두 번째 원소는 회원전용이라 댓글을 못 가져온 게시글 수.
    """
    all_comments: list[EventComment] = []
    restricted = 0
    for r in results:
        if not r.found or r.article is None or r.article.comment_count == 0:
            continue
        try:
            raw_comments = fetch_raw_comments_for_article(
                r.cafe_id, r.article.article_id, fetch_comment_page=fetch_comment_page
            )
        except CommentsRestrictedError:
            restricted += 1
            continue
        for c in raw_comments:
            all_comments.append(
                EventComment(
                    cafe_name=r.cafe_name,
                    writer=c.writer,
                    content=c.content,
                    submitted_at=c.write_datetime.strftime("%Y.%m.%d %H:%M"),
                )
            )
    return all_comments, restricted
