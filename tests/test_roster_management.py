"""매달 카페 로스터를 추가/삭제하는 CLI 헬퍼(roster.py)에 대한 테스트."""

from __future__ import annotations

import copy

import pytest

from naver_cafe_crawler.roster import add_cafe, list_cafes, remove_cafe

SAMPLE = {
    "brands": {
        "kumho": {
            "label": "금호타이어",
            "official_account": None,
            "groups": [
                {
                    "board_group": "금호타이어",
                    "board_group_short": "금호타이어",
                    "cafes": [
                        {
                            "car_model": "쏘나타DN8",
                            "name": "쏘나타 오너스클럽",
                            "url": "https://cafe.naver.com/f-e/cafes/12263355/menus/1498",
                            "member_count": 537292,
                        }
                    ],
                }
            ],
        }
    }
}


@pytest.fixture
def data():
    return copy.deepcopy(SAMPLE)


def test_add_cafe_to_existing_group(data):
    add_cafe(
        data,
        "kumho",
        "금호타이어",
        "K8",
        "K8 오너스클럽",
        "https://cafe.naver.com/f-e/cafes/11672934/menus/989",
    )
    assert len(data["brands"]["kumho"]["groups"]) == 1
    assert len(data["brands"]["kumho"]["groups"][0]["cafes"]) == 2


def test_add_cafe_creates_new_group(data):
    add_cafe(
        data,
        "kumho",
        "CRUGEN GT Pro",
        "카니발KA4",
        "카니발 포에버",
        "https://cafe.naver.com/f-e/cafes/10124067/menus/3278",
        board_group_short="CRUGEN GT Pro",
    )
    assert len(data["brands"]["kumho"]["groups"]) == 2


def test_add_cafe_rejects_duplicate_url(data):
    with pytest.raises(ValueError, match="이미 등록된 URL"):
        add_cafe(
            data,
            "kumho",
            "금호타이어",
            "쏘나타DN8",
            "쏘나타 오너스클럽(중복)",
            "https://cafe.naver.com/f-e/cafes/12263355/menus/1498",
        )


def test_add_cafe_rejects_bad_url(data):
    with pytest.raises(ValueError, match="https://cafe.naver.com"):
        add_cafe(data, "kumho", "금호타이어", "차종", "이름", "cafe.naver.com/badurl")


def test_remove_cafe(data):
    remove_cafe(data, "kumho", "https://cafe.naver.com/f-e/cafes/12263355/menus/1498")
    assert len(data["brands"]["kumho"]["groups"]) == 0  # 그룹에 카페가 없으면 그룹도 제거


def test_remove_cafe_missing_url_raises(data):
    with pytest.raises(ValueError, match="등록되어 있지 않은 URL"):
        remove_cafe(data, "kumho", "https://cafe.naver.com/f-e/cafes/nope")


def test_list_cafes(data):
    rows = list_cafes(data, "kumho")
    assert len(rows) == 1
    assert rows[0][0] == "kumho"
