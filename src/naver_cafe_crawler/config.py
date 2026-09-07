"""카페 로스터 설정 파일(config/cafes.yaml) 로더.

로스터 스키마는 PRD 3.1의 `금호`/`한국`/`넥센` 시트 구조를 따른다:
브랜드 -> 게시판 그룹(board_group) -> 카페 목록.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class CafeEntry:
    brand: str
    board_group: str
    board_group_short: str | None
    car_model: str
    name: str
    url: str
    member_count: int | None


@dataclass(frozen=True)
class BrandRoster:
    key: str
    label: str
    official_account: str | None
    cafes: list[CafeEntry]


def load_cafes(path: str | Path) -> dict[str, BrandRoster]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    rosters: dict[str, BrandRoster] = {}
    for brand_key, brand_data in data["brands"].items():
        cafes: list[CafeEntry] = []
        for group in brand_data["groups"]:
            for cafe in group["cafes"]:
                cafes.append(
                    CafeEntry(
                        brand=brand_key,
                        board_group=group["board_group"],
                        board_group_short=group.get("board_group_short"),
                        car_model=cafe["car_model"],
                        name=cafe["name"],
                        url=cafe["url"],
                        member_count=cafe.get("member_count"),
                    )
                )
        rosters[brand_key] = BrandRoster(
            key=brand_key,
            label=brand_data["label"],
            official_account=brand_data.get("official_account"),
            cafes=cafes,
        )
    return rosters
