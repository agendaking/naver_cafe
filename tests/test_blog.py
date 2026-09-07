"""T-07 승인 기준 검증: 제목/발행일로 그 달의 블로그·티스토리 게시글을
정확히 찾아내는지, 좋아요/댓글 파싱이 맞는지, 실패 시 명확한 예외로
스킵 가능한지 확인.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta

import pytest

from naver_cafe_crawler.blog import (
    BlogFetchError,
    RssEntry,
    fetch_naver_blog_stats,
    fetch_tistory_stats,
    find_rss_entry,
)

KST = timezone(timedelta(hours=9))

ENTRIES = [
    RssEntry(title="[이벤트] O/X 퀴즈! 추석 귀성길 준비, 정답은?", link="https://blog.naver.com/kumhotire_official/224403416495", pub_date=datetime(2026, 9, 7, tzinfo=KST)),
    RssEntry(title="[이벤트] 휴가철 함께 떠나고 싶은 금호타이어는?", link="https://blog.naver.com/kumhotire_official/224366394547", pub_date=datetime(2026, 8, 3, tzinfo=KST)),
]


def test_find_rss_entry_by_title():
    entry = find_rss_entry(ENTRIES, title="휴가철 함께 떠나고 싶은 금호타이어는?")
    assert entry.link.endswith("224366394547")


def test_find_rss_entry_by_title_ignores_cafe_style_tags():
    entry = find_rss_entry(ENTRIES, title="[공지] 휴가철 함께 떠나고 싶은 금호타이어는?")
    assert entry.link.endswith("224366394547")


def test_find_rss_entry_by_date():
    entry = find_rss_entry(ENTRIES, target_date="2026-08-03")
    assert entry.link.endswith("224366394547")


def test_find_rss_entry_no_match_raises():
    with pytest.raises(BlogFetchError, match="일치하는 게시글을 찾지 못함"):
        find_rss_entry(ENTRIES, title="전혀 다른 제목")


def test_find_rss_entry_requires_title_or_date():
    with pytest.raises(ValueError):
        find_rss_entry(ENTRIES)


# --- 네트워크 계층: 가짜 세션으로 파싱 로직만 검증 ---

class FakeResponse:
    def __init__(self, *, content=None, text=None, json_data=None, status=200):
        self.content = content
        self.text = text
        self._json = json_data
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        if self._json is None:
            raise ValueError("no json")
        return self._json


NAVER_RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<item>
<title><![CDATA[[이벤트] 휴가철 함께 떠나고 싶은 금호타이어는?]]></title>
<link><![CDATA[https://blog.naver.com/kumhotire_official/224366394547?fromRss=true]]></link>
<pubDate>Mon, 03 Aug 2026 09:59:00 +0900</pubDate>
</item>
</channel></rss>"""


class FakeSession:
    def __init__(self, responses: dict[str, FakeResponse]):
        self.responses = responses
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append((url, params))
        key = url
        if key not in self.responses:
            raise AssertionError(f"unexpected URL: {url} params={params}")
        return self.responses[key]


def test_fetch_naver_blog_stats_end_to_end():
    comment_html = '<em id="floating_bottom_commentCount">29</em>'
    session = FakeSession({
        "https://rss.blog.naver.com/kumhotire_official.xml": FakeResponse(content=NAVER_RSS_XML.encode("utf-8")),
        "https://apis.naver.com/blogserver/like/v1/search/contents": FakeResponse(
            json_data={"contents": [{"reactions": [{"count": 22}]}]}
        ),
        "https://blog.naver.com/PostView.naver": FakeResponse(text=comment_html),
    })

    stats = fetch_naver_blog_stats(
        "kumhotire_official", title="휴가철 함께 떠나고 싶은 금호타이어는?", session=session
    )
    assert stats.platform == "naver_blog"
    assert stats.likes == 22
    assert stats.comments == 29
    assert "224366394547" in stats.url


def test_fetch_naver_blog_stats_bad_like_response_raises_blogfetcherror():
    session = FakeSession({
        "https://rss.blog.naver.com/kumhotire_official.xml": FakeResponse(content=NAVER_RSS_XML.encode("utf-8")),
        "https://apis.naver.com/blogserver/like/v1/search/contents": FakeResponse(json_data={"unexpected": "shape"}),
        "https://blog.naver.com/PostView.naver": FakeResponse(text='<em id="floating_bottom_commentCount">1</em>'),
    })
    with pytest.raises(BlogFetchError, match="좋아요 파싱 실패"):
        fetch_naver_blog_stats("kumhotire_official", title="휴가철 함께 떠나고 싶은 금호타이어는?", session=session)


TISTORY_RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<item>
<title>[이벤트] 휴가철 함께 떠나고 싶은 금호타이어는?</title>
<link>https://blog.kumhotire.co.kr/1613</link>
<pubDate>Mon, 3 Aug 2026 09:59:00 +0900</pubDate>
</item>
</channel></rss>"""


def test_fetch_tistory_stats_end_to_end():
    session = FakeSession({
        "https://blog.kumhotire.co.kr/rss": FakeResponse(content=TISTORY_RSS_XML.encode("utf-8")),
        "https://blog.kumhotire.co.kr/reaction": FakeResponse(json_data={"data": {"reactionCounter": {"sum": 5}}}),
        "https://blog.kumhotire.co.kr/m/api/1613/comment/count": FakeResponse(json_data={"data": {"count": 3}}),
    })
    stats = fetch_tistory_stats(
        "blog.kumhotire.co.kr", title="휴가철 함께 떠나고 싶은 금호타이어는?", session=session
    )
    assert stats.platform == "tistory"
    assert stats.likes == 5
    assert stats.comments == 3
    assert stats.url == "https://blog.kumhotire.co.kr/1613"


def test_fetch_tistory_stats_by_date():
    session = FakeSession({
        "https://blog.kumhotire.co.kr/rss": FakeResponse(content=TISTORY_RSS_XML.encode("utf-8")),
        "https://blog.kumhotire.co.kr/reaction": FakeResponse(json_data={"data": {"reactionCounter": {"sum": 5}}}),
        "https://blog.kumhotire.co.kr/m/api/1613/comment/count": FakeResponse(json_data={"data": {"count": 3}}),
    })
    stats = fetch_tistory_stats("blog.kumhotire.co.kr", target_date="2026-08-03", session=session)
    assert stats.likes == 5


def test_fetch_tistory_stats_malformed_comment_json_raises_blogfetcherror():
    session = FakeSession({
        "https://blog.kumhotire.co.kr/rss": FakeResponse(content=TISTORY_RSS_XML.encode("utf-8")),
        "https://blog.kumhotire.co.kr/reaction": FakeResponse(json_data={"data": {"reactionCounter": {"sum": 5}}}),
        "https://blog.kumhotire.co.kr/m/api/1613/comment/count": FakeResponse(json_data={"oops": True}),
    })
    with pytest.raises(BlogFetchError, match="댓글수 파싱 실패"):
        fetch_tistory_stats("blog.kumhotire.co.kr", title="휴가철 함께 떠나고 싶은 금호타이어는?", session=session)
