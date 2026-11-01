"""crawl_from_workbook.py가 만든 JSON을 운영현황 엑셀의 결과 시트에 기록한다.

- `금호타이어` 시트: 구분, 일자, 카페, 그룹, 게시글, 조회수, 좋아요, 댓글, 비고
- `한국타이어`/`넥센타이어` 시트: 구분, 일자, 그룹, 카페, 게시글, 조회수, 좋아요, 댓글, 비고
  (기존 양식의 컬럼 순서를 그대로 따름)
- 맨 뒤 `댓글` 시트: 금호타이어 게시판 게시글의 댓글 — 카페명, 아이디, 댓글내용, 작성일시
- 맨 앞 요약 시트: 시트명을 `--summary-label`(예: "10월 31일")로 바꾸고, 그 라벨로
  열을 하나 추가해 브랜드별 조회수/좋아요/댓글 합계를 채운다.

데이터는 5행(B열)부터, 게시판 리스트 순서 → 최신 게시글 순으로 쓴다 (8월 파일과 동일).
한국/넥센은 config/cafes.yaml의 official_accounts에 있는 공식 계정 글만 남긴다
(2026년 9월 보고서에서 한국타이어 시트를 공식 계정 글만으로 정리한 기준을 따름).
"""

from __future__ import annotations

import argparse
import json
from copy import copy
from datetime import datetime
from pathlib import Path

import openpyxl
import yaml
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

CONFIG = Path(__file__).resolve().parents[1] / "config" / "cafes.yaml"
BRAND_CONFIG_KEYS = {"한국": "hankook", "넥센": "nexen"}
SUMMARY_ROWS = {"금호": 5, "한국": 8, "넥센": 11}  # 조회수 행; 좋아요/댓글은 +1/+2

FIRST_ROW = 5
SHEETS = {"금호": "금호타이어", "한국": "한국타이어", "넥센": "넥센타이어"}
NUM_FMT = "#,##0_);[Red]\\(#,##0\\)"
THIN = Side(style="thin")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
FONT = Font(name="맑은 고딕", size=11)


def style_cell(cell, *, number: bool = False) -> None:
    cell.font = copy(FONT)
    cell.border = copy(BORDER)
    if number:
        cell.number_format = NUM_FMT


def clear_rows(ws, start: int) -> None:
    for row in ws.iter_rows(min_row=start, min_col=2, max_col=10):
        for c in row:
            c.value = None


def write_brand(ws, brand_key: str, cafes: list[dict]) -> int:
    clear_rows(ws, FIRST_ROW)
    r = FIRST_ROW
    for cafe in cafes:
        for a in sorted(cafe["articles"], key=lambda x: x["datetime"], reverse=True):
            date = datetime.fromisoformat(a["datetime"]).strftime("%Y.%m.%d")
            if brand_key == "금호":
                cafe_col, group_col = 4, 5
            else:
                group_col, cafe_col = 4, 5
            values = {2: None, 3: date, cafe_col: cafe["name"], group_col: cafe["car_model"],
                      6: a["subject"], 7: a["views"], 8: a["likes"], 9: a["comments"], 10: None}
            for col, v in values.items():
                c = ws.cell(r, col, v)
                style_cell(c, number=col in (7, 8, 9))
            r += 1
    return r - FIRST_ROW


