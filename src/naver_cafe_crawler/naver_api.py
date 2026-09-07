"""네이버 카페 게시판 게시글 목록 조회.

2026-09-07 직접 확인: 로그인 없이 `cafe-boardlist-api` JSON API를 순수
HTTP GET으로 호출하면 게시글 목록(제목/일자/조회수/좋아요/댓글수/작성자)이
그대로 내려온다 (Playwright로 렌더링한 DOM과 대조해서 일치 확인함,
카페 10124067/게시판 3278 기준: 8월 8개 게시글 전부 원본 archived xlsx와
제목/날짜 일치, 조회수 등은 시간이 지나 소폭 증가한 정도만 차이).
그래서 브라우저 렌더링 없이 requests만으로 충분하다.
"""

from __future__ import annotations

import re

import requests

BOARD_LIST_API = (
    "https://apis.naver.com/cafe-web/cafe-boardlist-api/v1/cafes/{cafe_id}/menus/{menu_id}/articles"
)

COMMENTS_API = (
    "https://article.cafe.naver.com/gw/v4/cafes/{cafe_id}/articles/{article_id}/comments/pages/{page}"
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

class CommentsRestrictedError(Exception):
    """댓글이 카페 회원 전용으로 막혀 있어 조회할 수 없음 (Naver errorCode 4004).

    2026-09-07 확인: 게시글 목록/조회수/좋아요/댓글수는 로그인 없이 보이지만,
    일부 카페는 댓글 "본문"만 회원 전용으로 막아둔다 (예: 테슬라코리아클럽).
    형님 확인: 이런 카페는 댓글을 빈칸으로 두고 계속 진행하기로 함 — 다른
    실패와 구분해서 다루기 위해 별도 예외로 뺀다.
    """

    def __init__(self, cafe_id: str, article_id: int | str, reason: str):
        self.cafe_id = cafe_id
        self.article_id = article_id
        self.reason = reason
        super().__init__(f"cafe={cafe_id} article={article_id}: {reason}")


_NEW_STYLE_RE = re.compile(r"/cafes/(\d+)/menus/(\d+)")
_OLD_STYLE_RE = re.compile(r"search\.clubid=(\d+).*?search\.menuid=(\d+)")


def parse_cafe_menu_ids(url: str) -> tuple[str, str]:
    """카페 로스터에 저장된 URL에서 (cafeId, menuId)를 뽑아낸다.

    로스터에는 두 가지 URL 형식이 섞여 있다 (2026-09 확인):
    - 신형: https://cafe.naver.com/f-e/cafes/{cafeId}/menus/{menuId}
    - 구형: https://cafe.naver.com/ArticleList.nhn?search.clubid={cafeId}&search.menuid={menuId}
    """
    m = _NEW_STYLE_RE.search(url)
    if m:
        return m.group(1), m.group(2)
    m = _OLD_STYLE_RE.search(url)
    if m:
        return m.group(1), m.group(2)
    raise ValueError(f"카페/게시판 ID를 URL에서 찾을 수 없음: {url}")


def fetch_article_page(
    cafe_id: str,
    menu_id: str,
    page: int,
    *,
    page_size: int = 15,
    session: requests.Session | None = None,
) -> dict:
    """게시판 한 페이지치 원본 JSON을 그대로 반환한다."""
    sess = session or requests.Session()
    resp = sess.get(
        BOARD_LIST_API.format(cafe_id=cafe_id, menu_id=menu_id),
        params={"page": page, "pageSize": page_size, "sortBy": "TIME", "viewType": "L"},
        headers={
            "User-Agent": USER_AGENT,
            "Referer": f"https://cafe.naver.com/f-e/cafes/{cafe_id}/menus/{menu_id}",
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def fetch_comment_page(
    cafe_id: str,
    article_id: int | str,
    page: int,
    *,
    session: requests.Session | None = None,
) -> dict:
    """게시글 한 개의 댓글 목록을 페이지 단위로 그대로 반환한다.

    2026-09-07 직접 확인: listCommentCount(게시판 목록의 댓글수) ==
    displayCommentCount == 실제 반환된 댓글 개수, 여러 게시글로 정확히
    일치함(댓글 삭제/비공개 없는 경우). 로그인 불필요.
    """
    sess = session or requests.Session()
    resp = sess.get(
        COMMENTS_API.format(cafe_id=cafe_id, article_id=article_id, page=page),
        params={"requestFrom": "A", "orderBy": "asc"},
        headers={
            "User-Agent": USER_AGENT,
            "Referer": f"https://cafe.naver.com/f-e/cafes/{cafe_id}/articles/{article_id}",
        },
        timeout=10,
    )
    if resp.status_code == 403:
        try:
            body = resp.json()
        except ValueError:
            body = {}
        error_code = body.get("result", {}).get("errorCode")
        if error_code == "4004":
            reason = body["result"].get("reason", "")
            raise CommentsRestrictedError(cafe_id, article_id, reason)
    resp.raise_for_status()
    return resp.json()
