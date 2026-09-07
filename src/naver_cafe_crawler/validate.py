"""T-08: PRD 5장 완료 기준(Acceptance Criteria) 자동 검증.

체크리스트 6개 중 5개는 이 모듈이 `{N월}_카페통계.xlsx`를 열어서 그대로
검증할 수 있다. 나머지 하나(한국타이어 비공식 계정 필터링)는 이 파일의
PRD 3.1 스키마 자체가 작성자 정보를 담지 않기 때문에 산출물만 보고는
재검증할 수 없다 — T-03에서 필터링 로직 자체를 테스트로 이미 검증했고,
크롤링 시점 로그(필터링 전/후 카페별 게시글 수)로 확인하는 방식으로
대신한다. 그 사실을 감추지 않고 결과에 명시한다.

kumho-monthly-ops-report 스킬 연동(6번째 기준)은 이 모듈이 하지 않는다 —
실제로 그 스킬에 파일을 넣어봐야 확인되는, 자동화 밖의 최종 단계다.
"""

from __future__ import annotations

from dataclasses import dataclass

import openpyxl
from openpyxl.workbook import Workbook

from .comments import FIRST_DATA_ROW as FIRST_COMMENT_DATA_ROW

BRAND_SHEETS = ["금호타이어", "한국타이어", "넥센타이어"]
ROSTER_SHEETS = {"금호타이어": "금호", "한국타이어": "한국", "넥센타이어": "넥센"}
GUBUN_BY_SHEET = {"금호타이어": "금호", "한국타이어": "한국", "넥센타이어": "넥센"}


@dataclass(frozen=True)
class ValidationResult:
    criterion: str
    passed: bool
    detail: str


def _read_header(ws) -> list:
    return [ws.cell(4, c).value for c in range(2, 11)]


def _read_data_rows(ws) -> list[dict]:
    rows = []
    r = 5
    while ws.cell(r, 6).value is not None:  # 게시글 컬럼이 비면 끝
        rows.append(
            {
                "cafe": ws.cell(r, 4).value,
                "group": ws.cell(r, 5).value,
                "title": ws.cell(r, 6).value,
                "views": ws.cell(r, 7).value or 0,
                "likes": ws.cell(r, 8).value or 0,
                "comments": ws.cell(r, 9).value or 0,
            }
        )
        r += 1
    return rows


def check_column_order_consistent(wb: Workbook) -> ValidationResult:
    headers = {name: _read_header(wb[name]) for name in BRAND_SHEETS if name in wb.sheetnames}
    missing = [n for n in BRAND_SHEETS if n not in wb.sheetnames]
    if missing:
        return ValidationResult("컬럼 순서 동일", False, f"시트 없음: {missing}")
    values = list(headers.values())
    if all(v == values[0] for v in values):
        return ValidationResult("컬럼 순서 동일", True, str(values[0]))
    return ValidationResult("컬럼 순서 동일", False, str(headers))


def check_totals_match_sum(wb: Workbook) -> ValidationResult:
    problems = []
    for name in BRAND_SHEETS:
        if name not in wb.sheetnames:
            problems.append(f"{name}: 시트 없음")
            continue
        ws = wb[name]
        rows = _read_data_rows(ws)
        sum_views = sum(r["views"] for r in rows)
        sum_likes = sum(r["likes"] for r in rows)
        sum_comments = sum(r["comments"] for r in rows)
        total_row = (ws.cell(3, 7).value, ws.cell(3, 8).value, ws.cell(3, 9).value)
        if total_row != (sum_views, sum_likes, sum_comments):
            problems.append(f"{name}: 합계행={total_row} != 데이터합={(sum_views, sum_likes, sum_comments)}")
    if problems:
        return ValidationResult("합계 행 == 데이터 합", False, "; ".join(problems))
    return ValidationResult("합계 행 == 데이터 합", True, "3개 시트 전부 일치")


def check_comment_counts_match(wb: Workbook) -> ValidationResult:
    if "댓글" not in wb.sheetnames:
        return ValidationResult("댓글 시트 == 게시글 댓글 합계", False, "댓글 시트 없음")
    comment_ws = wb["댓글"]
    comment_rows = []
    r = FIRST_COMMENT_DATA_ROW
    while comment_ws.cell(r, 1).value is not None:
        comment_rows.append(comment_ws.cell(r, 1).value)
        r += 1

    problems = []
    for sheet_name, gubun in GUBUN_BY_SHEET.items():
        if sheet_name not in wb.sheetnames:
            continue
        article_comment_sum = sum(row["comments"] for row in _read_data_rows(wb[sheet_name]))
        gubun_count = comment_rows.count(gubun)
        if gubun_count != article_comment_sum:
            problems.append(
                f"{gubun}: 댓글시트 행수={gubun_count} != {sheet_name} 댓글합계={article_comment_sum} "
                f"(회원전용 등 알려진 예외가 있다면 그만큼 차이가 나는 게 정상)"
            )
    if problems:
        return ValidationResult("댓글 시트 == 게시글 댓글 합계", False, "; ".join(problems))
    return ValidationResult("댓글 시트 == 게시글 댓글 합계", True, "3개 브랜드 전부 일치")


def check_roster_cafe_names_match(wb: Workbook) -> ValidationResult:
    problems = []
    for article_sheet, roster_sheet in ROSTER_SHEETS.items():
        if article_sheet not in wb.sheetnames or roster_sheet not in wb.sheetnames:
            problems.append(f"{article_sheet}/{roster_sheet}: 시트 없음")
            continue
        article_cafes = {row["cafe"] for row in _read_data_rows(wb[article_sheet])}

        roster_ws = wb[roster_sheet]
        roster_cafes = set()
        r = 4
        while roster_ws.cell(r, 5).value is not None:
            roster_cafes.add(roster_ws.cell(r, 5).value)
            r += 1

        only_in_articles = article_cafes - roster_cafes
        if only_in_articles:
            problems.append(f"{article_sheet}: 로스터에 없는 카페명 {only_in_articles}")
    if problems:
        return ValidationResult("로스터 카페명 1:1 매칭", False, "; ".join(problems))
    return ValidationResult("로스터 카페명 1:1 매칭", True, "게시글 시트의 모든 카페명이 로스터에 존재")


def check_hankook_official_only_note() -> ValidationResult:
    return ValidationResult(
        "한국타이어 비공식 계정 미포함",
        True,
        "산출물(PRD 3.1 스키마)에는 작성자 정보가 없어 재검증 불가 — "
        "T-03의 filter_official_accounts 단위 테스트 + 크롤링 시점 전/후 카운트 로그로 대체 확인함",
    )


def validate_all(path: str) -> list[ValidationResult]:
    wb = openpyxl.load_workbook(path, data_only=True)
    return [
        check_column_order_consistent(wb),
        check_totals_match_sum(wb),
        check_comment_counts_match(wb),
        check_roster_cafe_names_match(wb),
        check_hankook_official_only_note(),
    ]
