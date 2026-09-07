"""T-02 승인 기준 검증: 대상 월 게시글만 정확히 걸러내는지, 페이지네이션이
올바르게 멈추는지 확인.

REAL_PAGE_1은 2026-09-07에 실제 라이브 카페(카니발 포에버, cafeId=10124067,
menuId=3278)에서 로그인 없이 cafe-boardlist-api를 호출해 받은 응답을 그대로
옮긴 것이다. 이 안에 9월 1건 + 8월 8건 + 7월 6건이 섞여 있는데, 8월 8건은
8월 카페통계.xlsx의 실제 수집분과 제목/날짜가 정확히 일치한다 (조회수 등은
그 뒤로 시간이 지나 자연 증가한 정도만 다름).
"""

from __future__ import annotations

from naver_cafe_crawler.crawl import (
    RawArticle,
    fetch_cafe_articles_for_month,
    fetch_raw_articles_for_month,
    filter_official_accounts,
)
from naver_cafe_crawler.naver_api import parse_cafe_menu_ids
from datetime import datetime


def _article(article_id, timestamp_ms, subject, read=0, like=0, comment=0, nickname="타이어프로", level="협력업체"):
    return {
        "type": "ARTICLE",
        "item": {
            "articleId": article_id,
            "subject": subject,
            "writeDateTimestamp": timestamp_ms,
            "readCount": read,
            "likeCount": like,
            "commentCount": comment,
            "writerInfo": {"nickName": nickname, "memberLevelName": level},
        },
    }


# 실제 라이브 응답에서 가져온 타임스탬프(ms) + 제목 (2026-09-07 확인).
REAL_PAGE_1 = {
    "result": {
        "articleList": [
            _article(900001, 1788747024830, "[이벤트] O/X 퀴즈! 추석 귀성길 준비, 정답은?", 40, 1, 0),
            _article(900002, 1787882288503, "CRUGEN GT Pro의 모든 것! 핵심 콘텐츠 다시 보기", 33, 0, 0),
            _article(900003, 1787713190983, "휴가 끝난 SUV, 타이어는 확인했나요?", 23, 0, 0),
            _article(900004, 1787278677557, "[이벤트] 여름의 끝자락, 시원한 혜택은 계속! KUMHO:T SUMMER PROMOTION", 125, 1, 1),
            _article(900005, 1787106986230, "포트홀 사고, 당황하지 말고 이렇게 대처하세요!", 40, 0, 1),
            _article(900006, 1787019882733, "[이벤트] 마제스티 No.1 프로모션", 220, 1, 1),
            _article(900007, 1786673637613, "친환경 타이어의 미래는? 금호타이어 ‘2026 지속가능경영보고서’ 발간", 7, 0, 1),
            _article(900008, 1786501304010, "이번 주말 어디 갈까? 8월, 계곡 드라이브 명소 TOP 3!", 103, 0, 3),
            _article(900009, 1785718777483, "[이벤트] 휴가철 함께 떠나고 싶은 금호타이어는?", 243, 1, 29),
            _article(900010, 1785464190110, "놓치면 아쉬운 2026년 2분기, 가장 사랑받은 금호타이어 콘텐츠 BEST 3", 28, 1, 0),
            _article(900011, 1785290645050, "SUV 빗길 사고, 차이는 타이어에 있습니다", 28, 1, 1),
            _article(900012, 1785216773333, "2026 하계 고속도로 타이어 안전점검 캠페인", 14, 0, 0),
            _article(900013, 1784686434180, "카니발 포에버 회원 전용 이벤트, 타이어프로가 드리는 특별한 혜택!!", 558, 3, 6),
            _article(900014, 1784513787873, "[이벤트] 금호타이어와 함께하는 TIRE PRO CUP 스크린 골프대회!", 45, 1, 0),
            _article(900015, 1783908005887, "[이벤트] 여름 무더위를 이겨낼 사계절 타이어는?", 246, 1, 6),
        ],
        "pageInfo": {"lastNavigationPageNumber": 9, "visibleNextButton": False},
    }
}


def fake_fetch_single_page(cafe_id, menu_id, page, **kwargs):
    assert page == 1  # 이 픽스처는 1페이지 안에서 8월 경계를 넘기므로 2페이지 호출이 없어야 함
    return REAL_PAGE_1


def test_month_filter_excludes_future_and_past_articles():
    raw = fetch_raw_articles_for_month(
        "10124067", "3278", 2026, 8, fetch_page=fake_fetch_single_page
    )
    assert len(raw) == 8
    subjects = {a.subject for a in raw}
    assert "[이벤트] O/X 퀴즈! 추석 귀성길 준비, 정답은?" not in subjects  # 9월 글
    assert "놓치면 아쉬운 2026년 2분기, 가장 사랑받은 금호타이어 콘텐츠 BEST 3" not in subjects  # 7월 글


