"""날짜 기반 이벤트 현황판 갱신(event_status_report.py) 검증."""

from __future__ import annotations

from naver_cafe_crawler.event_status_report import (
    collect_event_comments,
    find_cafe_link_result,
)
from naver_cafe_crawler.naver_api import CommentsRestrictedError


def _article(article_id, subject, day, read=0, like=0, comment=0):
    # 2026-09-{day} 11:00 KST 부근의 timestamp를 만든다.
    from datetime import datetime

    ts_ms = int(datetime(2026, 9, day, 11, 0).timestamp() * 1000)
    return {
        "type": "ARTICLE",
        "item": {
            "articleId": article_id,
            "subject": subject,
            "writeDateTimestamp": ts_ms,
            "readCount": read,
            "likeCount": like,
            "commentCount": comment,
            "writerInfo": {"nickName": "금호타이어", "memberLevelName": "매니저"},
        },
    }


def fake_fetch_page_single_match(cafe_id, menu_id, page, **kwargs):
    if page > 1:
        return {"result": {"articleList": [], "pageInfo": {}}}
    return {
        "result": {
            "articleList": [
                _article(1, "잡담글", day=11, read=5),
                _article(2, "[이벤트] O/X 퀴즈", day=7, read=352, like=10, comment=83),
            ],
            "pageInfo": {"lastNavigationPageNumber": 1, "visibleNextButton": False},
        }
    }


def fake_fetch_page_no_match(cafe_id, menu_id, page, **kwargs):
    if page > 1:
        return {"result": {"articleList": [], "pageInfo": {}}}
    return {
        "result": {
            "articleList": [_article(1, "잡담글", day=11, read=5)],
            "pageInfo": {"lastNavigationPageNumber": 1, "visibleNextButton": False},
        }
    }


def fake_fetch_page_ambiguous(cafe_id, menu_id, page, **kwargs):
    if page > 1:
        return {"result": {"articleList": [], "pageInfo": {}}}
    return {
        "result": {
            "articleList": [
                _article(1, "[이벤트] O/X 퀴즈", day=7, read=352, like=10, comment=83),
                _article(2, "다른 회원의 잡담", day=7, read=3, like=0, comment=0),
            ],
            "pageInfo": {"lastNavigationPageNumber": 1, "visibleNextButton": False},
        }
    }


def test_find_cafe_link_result_matches_by_date():
    r = find_cafe_link_result(
        "카니발 포에버",
        "https://cafe.naver.com/f-e/cafes/10124067/menus/3278",
        2026,
        9,
        7,
        fetch_page=fake_fetch_page_single_match,
    )
    assert r.found is True
    assert r.article.read_count == 352
    assert r.article.like_count == 10
    assert r.article.comment_count == 83
    assert r.ambiguous_matches == 0


def test_find_cafe_link_result_no_post_on_date():
    r = find_cafe_link_result(
        "카니발 포에버",
        "https://cafe.naver.com/f-e/cafes/10124067/menus/3278",
        2026,
        9,
        7,
        fetch_page=fake_fetch_page_no_match,
    )
    assert r.found is False
    assert r.article is None


def test_find_cafe_link_result_picks_highest_views_when_ambiguous():
    r = find_cafe_link_result(
        "카니발 포에버",
        "https://cafe.naver.com/f-e/cafes/10124067/menus/3278",
        2026,
        9,
        7,
        fetch_page=fake_fetch_page_ambiguous,
    )
    assert r.found is True
    assert r.ambiguous_matches == 2
    assert r.article.article_id == 1  # 조회수 352 > 3


def test_find_cafe_link_result_bad_url_does_not_raise():
    r = find_cafe_link_result("이상한카페", "https://example.com/not-a-cafe", 2026, 9, 7)
    assert r.found is False
    assert r.error is not None


def test_collect_event_comments_only_fetches_found_cafes_with_comments():
    found = find_cafe_link_result(
        "카니발 포에버",
        "https://cafe.naver.com/f-e/cafes/10124067/menus/3278",
        2026,
        9,
        7,
        fetch_page=fake_fetch_page_single_match,
    )
    not_found = find_cafe_link_result(
        "쏘렌토 멤버스",
        "https://cafe.naver.com/f-e/cafes/10037204/menus/3077",
        2026,
        9,
        7,
        fetch_page=fake_fetch_page_no_match,
    )

    calls = []

    def fake_comment_page(cafe_id, article_id, page, **kwargs):
        calls.append((cafe_id, article_id))
        return {
            "result": {
                "comments": {
                    "items": [
                        {"writer": {"nick": "참여자1"}, "content": "저요!", "updateDate": 1788747024830, "isDeleted": False},
                    ]
                },
                "hasNext": False,
            }
        }

    comments, restricted = collect_event_comments([found, not_found], fetch_comment_page=fake_comment_page)
    assert restricted == 0
    assert len(comments) == 1
    assert comments[0].cafe_name == "카니발 포에버"
    assert comments[0].writer == "참여자1"
    assert " " in comments[0].submitted_at  # 날짜 + 시:분 포맷
    assert calls == [("10124067", 2)]


def test_collect_event_comments_tracks_restricted():
    found = find_cafe_link_result(
        "카니발 포에버",
        "https://cafe.naver.com/f-e/cafes/10124067/menus/3278",
        2026,
        9,
        7,
        fetch_page=fake_fetch_page_single_match,
    )

    def restricted_fetch(cafe_id, article_id, page, **kwargs):
        raise CommentsRestrictedError(cafe_id, article_id, "카페 멤버만 읽을 수 있는 게시글입니다.")

    comments, restricted = collect_event_comments([found], fetch_comment_page=restricted_fetch)
    assert comments == []
    assert restricted == 1
