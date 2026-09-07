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

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

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
