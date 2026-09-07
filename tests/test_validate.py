"""T-08 승인 기준: PRD 5장 검증 스크립트가 실제로 문제를 잡아내는지 확인.

정상 케이스는 통과하고, 각 기준을 일부러 깨뜨린 케이스는 정확히 그 기준만
실패로 잡아내야 한다.
"""

from __future__ import annotations

import openpyxl
import pytest

from naver_cafe_crawler.articles import ArticleRecord, write_brand_sheet
from naver_cafe_crawler.comments import CommentRecord, write_comment_sheet
from naver_cafe_crawler.roster_sheet import write_roster_sheet
from naver_cafe_crawler.validate import validate_all

KUMHO_ARTICLES = [
    ArticleRecord(date="2026.08.01", cafe="카니발 포에버", group="카니발KA4", title="글1", views=10, likes=1, comments=2),
]
HANKOOK_ARTICLES = [
    ArticleRecord(date="2026.08.02", cafe="K8 오너스 클럽", group="K8", title="글2", views=20, likes=2, comments=1),
]
NEXEN_ARTICLES = [
    ArticleRecord(date="2026.08.03", cafe="카니발 포에버", group="카니발KA4", title="글3", views=30, likes=3, comments=0),
]

KUMHO_GROUPS = [{"board_group": "CRUGEN GT Pro", "cafes": [
    {"car_model": "카니발KA4", "name": "카니발 포에버", "url": "https://cafe.naver.com/f-e/cafes/1/menus/1", "member_count": 1},
]}]
HANKOOK_GROUPS = [{"board_group": "그룹", "cafes": [
    {"car_model": "K8", "name": "K8 오너스 클럽", "url": "https://cafe.naver.com/f-e/cafes/2/menus/2", "member_count": 1},
]}]
NEXEN_GROUPS = [{"board_group": "그룹", "cafes": [
    {"car_model": "카니발KA4", "name": "카니발 포에버", "url": "https://cafe.naver.com/f-e/cafes/3/menus/3", "member_count": 1},
]}]

KUMHO_COMMENTS = [
    CommentRecord(gubun="금호", cafe="카니발 포에버", article_title="글1", write_date="2026.08.01", writer="a", content="c1"),
    CommentRecord(gubun="금호", cafe="카니발 포에버", article_title="글1", write_date="2026.08.01", writer="b", content="c2"),
]
HANKOOK_COMMENTS = [
    CommentRecord(gubun="한국", cafe="K8 오너스 클럽", article_title="글2", write_date="2026.08.02", writer="a", content="c1"),
]


def _build_workbook(*, kumho_articles=KUMHO_ARTICLES, comments=None):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "금호타이어"
    write_brand_sheet(ws, "금호 타이어", kumho_articles)
    write_brand_sheet(wb.create_sheet("한국타이어"), "한국타이어", HANKOOK_ARTICLES)
    write_brand_sheet(wb.create_sheet("넥센타이어"), "넥센타이어", NEXEN_ARTICLES)
    write_roster_sheet(wb.create_sheet("금호"), "금호타이어", KUMHO_GROUPS)
    write_roster_sheet(wb.create_sheet("한국"), "한국타이어", HANKOOK_GROUPS)
    write_roster_sheet(wb.create_sheet("넥센"), "넥센타이어", NEXEN_GROUPS)
    write_comment_sheet(wb.create_sheet("댓글"), comments if comments is not None else KUMHO_COMMENTS + HANKOOK_COMMENTS)
    return wb


def _save_and_validate(wb, tmp_path, name="stats.xlsx"):
    out = tmp_path / name
    wb.save(out)
    return validate_all(str(out))


def test_all_criteria_pass_for_well_formed_workbook(tmp_path):
    results = _save_and_validate(_build_workbook(), tmp_path)
    for r in results:
        assert r.passed, f"{r.criterion}: {r.detail}"


def test_detects_column_order_mismatch(tmp_path):
    wb = _build_workbook()
    # 한국타이어 시트만 그룹/카페 순서를 실수로 바꿔치기
    ws = wb["한국타이어"]
    cafe_label, group_label = ws.cell(4, 4).value, ws.cell(4, 5).value
    ws.cell(4, 4, group_label)
    ws.cell(4, 5, cafe_label)
    results = _save_and_validate(wb, tmp_path)
    by_name = {r.criterion: r for r in results}
    assert by_name["컬럼 순서 동일"].passed is False


def test_detects_total_mismatch(tmp_path):
    wb = _build_workbook()
    ws = wb["금호타이어"]
    ws.cell(3, 7, 99999)  # 합계 조회수를 일부러 틀리게
    results = _save_and_validate(wb, tmp_path)
    by_name = {r.criterion: r for r in results}
    assert by_name["합계 행 == 데이터 합"].passed is False


def test_detects_comment_count_mismatch(tmp_path):
    # 금호타이어 시트는 댓글=2라고 하는데, 댓글 시트에는 금호 행이 1개뿐
    wb = _build_workbook(comments=[KUMHO_COMMENTS[0]] + HANKOOK_COMMENTS)
    results = _save_and_validate(wb, tmp_path)
    by_name = {r.criterion: r for r in results}
    assert by_name["댓글 시트 == 게시글 댓글 합계"].passed is False


def test_detects_roster_name_mismatch(tmp_path):
    wb = _build_workbook()
    # 로스터 시트의 카페명에 오타를 냄
    wb["금호"].cell(4, 5, "카니발포에버")  # 공백 빠짐
    results = _save_and_validate(wb, tmp_path)
    by_name = {r.criterion: r for r in results}
    assert by_name["로스터 카페명 1:1 매칭"].passed is False
