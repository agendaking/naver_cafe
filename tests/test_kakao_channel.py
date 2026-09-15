"""카카오톡 채널 게시물 수집(kakao_channel.py) 검증.

2026-09-16 실제 게시물(pf.kakao.com/_XNxdxkxl/114504145, 좋아요13/댓글85)을
브라우저 네트워크 탭으로 직접 확인해서 얻은 실제 응답 형태를 그대로 재현한다.
"""

from __future__ import annotations

import pytest

from naver_cafe_crawler.kakao_channel import (
    KakaoFetchError,
    fetch_kakao_post_comments,
    fetch_kakao_post_meta,
    parse_kakao_post_url,
)


def test_parse_kakao_post_url():
    profile_id, post_id = parse_kakao_post_url("https://pf.kakao.com/_XNxdxkxl/114504145")
    assert profile_id == "_XNxdxkxl"
    assert post_id == "114504145"


def test_parse_kakao_post_url_invalid_raises():
    with pytest.raises(ValueError, match="profileId/postId"):
        parse_kakao_post_url("https://pf.kakao.com/notapost")


class FakeResponse:
    def __init__(self, *, json_data, status=200):
        self._json = json_data
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._json


class FakeSession:
    """URL별로 호출 순서대로 소비되는 응답 큐 — since 커서 페이지네이션 검증용."""

    def __init__(self, queues: dict[str, list[FakeResponse]]):
        self.queues = {k: list(v) for k, v in queues.items()}
        self.calls: list[tuple[str, dict | None]] = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append((url, params))
        queue = self.queues.get(url)
        if not queue:
            raise AssertionError(f"unexpected/exhausted URL: {url} params={params}")
        return queue.pop(0)


META_URL = "https://pf.kakao.com/rocket-web/web/profiles/_XNxdxkxl/posts/114504145"
COMMENTS_URL = "https://pf.kakao.com/rocket-web/web/profiles/_XNxdxkxl/posts/114504145/comments"


def _comment_item(id_, nickname, text, created_at_ms):
    return {
        "id": id_,
        "author": {"nickname": nickname},
        "contents": [{"t": "text", "v": text}],
        "created_at": created_at_ms,
    }


def test_fetch_kakao_post_meta():
    session = FakeSession({
        META_URL: [FakeResponse(json_data={
            "like_count": 13,
            "comment_count": 85,
            "share_count": 6,
            "title": "[이벤트] O/X 퀴즈! 추석 귀성길 준비, 정답은?",
        })],
    })
    meta = fetch_kakao_post_meta("_XNxdxkxl", "114504145", session=session)
    assert meta.like_count == 13
    assert meta.comment_count == 85
    assert meta.share_count == 6


def test_fetch_kakao_post_meta_malformed_raises():
    session = FakeSession({META_URL: [FakeResponse(json_data={"oops": True})]})
    with pytest.raises(KakaoFetchError, match="메타 파싱 실패"):
        fetch_kakao_post_meta("_XNxdxkxl", "114504145", session=session)


def test_fetch_kakao_post_comments_paginates_with_since_cursor():
    # 2026-09-07 09:00 KST epoch ms 기준 값 (정확한 값 자체보다 왕복 변환 검증 목적)
    page1 = FakeResponse(json_data={
        "has_next": True,
        "items": [_comment_item("id_2", "둘째", "정답 O", 1789344237000), _comment_item("id_1", "첫째", "정답:O", 1789300000000)],
    })
    page2 = FakeResponse(json_data={
        "has_next": False,
        "items": [_comment_item("id_0", "막내", "O", 1789200000000)],
    })
    session = FakeSession({COMMENTS_URL: [page1, page2]})

    comments = fetch_kakao_post_comments("_XNxdxkxl", "114504145", session=session)

    assert [c.writer for c in comments] == ["둘째", "첫째", "막내"]
    assert comments[0].content == "정답 O"
    # 페이지네이션이 이전 페이지 마지막 항목의 id를 since로 넘겼는지 확인
    assert session.calls[0][1] == {"direction": "backward", "sort": "desc"}
    assert session.calls[1][1] == {"direction": "backward", "sort": "desc", "since": "id_1"}


def test_fetch_kakao_post_comments_empty_page_stops():
    session = FakeSession({COMMENTS_URL: [FakeResponse(json_data={"has_next": True, "items": []})]})
    comments = fetch_kakao_post_comments("_XNxdxkxl", "114504145", session=session)
    assert comments == []


def test_fetch_kakao_post_comments_joins_multi_line_text_contents():
    page = FakeResponse(json_data={
        "has_next": False,
        "items": [{
            "id": "id_9",
            "author": {"nickname": "닉네임"},
            "contents": [{"t": "text", "v": "정답:O"}, {"t": "text", "v": "안전운전 하세요"}],
            "created_at": 1789344237000,
        }],
    })
    session = FakeSession({COMMENTS_URL: [page]})
    comments = fetch_kakao_post_comments("_XNxdxkxl", "114504145", session=session)
    assert comments[0].content == "정답:O\n안전운전 하세요"
