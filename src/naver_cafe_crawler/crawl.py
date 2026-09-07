"""지정 월의 게시글을 카페별로 수집해서 ArticleRecord로 변환.

작성자 정보(writerInfo)도 함께 들고 있게 해서, T-03(경쟁사 공식 계정
필터링)이 같은 fetch 결과를 재사용할 수 있게 한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Iterable

from .articles import ArticleRecord
from .naver_api import fetch_article_page, parse_cafe_menu_ids

FetchPageFn = Callable[..., dict]


@dataclass(frozen=True)
class RawArticle:
    """API가 주는 원본 필드 중 크롤러가 쓰는 것만 뽑은 중간 표현."""

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
