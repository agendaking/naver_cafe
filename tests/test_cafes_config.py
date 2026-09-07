"""T-01 승인 기준 검증: config/cafes.yaml의 카페 수/그룹 배정이 올바른지 확인.

기준 수치는 2026-08 실제 수집분(8월 카페통계.xlsx)의 `금호`/`한국`/`넥센` 로스터
시트를 직접 세어서 얻은 값이다 (scripts/import_roster_from_xlsx.py 참고).
- 금호: 원본에 쏘나타 오너스클럽 행이 완전히 중복 기재되어 있어(동일 URL) 1건
  제외하고 70건으로 확정.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from naver_cafe_crawler.config import load_cafes

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "cafes.yaml"

EXPECTED_TOTAL_COUNTS = {
    "kumho": 70,
    "hankook": 30,
    "nexen": 54,
}

EXPECTED_KUMHO_GROUP_COUNTS = {
    "CRUGEN GT Pro": 19,
    "금호타이어": 51,
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


def test_hankook_official_account_recorded(rosters):
    # T-03에서 실제 필터링 로직에 사용할 값. 카페 로스터 자체와는 무관하지만
    # 브랜드 메타데이터로 지금 확정해둔다 (형님 확인: '한국타이어T매니저').
    assert rosters["hankook"].official_account == "한국타이어T매니저"
