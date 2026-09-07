"""8월 카페통계.xlsx의 `금호`/`한국`/`넥센` 로스터 시트를 읽어 config/cafes.yaml을
생성하는 1회성 부트스트랩 스크립트.

카페 로스터는 매달 크롤러가 재생성하는 게 아니라 "고정 설정"이다 (PRD 3.1).
이 스크립트는 최초 확정 시점(또는 로스터가 실제로 바뀌었을 때) 사람이 검토 후
다시 실행하는 용도로만 쓴다.

주의: 원본 시트의 게시판 그룹 단축명(D열)은 병합 셀 forward-fill 경계가 실제
부제(E열, 매 행 채워짐) 전환 시점과 한 행 어긋나 있는 경우가 있었다(2026-08 확인:
쏘나타DN8 행 부근). 그래서 그룹 판정은 병합 D열이 아니라 매 행에 값이 있는 E열을
기준으로 하고, D열 단축명은 알려진 값으로만 매핑한다.
"""

from __future__ import annotations

import argparse
from collections import OrderedDict
from pathlib import Path

import openpyxl
import yaml

KUMHO_SHORT_LABEL = {
    "SUV타이어 크루젠GTPro": "CRUGEN GT Pro",
    "대한민국 대표 금호타이어": "금호타이어",
}

# 형님 확인 (2026-09-07): 공식 계정 목록. 같은 이름 패턴(예: 한국타이어파주매니저)의
# 다른 계정이 실제로 존재하지만 공식으로 인정하지 않기로 확정했다 (T-03).
HANKOOK_OFFICIAL_ACCOUNTS = ["한국타이어T매니저"]
NEXEN_OFFICIAL_ACCOUNTS = ["넥스트레벨", "타이어엔샵"]


def _read_roster_rows(ws, *, cols, start_row=4):
    """빈 행이 나올 때까지 (row, {field: value}) 목록을 반환한다."""
    rows = []
    r = start_row
    while True:
        values = {name: ws.cell(r, c).value for name, c in cols.items()}
        if all(v is None for v in values.values()):
            break
        rows.append((r, values))
        r += 1
    return rows


def _build_groups(rows, *, short_label_map=None):
    """부제(board_group) 값이 바뀔 때마다 새 그룹으로 묶는다."""
    groups: "OrderedDict[str, list]" = OrderedDict()
    seen_urls: set[str] = set()
    skipped_dupes = []

    for row_idx, values in rows:
        board_group = values["board_group"]
        url = values["url"]

        if url in seen_urls:
            skipped_dupes.append((row_idx, values["name"], url))
            continue
        seen_urls.add(url)

        group = groups.setdefault(
            board_group,
            {
                "board_group": board_group,
                "board_group_short": (short_label_map or {}).get(board_group),
                "cafes": [],
            },
        )
        group["cafes"].append(
            {
                "car_model": values["car_model"],
                "name": values["name"],
                "url": url,
                "member_count": values.get("member_count"),
            }
        )

    return list(groups.values()), skipped_dupes


def build_kumho(wb):
    ws = wb["금호"]
    cols = {
        "board_group": 5,  # E: 게시판명(부제) - 매 행 채워짐
        "car_model": 6,  # F: 차종
        "name": 7,  # G: 카페명
        "member_count": 8,  # H: 전체회원수
        "url": 9,  # I: URL
    }
    rows = _read_roster_rows(ws, cols=cols)
    groups, skipped = _build_groups(rows, short_label_map=KUMHO_SHORT_LABEL)
    return groups, skipped


def build_hankook(wb):
    ws = wb["한국"]
    cols = {
        "board_group": 5,  # E: 게시판명(부제)
        "car_model": 6,
        "name": 7,
        "member_count": 8,
        "url": 9,
    }
    rows = _read_roster_rows(ws, cols=cols)
    groups, skipped = _build_groups(rows)
    return groups, skipped


def build_nexen(wb):
    ws = wb["넥센"]
    cols = {
        "car_model": 3,  # C: 차종
        "name": 4,  # D: 카페
        "url": 5,  # E: URL
    }
    rows = _read_roster_rows(ws, cols=cols)
    # 넥센 로스터에는 게시판 그룹 구분이 없다 -> 단일 그룹으로 묶는다.
    for _, values in rows:
        values["board_group"] = "넥센타이어"
        values["member_count"] = None
    groups, skipped = _build_groups(rows)
    return groups, skipped


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="원본 xlsx 경로 (예: 8월 카페통계.xlsx)")
    parser.add_argument("--out", required=True, help="출력 config/cafes.yaml 경로")
    args = parser.parse_args()

    wb = openpyxl.load_workbook(args.source, data_only=True)

    kumho_groups, kumho_dupes = build_kumho(wb)
    hankook_groups, hankook_dupes = build_hankook(wb)
    nexen_groups, nexen_dupes = build_nexen(wb)

    for brand, dupes in [("금호", kumho_dupes), ("한국", hankook_dupes), ("넥센", nexen_dupes)]:
        for row_idx, name, url in dupes:
            print(f"[SKIP DUP] {brand} row {row_idx}: {name} ({url})")

    data = {
        "brands": {
            "kumho": {
                "label": "금호타이어",
                "official_accounts": [],
                "groups": kumho_groups,
            },
            "hankook": {
                "label": "한국타이어",
                "official_accounts": HANKOOK_OFFICIAL_ACCOUNTS,
                "groups": hankook_groups,
            },
            "nexen": {
                "label": "넥센타이어",
                "official_accounts": NEXEN_OFFICIAL_ACCOUNTS,
                "groups": nexen_groups,
            },
        }
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=100),
        encoding="utf-8",
    )
    total = sum(len(g["cafes"]) for g in kumho_groups) + \
        sum(len(g["cafes"]) for g in hankook_groups) + \
        sum(len(g["cafes"]) for g in nexen_groups)
    print(f"Wrote {out_path} ({total} cafes total)")


if __name__ == "__main__":
    main()
