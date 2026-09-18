"""T-01 승인 기준 검증: config/cafes.yaml의 카페 수/그룹 배정이 올바른지 확인.

기준 수치는 2026-08 실제 수집분(8월 카페통계.xlsx)의 `금호`/`한국`/`넥센` 로스터
시트를 직접 세어서 얻은 값이다 (scripts/import_roster_from_xlsx.py 참고).
- 금호: 원본에 쏘나타 오너스클럽 행이 완전히 중복 기재되어 있어(동일 URL) 1건
  제외하고 70건으로 확정 (형님 확인 완료).
  2026-09-18: 형님이 준 cafe_list_202609.xlsx로 갱신 — 더뉴카니발/카포페 게시판이
  GV90/GV90더클래스로 대상 차종이 바뀌었고, 기아PV5클럽(PV5)이 신규 추가돼
  70 -> 71건.
- 한국: 원본에 URL이 프로토콜 없는 짧은 별칭(예: cafe.naver.com/pantagi)으로
  잘못 기재된 19개 행이 있었는데, 형님이 원본 8월 카페통계.xlsx에서 직접
  정리해서 정식 URL이 있는 11개 카페만 남겼다. 그 결과를 그대로 반영.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from naver_cafe_crawler.config import load_cafes

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "cafes.yaml"

EXPECTED_TOTAL_COUNTS = {
    "kumho": 71,
    "hankook": 11,
    "nexen": 54,
}

EXPECTED_KUMHO_GROUP_COUNTS = {
    "CRUGEN GT Pro": 19,
    "금호타이어": 52,
}


@pytest.fixture(scope="module")
def rosters():
    return load_cafes(CONFIG_PATH)


def test_all_brands_present(rosters):
    assert set(rosters.keys()) == {"kumho", "hankook", "nexen"}


@pytest.mark.parametrize("brand", ["kumho", "hankook", "nexen"])
def test_total_cafe_count(rosters, brand):
    assert len(rosters[brand].cafes) == EXPECTED_TOTAL_COUNTS[brand]


@pytest.mark.parametrize("brand", ["kumho", "hankook", "nexen"])
def test_no_duplicate_urls(rosters, brand):
    urls = [c.url for c in rosters[brand].cafes]
    assert len(urls) == len(set(urls)), "브랜드 내 카페 URL이 중복되면 안 된다"


@pytest.mark.parametrize("brand", ["kumho", "hankook", "nexen"])
def test_required_fields_non_empty(rosters, brand):
    for cafe in rosters[brand].cafes:
        assert cafe.car_model
        assert cafe.name
        assert cafe.url.startswith("https://cafe.naver.com")
        assert cafe.board_group


def test_kumho_group_breakdown(rosters):
    counts: dict[str, int] = {}
    for cafe in rosters["kumho"].cafes:
        counts[cafe.board_group_short] = counts.get(cafe.board_group_short, 0) + 1
    assert counts == EXPECTED_KUMHO_GROUP_COUNTS


EXPECTED_HANKOOK_GROUP_COUNTS = {
    "대한민국1등 한국타이어": 5,
    "SUV전용타이어 DYNAPRO": 3,
    "전기차전용 타이어 iON": 3,
}


def test_hankook_group_breakdown(rosters):
    counts: dict[str, int] = {}
    for cafe in rosters["hankook"].cafes:
        counts[cafe.board_group] = counts.get(cafe.board_group, 0) + 1
    assert counts == EXPECTED_HANKOOK_GROUP_COUNTS


def test_official_accounts_recorded(rosters):
    # T-03에서 실제 필터링 로직에 사용할 값 (형님 확인, 2026-09-07).
    assert rosters["hankook"].official_accounts == ("한국타이어T매니저",)
    assert rosters["nexen"].official_accounts == ("넥스트레벨", "타이어엔샵")
    assert rosters["kumho"].official_accounts == ()
