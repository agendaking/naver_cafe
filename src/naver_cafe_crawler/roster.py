"""config/cafes.yaml을 매달 손으로 안전하게 갱신하기 위한 헬퍼.

카페 로스터는 매달 조금씩 바뀐다(카페 신설/폐쇄, URL 변경 등). 이 모듈은
YAML 파일을 매번 처음부터 다시 만드는 대신, 개별 카페를 추가/삭제하면서
중복 URL 같은 실수를 즉시 걸러낸다. CLI는 scripts/manage_roster.py 참고.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_raw(path: str | Path) -> dict[str, Any]:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def save_raw(data: dict[str, Any], path: str | Path) -> None:
    Path(path).write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=100),
        encoding="utf-8",
    )


def _all_urls(brand_data: dict[str, Any]) -> set[str]:
    return {c["url"] for g in brand_data["groups"] for c in g["cafes"]}


def add_cafe(
    data: dict[str, Any],
    brand: str,
    board_group: str,
    car_model: str,
    name: str,
    url: str,
    *,
    member_count: int | None = None,
    board_group_short: str | None = None,
) -> None:
    if brand not in data["brands"]:
        raise ValueError(f"알 수 없는 브랜드: {brand}")
    if not url.startswith("https://cafe.naver.com"):
        raise ValueError(f"URL은 https://cafe.naver.com 으로 시작해야 함: {url}")

    brand_data = data["brands"][brand]
    if url in _all_urls(brand_data):
        raise ValueError(f"이미 등록된 URL: {url}")

    group = next(
        (g for g in brand_data["groups"] if g["board_group"] == board_group), None
    )
    if group is None:
        group = {
            "board_group": board_group,
            "board_group_short": board_group_short,
            "cafes": [],
        }
        brand_data["groups"].append(group)

    group["cafes"].append(
        {
            "car_model": car_model,
            "name": name,
            "url": url,
            "member_count": member_count,
        }
    )


def remove_cafe(data: dict[str, Any], brand: str, url: str) -> None:
    if brand not in data["brands"]:
        raise ValueError(f"알 수 없는 브랜드: {brand}")

    brand_data = data["brands"][brand]
    removed = False
    for group in brand_data["groups"]:
        before = len(group["cafes"])
        group["cafes"] = [c for c in group["cafes"] if c["url"] != url]
        if len(group["cafes"]) != before:
            removed = True

    if not removed:
        raise ValueError(f"등록되어 있지 않은 URL: {url}")

    # 카페가 하나도 안 남은 그룹은 정리
    brand_data["groups"] = [g for g in brand_data["groups"] if g["cafes"]]


def list_cafes(data: dict[str, Any], brand: str | None = None) -> list[tuple[str, str, str, str]]:
    """(brand, board_group, car_model, name+url) 튜플 목록."""
    brands = [brand] if brand else list(data["brands"].keys())
    rows = []
    for b in brands:
        for group in data["brands"][b]["groups"]:
            for cafe in group["cafes"]:
                rows.append((b, group["board_group"], cafe["car_model"], f"{cafe['name']} ({cafe['url']})"))
    return rows
