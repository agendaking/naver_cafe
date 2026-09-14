"""지정 월의 게시글을 카페별로 수집해서 ArticleRecord로 변환.

작성자 정보(writerInfo)도 함께 들고 있게 해서, T-03(경쟁사 공식 계정
필터링)이 같은 fetch 결과를 재사용할 수 있게 한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Iterable

from .articles import ArticleRecord
from .comments import CommentRecord
from .naver_api import (
    CommentsRestrictedError,
    fetch_article_page,
    fetch_comment_page,
    parse_cafe_menu_ids,
)

FetchPageFn = Callable[..., dict]
FetchCommentPageFn = Callable[..., dict]


@dataclass(frozen=True)
class RawArticle:
    """API가 주는 원본 필드 중 크롤러가 쓰는 것만 뽑은 중간 표현."""

    article_id: int
    write_datetime: datetime
    subject: str
    read_count: int
    like_count: int
    comment_count: int
    writer_nickname: str
    writer_member_level_name: str


def _month_bounds(year: int, month: int) -> tuple[datetime, datetime]:
    start = datetime(year, month, 1)
    if month == 12:
        end_exclusive = datetime(year + 1, 1, 1)
    else:
        end_exclusive = datetime(year, month + 1, 1)
    return start, end_exclusive


def fetch_raw_articles_for_month(
    cafe_id: str,
    menu_id: str,
    year: int,
    month: int,
    *,
    fetch_page: FetchPageFn = fetch_article_page,
    max_pages: int = 30,
) -> list[RawArticle]:
    """대상 월에 속하는 게시글만 페이지를 넘겨가며 모은다.

    최신순 정렬(sortBy=TIME)이라는 전제 하에, 한 페이지의 게시글이 전부
    대상 월보다 과거면 그 시점에 멈춘다.
    """
    month_start, month_end_exclusive = _month_bounds(year, month)
    results: list[RawArticle] = []

    page = 1
    while page <= max_pages:
        data = fetch_page(cafe_id, menu_id, page)
        items = data.get("result", {}).get("articleList", [])
        if not items:
            break

        reached_before_month = False
        for entry in items:
            if entry.get("type") != "ARTICLE":
                continue
            item = entry["item"]
            dt = datetime.fromtimestamp(item["writeDateTimestamp"] / 1000)
            if dt >= month_end_exclusive:
                continue  # 대상 월보다 미래 글
            if dt < month_start:
                reached_before_month = True
                break
            writer = item.get("writerInfo", {})
            results.append(
                RawArticle(
                    article_id=item["articleId"],
                    write_datetime=dt,
                    subject=item["subject"],
                    read_count=item["readCount"],
                    like_count=item["likeCount"],
                    comment_count=item["commentCount"],
                    writer_nickname=writer.get("nickName", ""),
                    writer_member_level_name=writer.get("memberLevelName", ""),
                )
            )

        if reached_before_month:
            break

        page_info = data.get("result", {}).get("pageInfo", {})
        last_page = page_info.get("lastNavigationPageNumber")
        if last_page is not None and page >= last_page and not page_info.get("visibleNextButton", False):
            break

        page += 1

    return results


def filter_official_accounts(
    raw_articles: Iterable[RawArticle], official_accounts: Iterable[str]
) -> list[RawArticle]:
    """작성자 닉네임이 공식 계정 화이트리스트에 있는 게시글만 남긴다 (T-03).

    화이트리스트가 비어 있으면(예: 금호처럼 계정 필터링이 필요 없는 브랜드)
    아무것도 거르지 않고 그대로 반환한다.
    """
    allowed = set(official_accounts)
    if not allowed:
        return list(raw_articles)
    return [a for a in raw_articles if a.writer_nickname in allowed]


def raw_to_article_records(
    raw_articles: Iterable[RawArticle], *, cafe_name: str, group: str
) -> list[ArticleRecord]:
    return [
        ArticleRecord(
            date=a.write_datetime.strftime("%Y.%m.%d"),
            cafe=cafe_name,
            group=group,
            title=a.subject,
            views=a.read_count,
            likes=a.like_count,
            comments=a.comment_count,
        )
        for a in raw_articles
    ]


def fetch_cafe_articles_for_month(
    cafe_url: str,
    year: int,
    month: int,
    *,
    cafe_name: str,
    group: str,
    fetch_page: FetchPageFn = fetch_article_page,
) -> list[ArticleRecord]:
    cafe_id, menu_id = parse_cafe_menu_ids(cafe_url)
    raw = fetch_raw_articles_for_month(cafe_id, menu_id, year, month, fetch_page=fetch_page)
    return raw_to_article_records(raw, cafe_name=cafe_name, group=group)


def fetch_comments_for_article(
    cafe_id: str,
    article_id: int,
    *,
    gubun: str,
    cafe_name: str,
    article_title: str,
    fetch_comment_page: FetchCommentPageFn = fetch_comment_page,
    max_pages: int = 20,
) -> list[CommentRecord]:
    """게시글 하나의 댓글 전체를 페이지네이션 끝까지 모은다."""
    results: list[CommentRecord] = []
    page = 1
    while page <= max_pages:
        data = fetch_comment_page(cafe_id, article_id, page)
        result = data.get("result", {})
        items = result.get("comments", {}).get("items", [])
        for item in items:
            if item.get("isDeleted"):
                continue
            dt = datetime.fromtimestamp(item["updateDate"] / 1000)
            results.append(
                CommentRecord(
                    gubun=gubun,
                    cafe=cafe_name,
                    article_title=article_title,
                    write_date=dt.strftime("%Y.%m.%d"),
                    writer=item.get("writer", {}).get("nick", ""),
                    content=item.get("content", ""),
                )
            )
        if not result.get("hasNext"):
            break
        page += 1
    return results


@dataclass(frozen=True)
class RawComment:
    """댓글 원문을 시:분까지 보존한 중간 표현.

    comments.py의 CommentRecord는 PRD 3.1 댓글 시트용으로 write_date를
    날짜까지만 남기지만(예: "2026.09.07"), 이벤트 응모시간 기록에는 시:분이
    필요해서 별도로 둔다.
    """

    writer: str
    content: str
    write_datetime: datetime


def fetch_raw_comments_for_article(
    cafe_id: str,
    article_id: int,
    *,
    fetch_comment_page: FetchCommentPageFn = fetch_comment_page,
    max_pages: int = 20,
) -> list[RawComment]:
    """게시글 하나의 댓글 전체를 시:분 단위까지 보존한 채로 모은다."""
    results: list[RawComment] = []
    page = 1
    while page <= max_pages:
        data = fetch_comment_page(cafe_id, article_id, page)
        result = data.get("result", {})
        items = result.get("comments", {}).get("items", [])
        for item in items:
            if item.get("isDeleted"):
                continue
            dt = datetime.fromtimestamp(item["updateDate"] / 1000)
            results.append(
                RawComment(
                    writer=item.get("writer", {}).get("nick", ""),
                    content=item.get("content", ""),
                    write_datetime=dt,
                )
            )
        if not result.get("hasNext"):
            break
        page += 1
    return results


def fetch_cafe_articles_and_comments_for_month(
    cafe_url: str,
    year: int,
    month: int,
    *,
    gubun: str,
    cafe_name: str,
    group: str,
    official_accounts: Iterable[str] | None = None,
    fetch_page: FetchPageFn = fetch_article_page,
    fetch_comment_page: FetchCommentPageFn = fetch_comment_page,
) -> tuple[list[ArticleRecord], list[CommentRecord], int]:
    """게시글과 그 댓글을 한 번의 크롤링에서 함께 수집한다 (PRD 3.1 필수 요건).

    게시글 목록을 한 번만 가져와서(raw) 그 결과로 게시글 시트와 댓글 시트를
    둘 다 만들기 때문에, 두 시트가 서로 다른 시점의 스냅샷이 되는 게
    구조적으로 불가능하다.

    반환값의 세 번째 원소는 "회원 전용이라 댓글 원문을 못 가져온" 게시글들의
    댓글 수 합계다 (형님 확인, 2026-09-07: 이런 카페는 댓글을 빈칸으로 두고
    계속 진행하기로 함). 호출부에서 게시글 시트 댓글 합계와 댓글 시트 행수를
    비교할 때 이 값만큼은 예외로 빼고 비교해야 한다.
    """
    cafe_id, menu_id = parse_cafe_menu_ids(cafe_url)
    raw = fetch_raw_articles_for_month(cafe_id, menu_id, year, month, fetch_page=fetch_page)
    if official_accounts:
        raw = filter_official_accounts(raw, official_accounts)

    articles = raw_to_article_records(raw, cafe_name=cafe_name, group=group)

    all_comments: list[CommentRecord] = []
    restricted_comment_count = 0
    for a in raw:
        if a.comment_count == 0:
            continue
        try:
            fetched = fetch_comments_for_article(
                cafe_id,
                a.article_id,
                gubun=gubun,
                cafe_name=cafe_name,
                article_title=a.subject,
                fetch_comment_page=fetch_comment_page,
            )
        except CommentsRestrictedError as e:
            print(f"  [회원전용] articleId={a.article_id}: {e.reason}")
            restricted_comment_count += a.comment_count
            continue
        except Exception as e:  # noqa: BLE001
            # 게시글 하나의 댓글 수집 실패로 그 카페의 게시글 데이터까지
            # 통째로 버려지면 안 된다 — 이 게시글만 건너뛴다. 알려진
            # 회원전용 제한이 아닌 예상 밖의 실패이므로 restricted count에는
            # 넣지 않는다 (호출부의 T-04 검증이 이 불일치를 그대로 잡아냄).
            print(f"  [SKIP 댓글] articleId={a.article_id} 실패: {e}")
            continue
        all_comments.extend(fetched)
    return articles, all_comments, restricted_comment_count
