"""네이버 블로그 / 티스토리 수집 (PRD 4장, T-07).

이 블로그들의 게시글 URL은 매달 바뀐다(글이 새로 올라가므로) — 그래서
고정 URL을 입력받지 않는다. 대신 각 플랫폼의 RSS 피드(로그인 불필요)에서
제목 또는 발행일로 그 달의 게시글을 찾은 다음, 좋아요/댓글 수를 가져온다.

2026-09-07 직접 확인 (금호타이어 공식 계정 기준, 로그인 불필요):
- 네이버 블로그(blog.naver.com/kumhotire_official):
  RSS: https://rss.blog.naver.com/{blogId}.xml
  좋아요: https://apis.naver.com/blogserver/like/v1/search/contents
          ?q=BLOG[{blogId}_{logNo}]&pool=blogid&cssIds=MULTI_PC,BLOG_PC
  댓글 개수: PostView.naver 페이지 HTML에 <em id="floating_bottom_commentCount"> 로 임베드
  댓글 원문: apis.naver.com/commentBox/cbox/web_naver_list_json.json (아래 참고, 2026-09-16
             형님이 브라우저 Network 탭에서 직접 캡처해준 요청으로 확인 — 사내 정책상
             blog.naver.com이 브라우저 도구로 막혀 있어 이 부분만 직접 확인 불가했음)
- 티스토리(blog.kumhotire.co.kr, 커스텀 도메인):
  RSS: https://{domain}/rss
  좋아요: https://{domain}/reaction?entryId={postId} -> reactionCounter.like
  댓글: https://{domain}/m/api/{postId}/comment/count -> data.count
  (PRD가 말한 "공식 API 종료"는 예전 얘기고, 지금은 이 비공식 프론트엔드
  API가 동작한다 — 다만 스킨/버전에 따라 언제든 깨질 수 있으므로 실패를
  BlogFetchError로 명확히 구분해서 호출부가 스킵/로그하게 한다.)
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

import requests

from .articles import normalize_title

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


class BlogFetchError(Exception):
    """블로그/티스토리 수집 중 실패 — 호출부가 이 항목만 스킵하고 로그를
    남긴 뒤 전체 배치는 계속 진행해야 한다 (PRD 4장)."""


@dataclass(frozen=True)
class RssEntry:
    title: str
    link: str
    pub_date: datetime


@dataclass(frozen=True)
class BlogPostStats:
    platform: str  # "naver_blog" | "tistory"
    title: str
    url: str
    pub_date: datetime
    likes: int
    comments: int


def _fetch_rss_entries(rss_url: str, *, session: requests.Session | None = None) -> list[RssEntry]:
    sess = session or requests.Session()
    resp = sess.get(rss_url, headers={"User-Agent": USER_AGENT}, timeout=10)
    resp.raise_for_status()
    try:
        root = ElementTree.fromstring(resp.content)
    except ElementTree.ParseError as e:
        raise BlogFetchError(f"RSS 파싱 실패 ({rss_url}): {e}") from e

    entries = []
    for item in root.iter("item"):
        title_el = item.find("title")
        link_el = item.find("link")
        pub_el = item.find("pubDate")
        if title_el is None or link_el is None or pub_el is None:
            continue
        try:
            pub_date = parsedate_to_datetime(pub_el.text)
        except (TypeError, ValueError):
            continue
        entries.append(RssEntry(title=(title_el.text or "").strip(), link=(link_el.text or "").strip(), pub_date=pub_date))
    return entries


def find_rss_entry(
    entries: list[RssEntry], *, title: str | None = None, target_date: str | None = None
) -> RssEntry:
    """제목(정규화 매칭) 우선, 없으면 발행일(YYYY-MM-DD)로 찾는다.

    title과 target_date 중 최소 하나는 있어야 한다.
    """
    if title is None and target_date is None:
        raise ValueError("title 또는 target_date 중 하나는 지정해야 함")

    if title is not None:
        key = normalize_title(title)
        for e in entries:
            if normalize_title(e.title) == key:
                return e

    if target_date is not None:
        for e in entries:
            if e.pub_date.strftime("%Y-%m-%d") == target_date:
                return e

    raise BlogFetchError(
        f"RSS에서 일치하는 게시글을 찾지 못함 (title={title!r}, target_date={target_date!r})"
    )


_NAVER_BLOG_URL_RE = re.compile(r"blog\.naver\.com/([^/?]+)/(\d+)")


def parse_naver_blog_url(url: str) -> tuple[str, str]:
    """게시글 URL에서 (blogId, logNo)를 뽑는다. 예: blog.naver.com/kumhotire_official/224403416495"""
    m = _NAVER_BLOG_URL_RE.search(url)
    if not m:
        raise ValueError(f"네이버 블로그 URL에서 blogId/logNo를 못 찾음: {url}")
    return m.group(1), m.group(2)


@dataclass(frozen=True)
class NaverBlogPostStats:
    likes: int
    comment_count: int


def fetch_naver_blog_post_stats(
    blog_id: str, log_no: str, *, session: requests.Session | None = None
) -> NaverBlogPostStats:
    """URL이 이미 확정된 게시글의 좋아요/댓글수만 바로 가져온다 (RSS 제목/날짜 검색 불필요)."""
    sess = session or requests.Session()
    return NaverBlogPostStats(
        likes=_fetch_naver_blog_likes(blog_id, log_no, session=sess),
        comment_count=_fetch_naver_blog_comments(blog_id, log_no, session=sess),
    )


def fetch_naver_blog_stats(
    blog_id: str,
    *,
    title: str | None = None,
    target_date: str | None = None,
    session: requests.Session | None = None,
) -> BlogPostStats:
    sess = session or requests.Session()
    entries = _fetch_rss_entries(f"https://rss.blog.naver.com/{blog_id}.xml", session=sess)
    entry = find_rss_entry(entries, title=title, target_date=target_date)

    m = re.search(r"/(\d+)(?:\?|$)", entry.link)
    if not m:
        raise BlogFetchError(f"네이버 블로그 링크에서 logNo를 못 찾음: {entry.link}")
    log_no = m.group(1)

    likes = _fetch_naver_blog_likes(blog_id, log_no, session=sess)
    comments = _fetch_naver_blog_comments(blog_id, log_no, session=sess)

    return BlogPostStats(
        platform="naver_blog",
        title=entry.title,
        url=f"https://blog.naver.com/{blog_id}/{log_no}",
        pub_date=entry.pub_date,
        likes=likes,
        comments=comments,
    )


def _fetch_naver_blog_likes(blog_id: str, log_no: str, *, session: requests.Session) -> int:
    resp = session.get(
        "https://apis.naver.com/blogserver/like/v1/search/contents",
        params={
            "suppress_response_codes": "true",
            "pool": "blogid",
            "q": f"BLOG[{blog_id}_{log_no}]",
            "isDuplication": "false",
            "cssIds": "MULTI_PC,BLOG_PC",
        },
        headers={"User-Agent": USER_AGENT, "Referer": f"https://blog.naver.com/{blog_id}/{log_no}"},
        timeout=10,
    )
    resp.raise_for_status()
    try:
        data = resp.json()
        reactions = data["contents"][0]["reactions"]
        return sum(r["count"] for r in reactions)
    except (ValueError, KeyError, IndexError, TypeError) as e:
        raise BlogFetchError(f"네이버 블로그 좋아요 파싱 실패 ({blog_id}/{log_no}): {e}") from e


_COMMENT_COUNT_RE = re.compile(
    r'id="floating_bottom_commentCount"[^>]*>\s*([\d,]+)\s*<', re.DOTALL
)


def _fetch_naver_blog_comments(blog_id: str, log_no: str, *, session: requests.Session) -> int:
    resp = session.get(
        "https://blog.naver.com/PostView.naver",
        params={"blogId": blog_id, "logNo": log_no},
        headers={"User-Agent": USER_AGENT},
        timeout=10,
    )
    resp.raise_for_status()
    m = _COMMENT_COUNT_RE.search(resp.text)
    if not m:
        raise BlogFetchError(f"네이버 블로그 댓글수를 페이지에서 못 찾음 ({blog_id}/{log_no})")
    return int(m.group(1).replace(",", ""))


@dataclass(frozen=True)
class BlogComment:
    writer: str
    content: str
    submitted_at: str  # "2026.09.13 22:58" (KST, regTime 그대로)


_BLOG_NO_RE = re.compile(r"var\s+blogNo\s*=\s*'(\d+)'")
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")


def _clean_comment_html(raw: str) -> str:
    """댓글 contents는 줄바꿈이 <br>로 온다 — 개행으로 되돌리고 나머지 태그/엔티티 정리."""
    text = _BR_RE.sub("\n", raw or "")
    text = _TAG_RE.sub("", text)
    return html.unescape(text).strip()


def _fetch_naver_blog_no(blog_id: str, log_no: str, *, session: requests.Session) -> str:
    resp = session.get(
        "https://blog.naver.com/PostView.naver",
        params={"blogId": blog_id, "logNo": log_no},
        headers={"User-Agent": USER_AGENT},
        timeout=10,
    )
    resp.raise_for_status()
    m = _BLOG_NO_RE.search(resp.text)
    if not m:
        raise BlogFetchError(f"네이버 블로그 blogNo를 페이지에서 못 찾음 ({blog_id}/{log_no})")
    return m.group(1)


def fetch_naver_blog_comments(
    blog_id: str, log_no: str, *, session: requests.Session | None = None
) -> list[BlogComment]:
    """게시글의 댓글 원문을 전부 가져온다 (대댓글 포함, commentList가 평면 목록으로 줌).

    objectId 형식 `{blogNo}_201_{logNo}`은 페이지 HTML의 댓글 컨테이너 id
    (`naverComment_201_{logNo}`)와 `var blogNo = '...'`에서 확인된 패턴이다.
    "201"은 블로그 댓글의 고정 카테고리 코드로 보인다(게시글마다 다르지 않음).
    """
    sess = session or requests.Session()
    blog_no = _fetch_naver_blog_no(blog_id, log_no, session=sess)
    object_id = f"{blog_no}_201_{log_no}"
    base_params = {
        "ticket": "blog",
        "templateId": "default",
        "pool": "blogid",
        "_cv": "",
        "lang": "ko",
        "pageType": "default",
        "country": "",
        "objectId": object_id,
        "categoryId": "",
        "pageSize": "50",
        "indexSize": "10",
        "groupId": blog_no,
        "listType": "OBJECT",
        "followSize": "5",
        "userType": "MANAGER",
        "useAltSort": "true",
        "replyPageSize": "10",
        "showReply": "true",
    }
    referer = f"https://blog.naver.com/{blog_id}/{log_no}"

    comments: list[BlogComment] = []
    page = 1
    total_pages = 1
    while page <= total_pages:
        resp = sess.get(
            "https://apis.naver.com/commentBox/cbox/web_naver_list_json.json",
            params={**base_params, "page": str(page)},
            headers={"User-Agent": USER_AGENT, "Referer": referer},
            timeout=10,
        )
        resp.raise_for_status()
        try:
            result = resp.json()["result"]
            items = result["commentList"]
            total_pages = result["pageModel"]["totalPages"]
        except (ValueError, KeyError) as e:
            raise BlogFetchError(
                f"네이버 블로그 댓글 목록 파싱 실패 ({blog_id}/{log_no}, page={page}): {e}"
            ) from e
        for it in items:
            dt = datetime.fromisoformat(it["regTime"])
            comments.append(
                BlogComment(
                    writer=it.get("userName", ""),
                    content=_clean_comment_html(it.get("contents", "")),
                    submitted_at=dt.strftime("%Y.%m.%d %H:%M"),
                )
            )
        page += 1

    return comments


def fetch_tistory_stats(
    domain: str,
    *,
    title: str | None = None,
    target_date: str | None = None,
    session: requests.Session | None = None,
) -> BlogPostStats:
    sess = session or requests.Session()
    domain = domain.rstrip("/")
    entries = _fetch_rss_entries(f"https://{domain}/rss", session=sess)
    entry = find_rss_entry(entries, title=title, target_date=target_date)

    m = re.search(r"/(\d+)$", entry.link.rstrip("/"))
    if not m:
        raise BlogFetchError(f"티스토리 링크에서 게시글 ID를 못 찾음: {entry.link}")
    post_id = m.group(1)

    likes = _fetch_tistory_likes(domain, post_id, session=sess)
    comments = _fetch_tistory_comments(domain, post_id, session=sess)

    return BlogPostStats(
        platform="tistory",
        title=entry.title,
        url=f"https://{domain}/{post_id}",
        pub_date=entry.pub_date,
        likes=likes,
        comments=comments,
    )


def _fetch_tistory_likes(domain: str, post_id: str, *, session: requests.Session) -> int:
    resp = session.get(
        f"https://{domain}/reaction",
        params={"entryId": post_id},
        headers={"User-Agent": USER_AGENT, "Referer": f"https://{domain}/{post_id}"},
        timeout=10,
    )
    resp.raise_for_status()
    try:
        data = resp.json()
        return int(data["data"]["reactionCounter"]["sum"])
    except (ValueError, KeyError, TypeError) as e:
        raise BlogFetchError(f"티스토리 좋아요 파싱 실패 ({domain}/{post_id}): {e}") from e


def _fetch_tistory_comments(domain: str, post_id: str, *, session: requests.Session) -> int:
    resp = session.get(
        f"https://{domain}/m/api/{post_id}/comment/count",
        headers={"User-Agent": USER_AGENT, "Referer": f"https://{domain}/{post_id}"},
        timeout=10,
    )
    resp.raise_for_status()
    try:
        data = resp.json()
        return int(data["data"]["count"])
    except (ValueError, KeyError, TypeError) as e:
        raise BlogFetchError(f"티스토리 댓글수 파싱 실패 ({domain}/{post_id}): {e}") from e
