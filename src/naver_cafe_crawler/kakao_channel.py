"""카카오톡 채널 게시물(소식) 좋아요/댓글수 + 댓글 원문 수집.

카카오톡 채널 소식 페이지(pf.kakao.com/{profileId}/{postId})는 React SPA라 정적
HTML에는 아무 데이터도 없지만, 페이지가 호출하는 rocket-web 내부 API는 로그인
없이 그대로 호출 가능하다 (2026-09-16 브라우저 네트워크 탭으로 직접 확인):

- 게시물 메타: GET /rocket-web/web/profiles/{profileId}/posts/{postId}
  -> like_count, comment_count, share_count (조회수 필드는 없음 — 카카오톡 채널은
     게시물별 조회수를 공개하지 않는다, UI에도 표시 안 됨)
- 댓글 목록: GET /rocket-web/web/profiles/{profileId}/posts/{postId}/comments
             ?direction=backward&sort=desc[&since={마지막 댓글 id}]
  -> 한 페이지 15개, `since`에 방금 받은 마지막 댓글의 id를 넣어 다음 페이지 요청
     (무한 스크롤 방식). `has_next`가 false거나 items가 비면 종료.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import requests

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

_KST = timezone(timedelta(hours=9))

_URL_RE = re.compile(r"pf\.kakao\.com/([^/]+)/(\d+)")


class KakaoFetchError(Exception):
    """카카오톡 채널 게시물 수집 실패."""


@dataclass(frozen=True)
class KakaoPostMeta:
    like_count: int
    comment_count: int
    share_count: int
    title: str


@dataclass(frozen=True)
class KakaoComment:
    writer: str
    content: str
    submitted_at: str  # "2026.09.07 11:23" (KST)


def parse_kakao_post_url(url: str) -> tuple[str, str]:
    """소식 URL에서 (profileId, postId)를 뽑는다. 예: pf.kakao.com/_XNxdxkxl/114504145"""
    m = _URL_RE.search(url)
    if not m:
        raise ValueError(f"카카오톡 채널 게시물 URL에서 profileId/postId를 못 찾음: {url}")
    return m.group(1), m.group(2)


def fetch_kakao_post_meta(
    profile_id: str, post_id: str, *, session: requests.Session | None = None
) -> KakaoPostMeta:
    sess = session or requests.Session()
    resp = sess.get(
        f"https://pf.kakao.com/rocket-web/web/profiles/{profile_id}/posts/{post_id}",
        headers={"User-Agent": USER_AGENT},
        timeout=10,
    )
    resp.raise_for_status()
    try:
        data = resp.json()
        return KakaoPostMeta(
            like_count=data["like_count"],
            comment_count=data["comment_count"],
            share_count=data["share_count"],
            title=data["title"],
        )
    except (ValueError, KeyError) as e:
        raise KakaoFetchError(f"카카오톡 게시물 메타 파싱 실패 ({profile_id}/{post_id}): {e}") from e


def _comment_text(item: dict) -> str:
    return "\n".join(c.get("v", "") for c in item.get("contents", []) if c.get("t") == "text")


def fetch_kakao_post_comments(
    profile_id: str,
    post_id: str,
    *,
    session: requests.Session | None = None,
    page_limit: int = 200,
) -> list[KakaoComment]:
    """게시물의 모든 댓글을 `since` 커서로 페이지네이션하며 끝까지 모은다.

    page_limit은 무한루프 방지용 안전장치(카카오 쪽 응답 형식이 바뀌어 has_next가
    영원히 true로 오는 등의 이상 상황 대비)이지 정상 동작에서 도달할 값이 아니다.
    """
    sess = session or requests.Session()
    url = f"https://pf.kakao.com/rocket-web/web/profiles/{profile_id}/posts/{post_id}/comments"

    comments: list[KakaoComment] = []
    since: str | None = None
    for _ in range(page_limit):
        params = {"direction": "backward", "sort": "desc"}
        if since:
            params["since"] = since
        resp = sess.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=10)
        resp.raise_for_status()
        try:
            data = resp.json()
        except ValueError as e:
            raise KakaoFetchError(f"카카오톡 댓글 목록 파싱 실패 ({profile_id}/{post_id}): {e}") from e

        items = data.get("items", [])
        if not items:
            break
        for item in items:
            dt = datetime.fromtimestamp(item["created_at"] / 1000, tz=_KST)
            comments.append(
                KakaoComment(
                    writer=item.get("author", {}).get("nickname", ""),
                    content=_comment_text(item),
                    submitted_at=dt.strftime("%Y.%m.%d %H:%M"),
                )
            )
        since = items[-1]["id"]
        if not data.get("has_next"):
            break

    return comments