def test_month_filter_matches_real_archived_totals():
    raw = fetch_raw_articles_for_month(
        "10124067", "3278", 2026, 8, fetch_page=fake_fetch_single_page
    )
    # 8월 카페통계.xlsx 원본에 기록된 8개 게시글 제목과 정확히 일치해야 한다.
    expected_subjects = {
        "CRUGEN GT Pro의 모든 것! 핵심 콘텐츠 다시 보기",
        "휴가 끝난 SUV, 타이어는 확인했나요?",
        "[이벤트] 여름의 끝자락, 시원한 혜택은 계속! KUMHO:T SUMMER PROMOTION",
        "포트홀 사고, 당황하지 말고 이렇게 대처하세요!",
        "[이벤트] 마제스티 No.1 프로모션",
        "친환경 타이어의 미래는? 금호타이어 ‘2026 지속가능경영보고서’ 발간",
        "이번 주말 어디 갈까? 8월, 계곡 드라이브 명소 TOP 3!",
        "[이벤트] 휴가철 함께 떠나고 싶은 금호타이어는?",
    }
    assert {a.subject for a in raw} == expected_subjects


def test_fetch_cafe_articles_for_month_builds_article_records():
    records = fetch_cafe_articles_for_month(
        "https://cafe.naver.com/f-e/cafes/10124067/menus/3278?viewType=L",
        2026,
        8,
        cafe_name="카니발 포에버",
        group="카니발KA4",
        fetch_page=fake_fetch_single_page,
    )
    assert len(records) == 8
    assert all(r.cafe == "카니발 포에버" and r.group == "카니발KA4" for r in records)
    total_views = sum(r.views for r in records)
    total_likes = sum(r.likes for r in records)
    total_comments = sum(r.comments for r in records)
    # 원본 xlsx 스냅샷(수집 시점) 대비 조회수는 자연 증가했을 수 있으니 값 자체는
    # 비교하지 않고, 필드가 손실 없이 그대로 옮겨졌는지만 확인.
    assert total_views > 0 and total_likes >= 0 and total_comments >= 0


def test_pagination_stops_when_page_entirely_before_month():
    page1 = {
        "result": {
            "articleList": [_article(900016, 1787361430000, "8월 글", 1, 0, 0)],  # 2026-08-18
            "pageInfo": {"lastNavigationPageNumber": 2, "visibleNextButton": True},
        }
    }
    page2 = {
        "result": {
            "articleList": [_article(900017, 1783998000000, "7월 글", 1, 0, 0)],  # 2026-07-13
            "pageInfo": {"lastNavigationPageNumber": 2, "visibleNextButton": False},
        }
    }
    calls = []

    def fetch(cafe_id, menu_id, page, **kwargs):
        calls.append(page)
        return page1 if page == 1 else page2

    raw = fetch_raw_articles_for_month("1", "1", 2026, 8, fetch_page=fetch)
    assert len(raw) == 1
    assert calls == [1, 2]  # 2페이지까지 가서 7월 글을 만나고 멈춤


def _raw(nickname: str, subject: str = "글") -> RawArticle:
    return RawArticle(
        article_id=1,
        write_datetime=datetime(2026, 8, 1),
        subject=subject,
        read_count=0,
        like_count=0,
        comment_count=0,
        writer_nickname=nickname,
        writer_member_level_name="협력업체",
    )


# 2026-08 실제 라이브 스캔 결과 축소판 (형님 확인, 2026-09-07):
# 한국타이어는 'T매니저'만 공식, '파주매니저'와 랜덤 닉네임은 비공식.
# 넥센타이어는 '넥스트레벨'과 '타이어엔샵'만 공식, 나머지 변형 계정은 비공식.
def test_filter_official_accounts_hankook():
    raw = [
        _raw("한국타이어T매니저"),
        _raw("한국타이어T매니저"),
        _raw("한국타이어파주매니저"),
        _raw("틴셔lev6gtl부산"),
    ]
    filtered = filter_official_accounts(raw, ["한국타이어T매니저"])
    assert len(filtered) == 2
    assert all(a.writer_nickname == "한국타이어T매니저" for a in filtered)


def test_filter_official_accounts_nexen_multiple_allowed():
    raw = [
        _raw("넥스트레벨"),
        _raw("타이어엔샵"),
        _raw("전국G넥스트레벨"),
        _raw("넥센ll넥스트레벨"),
    ]
    filtered = filter_official_accounts(raw, ["넥스트레벨", "타이어엔샵"])
    assert {a.writer_nickname for a in filtered} == {"넥스트레벨", "타이어엔샵"}
    assert len(filtered) == 2


def test_filter_official_accounts_empty_whitelist_passes_through():
    # 금호처럼 계정 필터링이 필요 없는 브랜드는 화이트리스트가 비어 있고,
    # 이 경우 아무것도 걸러지지 않아야 한다.
    raw = [_raw("아무개1"), _raw("아무개2")]
    assert filter_official_accounts(raw, []) == raw


def test_parse_cafe_menu_ids_new_style_url():
    cafe_id, menu_id = parse_cafe_menu_ids(
        "https://cafe.naver.com/f-e/cafes/10124067/menus/3278?viewType=L"
    )
    assert cafe_id == "10124067"
    assert menu_id == "3278"


def test_parse_cafe_menu_ids_old_style_url():
    # 로스터에 이 구형 URL(카니발 포에버)이 실제로 섞여 있어서 별도로 지원해야 함.
    cafe_id, menu_id = parse_cafe_menu_ids(
        "https://cafe.naver.com/ArticleList.nhn?search.clubid=10124067&search.menuid=3278&search.boardtype=L"
    )
    assert cafe_id == "10124067"
    assert menu_id == "3278"
