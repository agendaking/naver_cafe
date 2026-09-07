"""카페 로스터(config/cafes.yaml) 갱신 CLI.

예시:
  python scripts/manage_roster.py add --brand kumho --group "금호타이어" \
      --car-model "쏘나타DN8" --name "쏘나타 오너스클럽" \
      --url "https://cafe.naver.com/f-e/cafes/12263355/menus/1498"

  python scripts/manage_roster.py remove --brand hankook \
      --url "https://cafe.naver.com/f-e/cafes/11672934/menus/873?viewType=L"

  python scripts/manage_roster.py list --brand nexen
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from naver_cafe_crawler.roster import add_cafe, list_cafes, load_raw, remove_cafe, save_raw  # noqa: E402

BRANDS = ["kumho", "hankook", "nexen"]
DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config" / "cafes.yaml"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add", help="카페 추가")
    p_add.add_argument("--brand", required=True, choices=BRANDS)
    p_add.add_argument("--group", required=True, help="게시판 그룹(부제) 값. 기존 그룹명이면 거기 추가됨")
    p_add.add_argument("--group-short", default=None, help="그룹 단축명 (신규 그룹일 때만 의미 있음)")
    p_add.add_argument("--car-model", required=True)
    p_add.add_argument("--name", required=True)
    p_add.add_argument("--url", required=True)
    p_add.add_argument("--member-count", type=int, default=None)

    p_remove = sub.add_parser("remove", help="카페 삭제")
    p_remove.add_argument("--brand", required=True, choices=BRANDS)
    p_remove.add_argument("--url", required=True)

    p_list = sub.add_parser("list", help="현재 로스터 조회")
    p_list.add_argument("--brand", choices=BRANDS, default=None)

    args = parser.parse_args()
    data = load_raw(args.config)

    if args.command == "add":
        add_cafe(
            data,
            args.brand,
            args.group,
            args.car_model,
            args.name,
            args.url,
            member_count=args.member_count,
            board_group_short=args.group_short,
        )
        save_raw(data, args.config)
        print(f"[OK] 추가됨: {args.brand}/{args.group}/{args.car_model} - {args.name}")

    elif args.command == "remove":
        remove_cafe(data, args.brand, args.url)
        save_raw(data, args.config)
        print(f"[OK] 삭제됨: {args.brand} - {args.url}")

    elif args.command == "list":
        rows = list_cafes(data, args.brand)
        for brand, group, car_model, cafe in rows:
            print(f"{brand}\t{group}\t{car_model}\t{cafe}")
        print(f"--- 총 {len(rows)}개 ---")


if __name__ == "__main__":
    main()
