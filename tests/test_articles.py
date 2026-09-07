"""T-02 승인 기준 검증: 샘플 1개월 출력의 합계 행이 데이터 행 합과 일치하는지,
그리고 세 브랜드 시트가 항상 같은 컬럼 순서로 나오는지 확인.
"""

from __future__ import annotations

import openpyxl
import pytest

from naver_cafe_crawler.articles import (
    HEADER,
    ArticleRecord,
    group_cross_posted,
    normalize_title,
    write_brand_sheet,
)

SAMPLE_ARTICLES = [
    ArticleRecord(date="2026.08.28", cafe="카니발 포에버", group="카니발KA4",
                  title="CRUGEN GT Pro의 모든 것! 핵심 콘텐츠 다시 보기", views=18, likes=0, comments=0),
    ArticleRecord(date="2026.08.26", cafe="카니발 포에버", group="카니발KA4",
                  title="휴가 끝난 SUV, 타이어는 확인했나요?", views=20, likes=1, comments=2),
    ArticleRecord(date="2026.08.14", cafe="쏘렌토 멤버스", group="쏘렌토MQ4",
                  title="친환경 타이어의 미래는? 금호타이어 '2026 지속가능경영보고서' 발간",
                  views=4, likes=0, comments=0),
    # 크로스포스팅: 다른 카페에 같은 콘텐츠, 카페마다 태그만 다르게 붙음
    ArticleRecord(date="2026.08.14", cafe="아반떼AD 공식 동호회", group="아반떼AD",
                  title="[공지] 친환경 타이어의 미래는? 금호타이어 '2026 지속가능경영보고서' 발간",
                  views=3, likes=0, comments=0),
]


@pytest.fixture
def workbook_with_sheet(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "금호타이어"
    write_brand_sheet(ws, "금호 타이어", SAMPLE_ARTICLES)
    out = tmp_path / "sample.xlsx"
    wb.save(out)
    return openpyxl.load_workbook(out, data_only=True)["금호타이어"]


def test_header_matches_prd_canonical_order(workbook_with_sheet):
    ws = workbook_with_sheet
    header_row = [ws.cell(4, c).value for c in range(2, 2 + len(HEADER))]
    assert header_row == HEADER


def test_total_row_matches_sum_of_data_rows(workbook_with_sheet):
    ws = workbook_with_sheet
    n = len(SAMPLE_ARTICLES)
    data_rows = [
        (ws.cell(r, 7).value, ws.cell(r, 8).value, ws.cell(r, 9).value)
        for r in range(5, 5 + n)
    ]
    sum_views = sum(v for v, _, _ in data_rows)
    sum_likes = sum(li for _, li, _ in data_rows)
    sum_comments = sum(c for _, _, c in data_rows)

    assert ws.cell(3, 7).value == sum_views == sum(a.views for a in SAMPLE_ARTICLES)
    assert ws.cell(3, 8).value == sum_likes == sum(a.likes for a in SAMPLE_ARTICLES)
    assert ws.cell(3, 9).value == sum_comments == sum(a.comments for a in SAMPLE_ARTICLES)


def test_total_row_placeholder_cells(workbook_with_sheet):
    ws = workbook_with_sheet
    assert ws.cell(3, 2).value == "합계"
    assert ws.cell(3, 3).value == "-"
    assert ws.cell(3, 4).value == "-"
    assert ws.cell(3, 5).value is None
    assert ws.cell(3, 6).value == "-"


def test_data_row_count_matches_input(workbook_with_sheet):
    ws = workbook_with_sheet
    non_empty = [r for r in range(5, 5 + len(SAMPLE_ARTICLES)) if ws.cell(r, 6).value]
    assert len(non_empty) == len(SAMPLE_ARTICLES)


def test_normalize_title_strips_cafe_specific_tag():
    a = normalize_title("친환경 타이어의 미래는? 금호타이어 '2026 지속가능경영보고서' 발간")
    b = normalize_title("[공지] 친환경 타이어의 미래는? 금호타이어 '2026 지속가능경영보고서' 발간")
    assert a == b


def test_normalize_title_collapses_whitespace():
    a = normalize_title("여름의   끝자락,  시원한 혜택은 계속!")
    b = normalize_title("여름의 끝자락, 시원한 혜택은 계속!")
    assert a == b


def test_normalize_title_nfkc_for_styled_unicode():
    # 실제 원본에서 본 장식용 수학 알파벳 스타일 제목
    styled = "𝔾𝔸𝕊 & 𝕁𝕌𝕀ℂ𝔼 𝕓𝕪 𝔻ℝ𝕀𝕍𝔼"
    assert normalize_title(styled) == "GAS & JUICE by DRIVE"


def test_group_cross_posted_identifies_same_content():
    groups = group_cross_posted(SAMPLE_ARTICLES)
    key = normalize_title("친환경 타이어의 미래는? 금호타이어 '2026 지속가능경영보고서' 발간")
    assert len(groups[key]) == 2
    assert {a.cafe for a in groups[key]} == {"쏘렌토 멤버스", "아반떼AD 공식 동호회"}


def test_group_cross_posted_keeps_distinct_titles_separate():
    groups = group_cross_posted(SAMPLE_ARTICLES)
    assert len(groups) == 3  # 4개 게시글, 그 중 2개가 같은 콘텐츠 -> 3개 콘텐츠