def write_comments(wb, cafes: list[dict]) -> int:
    if "댓글" in wb.sheetnames:
        del wb["댓글"]
    ws = wb.create_sheet("댓글")  # 맨 뒤에 추가됨
    ws.sheet_view.showGridLines = False
    ws.column_dimensions["A"].width = 1.125
    for col, w in zip("BCDE", (24, 22, 80, 18)):
        ws.column_dimensions[col].width = w
    ws.cell(1, 2, "금호타이어 게시판 댓글 현황").font = Font(name="맑은 고딕", size=16, bold=True)
    header_fill = PatternFill("solid", fgColor="D9D9D9")
    for i, label in enumerate(["카페명", "아이디", "댓글내용", "작성일시"], start=2):
        c = ws.cell(4, i, label)
        style_cell(c)
        c.font = Font(name="맑은 고딕", size=11, bold=True)
        c.fill = header_fill
        c.alignment = Alignment(horizontal="center")
    r = FIRST_ROW
    for cafe in cafes:
        for a in sorted(cafe["articles"], key=lambda x: x["datetime"], reverse=True):
            for cm in a["comment_items"] or []:
                vals = [cafe["name"], cm["writer"], cm["content"], datetime.fromisoformat(cm["datetime"])]
                for i, v in enumerate(vals, start=2):
                    c = ws.cell(r, i, v)
                    style_cell(c)
                ws.cell(r, 5).number_format = "yyyy-mm-dd hh:mm"
                ws.cell(r, 4).alignment = Alignment(wrap_text=False)
                r += 1
    ws.freeze_panes = "B5"
    return r - FIRST_ROW


def filter_official(cafes: list[dict], accounts: list[str]) -> list[dict]:
    if not accounts:
        return cafes
    return [dict(c, articles=[a for a in c["articles"] if a["writer"] in accounts]) for c in cafes]


def write_summary(wb, label: str, totals: dict[str, tuple[int, int, int]]) -> None:
    """맨 앞 요약 시트에 `label` 열을 추가(이미 있으면 덮어씀)하고 시트명을 바꾼다."""
    ws = wb.worksheets[0]
    last = ws.max_column
    col = last if ws.cell(4, last).value == label else last + 1
    if col != last:
        src = get_column_letter(last)
        for r in range(3, ws.max_row + 1):
            s, d = ws.cell(r, last), ws.cell(r, col)
            if s.has_style:
                d._style = copy(s._style)
        ws.column_dimensions[get_column_letter(col)].width = ws.column_dimensions[src].width
        # 연도 헤더 병합(예: AD3:AL3)을 새 열까지 늘린다
        for rng in list(ws.merged_cells.ranges):
            if rng.min_row == 3 and rng.max_col == last:
                ws.unmerge_cells(str(rng))
                ws.merge_cells(start_row=3, start_column=rng.min_col, end_row=3, end_column=col)
    ws.cell(4, col, label)
    for key, row in SUMMARY_ROWS.items():
        views, likes, comments = totals[key]
        # 게시글이 하나도 없으면 9월 넥센처럼 빈칸으로 둔다
        for i, v in enumerate((views, likes, comments)):
            ws.cell(row + i, col, v if any(totals[key]) else None)
    ws.title = label


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbook", required=True, help="원본 운영현황 엑셀")
    parser.add_argument("--data", required=True, help="crawl_from_workbook.py 출력 JSON")
    parser.add_argument("--out", required=True)
    parser.add_argument("--summary-label", help='요약 시트 새 열/시트명, 예: "10월 31일"')
    args = parser.parse_args()

    data = json.loads(open(args.data, encoding="utf-8").read())
    brands_cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))["brands"]
    wb = openpyxl.load_workbook(args.workbook)
    totals: dict[str, tuple[int, int, int]] = {}
    brand_cafes: dict[str, list[dict]] = {}
    for key, sheet in SHEETS.items():
        cafes = data["brands"][key]["cafes"]
        if key in BRAND_CONFIG_KEYS:
            accounts = brands_cfg[BRAND_CONFIG_KEYS[key]].get("official_accounts") or []
            cafes = filter_official(cafes, accounts)
        brand_cafes[key] = cafes
        n = write_brand(wb[sheet], key, cafes)
        arts = [a for c in cafes for a in c["articles"]]
        totals[key] = (sum(a["views"] for a in arts), sum(a["likes"] for a in arts),
                       sum(a["comments"] for a in arts))
        print(f"{sheet}: {n}건 / 조회수 {totals[key][0]:,} 좋아요 {totals[key][1]:,} 댓글 {totals[key][2]:,}")
    n = write_comments(wb, brand_cafes["금호"])
    print(f"댓글: {n}건")
    if args.summary_label:
        write_summary(wb, args.summary_label, totals)
        print(f"요약 시트: '{args.summary_label}' 열 추가/갱신")
    wb.save(args.out)
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
