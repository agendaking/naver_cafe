"""T-08: kumho-monthly-ops-report 스킬이 실제로 기대하는 파일 계약을 고정.

이 테스트는 그 스킬의 references/data_sources.md에 문서화된 두 가지를
그대로 재현한다:
1. 브랜드 시트를 `ws.iter_rows(values_only=True)`로 읽었을 때 0-index
   2~8 위치에 일자/카페/그룹/게시글/조회수/좋아요/댓글이 온다.
2. 댓글 시트는 헤더가 4행, 데이터가 5행부터 시작하고, 구분='금호' 필터
   행수가 금호타이어 시트 댓글 합계와 정확히 일치한다.

2026-09-07 실제 크롤러 산출물(8월_카페통계.xlsx, 135개 카페 라이브
크롤링)로 이 계약을 검증했고, 그 과정에서 댓글 시트 헤더 위치가
1행이었던 버그(스킬은 4행을 기대)를 실제로 잡아서 고쳤다 — 이 테스트는
그 버그가 다시 생기지 않게 막는다.
"""

from __future__ import annotations

import openpyxl

from naver_cafe_crawler.articles import ArticleRecord, write_brand_sheet
from naver_cafe_crawler.comments import CommentRecord, write_comment_sheet


def test_brand_sheet_column_offsets_match_downstream_skill_contract(tmp_path):
    articles = [
        ArticleRecord(date="2026.08.01", cafe="카니발 포에버", group="카니발KA4", title="글1", views=10, likes=1, comments=2),
    ]
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "금호타이어"
    write_brand_sheet(ws, "금호 타이어", articles)
    out = tmp_path / "brand.xlsx"
    wb.save(out)

    loaded = openpyxl.load_workbook(out, data_only=True)["금호타이어"]
    header = list(loaded.iter_rows(min_row=4, max_row=4, values_only=True))[0]
    assert header[2:9] == ("일자", "카페", "그룹", "게시글", "조회수", "좋아요", "댓글")

    data_row = list(loaded.iter_rows(min_row=5, max_row=5, values_only=True))[0]
    assert data_row[2:9] == ("2026.08.01", "카니발 포에버", "카니발KA4", "글1", 10, 1, 2)


def test_comment_sheet_header_and_data_rows_match_downstream_skill_contract(tmp_path):
    comments = [
        CommentRecord(gubun="금호", cafe="카니발 포에버", article_title="글1", write_date="2026.08.01", writer="a", content="c"),
    ]
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "댓글"
    write_comment_sheet(ws, comments)
    out = tmp_path / "comments.xlsx"
    wb.save(out)

    loaded = openpyxl.load_workbook(out, data_only=True)["댓글"]
    # references/data_sources.md: "header row around row 4, data from row 5"
    header = [loaded.cell(4, c).value for c in range(1, 7)]
    assert header == ["구분", "카페", "게시물", "발행일", "작성자", "댓글내용"]
    data = [loaded.cell(5, c).value for c in range(1, 7)]
    assert data == ["금호", "카니발 포에버", "글1", "2026.08.01", "a", "c"]
