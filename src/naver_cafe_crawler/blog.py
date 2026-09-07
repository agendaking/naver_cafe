"""네이버 블로그 / 티스토리 수집 (PRD 4장, T-07).

이 블로그들의 게시글 URL은 매달 바뀐다(글이 새로 올라가므로) — 그래서
고정 URL을 입력받지 않는다. 대신 각 플랫폼의 RSS 피드(로그인 불필요)에서
제목 또는 발행일로 그 달의 게시글을 찾은 다음, 좋아요/댓글 수를 가져온다.

2026-09-07 직접 확인 (금호타이어 공식 계정 기준, 로그인 불필요):
- 네이버 블로그(blog.naver.com/kumhotire_official):
  RSS: https://rss.blog.naver.com/{blogId}.xml
  좋아요: https://apis.naver.com/blogserver/like/v1/search/contents
          ?q=BLOG[{blogId}_{logNo}]&pool=blogid&cssIds=MULTI_PC,BLOG_PC
  댓글: PostView.naver 페이지 HTML에 <em id="floating_bottom_commentCount"> 로 임베드
- 티스토리(blog.kumhotire.co.kr, 커스텀 도메인):
  RSS: https://{domain}/rss
  좋아요: https://{domain}/reaction?entryId={postId} -> reactionCounter.like
  댓글: https://{domain}/m/api/{postId}/comment/count -> data.count
  (PRD가 말한 "공식 API 종료"는 예전 얘기고, 지금은 이 비공식 프론트엔드
  API가 동작한다 — 다만 스킨/버전에 따라 언제든 깨질 수 있으므로 실패를
  BlogFetchError로 명확히 구분해서 호출부가 스킵/로그하게 한다.)
"""

from __future__ import annotations

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
