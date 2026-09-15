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
    fetch_naver_blog_comments,
    fetch_naver_blog_post_stats,
    fetch_naver_blog_stats,
    fetch_tistory_stats,
    find_rss_entry,
    parse_naver_blog_url,
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


# --- 네이버 블로그 댓글 원문 (2026-09-16, 형님이 브라우저에서 직접 캡처해준
# apis.naver.com/commentBox/cbox/web_naver_list_json.json 요청 기반) ---


class QueueFakeSession:
    """URL별로 호출 순서대로 소비되는 응답 큐 — page 파라미터 페이지네이션 검증용."""

    def __init__(self, queues: dict[str, list[FakeResponse]]):
        self.queues = {k: list(v) for k, v in queues.items()}
        self.calls: list[tuple[str, dict | None]] = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append((url, params))
        queue = self.queues.get(url)
        if not queue:
            raise AssertionError(f"unexpected/exhausted URL: {url} params={params}")
        return queue.pop(0)


POSTVIEW_URL = "https://blog.naver.com/PostView.naver"
COMMENT_LIST_URL = "https://apis.naver.com/commentBox/cbox/web_naver_list_json.json"
POSTVIEW_HTML_WITH_BLOGNO = "<script>var blogNo = '60122265';</script>"


def _naver_comment_item(comment_no, user_name, contents, reg_time):
    return {"commentNo": comment_no, "userName": user_name, "contents": contents, "regTime": reg_time}


def test_fetch_naver_blog_comments_single_page():
    session = QueueFakeSession({
        POSTVIEW_URL: [FakeResponse(text=POSTVIEW_HTML_WITH_BLOGNO)],
        COMMENT_LIST_URL: [FakeResponse(json_data={"result": {
            "commentList": [
                _naver_comment_item("1", "심철용", "정답 : O<br><br>안전운전 하세요", "2026-09-07T12:45:00+0900"),
            ],
            "pageModel": {"totalPages": 1},
        }})],
    })

    comments = fetch_naver_blog_comments("kumhotire_official", "224403416495", session=session)

    assert len(comments) == 1
    assert comments[0].writer == "심철용"
    assert comments[0].content == "정답 : O\n\n안전운전 하세요"
    assert comments[0].submitted_at == "2026.09.07 12:45"
    # objectId가 blogNo_201_logNo 형식으로 조립됐는지 확인
    _, params = session.calls[1]
    assert params["objectId"] == "60122265_201_224403416495"
    assert params["page"] == "1"


def test_fetch_naver_blog_comments_paginates_across_pages():
    session = QueueFakeSession({
        POSTVIEW_URL: [FakeResponse(text=POSTVIEW_HTML_WITH_BLOGNO)],
        COMMENT_LIST_URL: [
            FakeResponse(json_data={"result": {
                "commentList": [_naver_comment_item(str(i), f"user{i}", "O", "2026-09-07T10:00:00+0900") for i in range(50)],
                "pageModel": {"totalPages": 2},
            }}),
            FakeResponse(json_data={"result": {
                "commentList": [_naver_comment_item(str(i), f"user{i}", "O", "2026-09-07T10:00:00+0900") for i in range(50, 89)],
                "pageModel": {"totalPages": 2},
            }}),
        ],
    })

    comments = fetch_naver_blog_comments("kumhotire_official", "224403416495", session=session)

    assert len(comments) == 89
    comment_list_calls = [p for u, p in session.calls if u == COMMENT_LIST_URL]
    assert [c["page"] for c in comment_list_calls] == ["1", "2"]


def test_fetch_naver_blog_comments_strips_mention_tags_and_unescapes_entities():
    session = QueueFakeSession({
        POSTVIEW_URL: [FakeResponse(text=POSTVIEW_HTML_WITH_BLOGNO)],
        COMMENT_LIST_URL: [FakeResponse(json_data={"result": {
            "commentList": [_naver_comment_item(
                "1", "옹이",
                "고마워&lt;3<br><a href='#'>@ykszym</a> 축하해",
                "2026-09-07T21:16:00+0900",
            )],
            "pageModel": {"totalPages": 1},
        }})],
    })
    comments = fetch_naver_blog_comments("kumhotire_official", "224403416495", session=session)
    assert comments[0].content == "고마워<3\n@ykszym 축하해"


def test_fetch_naver_blog_comments_blogno_not_found_raises():
    session = QueueFakeSession({POSTVIEW_URL: [FakeResponse(text="<html>no blogno here</html>")]})
    with pytest.raises(BlogFetchError, match="blogNo를 페이지에서 못 찾음"):
        fetch_naver_blog_comments("kumhotire_official", "224403416495", session=session)


def test_parse_naver_blog_url():
    blog_id, log_no = parse_naver_blog_url("https://blog.naver.com/kumhotire_official/224403416495")
    assert blog_id == "kumhotire_official"
    assert log_no == "224403416495"


def test_parse_naver_blog_url_invalid_raises():
    with pytest.raises(ValueError, match="blogId/logNo"):
        parse_naver_blog_url("https://blog.naver.com/")


def test_fetch_naver_blog_post_stats_by_known_url_skips_rss_search():
    session = FakeSession({
        "https://apis.naver.com/blogserver/like/v1/search/contents": FakeResponse(
            json_data={"contents": [{"reactions": [{"count": 84}]}]}
        ),
        "https://blog.naver.com/PostView.naver": FakeResponse(
            text='<em id="floating_bottom_commentCount">139</em>'
        ),
    })
    stats = fetch_naver_blog_post_stats("kumhotire_official", "224403416495", session=session)
    assert stats.likes == 84
    assert stats.comment_count == 139


def test_fetch_naver_blog_comments_malformed_list_raises():
    session = QueueFakeSession({
        POSTVIEW_URL: [FakeResponse(text=POSTVIEW_HTML_WITH_BLOGNO)],
        COMMENT_LIST_URL: [FakeResponse(json_data={"oops": True})],
    })
    with pytest.raises(BlogFetchError, match="댓글 목록 파싱 실패"):
        fetch_naver_blog_comments("kumhotire_official", "224403416495", session=session)
