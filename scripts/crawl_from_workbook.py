"""운영현황 엑셀의 `금호`/`한국`/`넥센` 게시판 리스트 시트를 그대로 읽어서
대상 월 게시글(+금호 댓글)을 수집하고, 원본 데이터를 JSON으로 저장한다.

config/cafes.yaml 대신 매달 갱신되는 운영현황 엑셀 자체를 로스터로 쓴다.
엑셀 기록은 write_workbook_results.py가 이 JSON을 읽어서 한다.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import openpyxl  # noqa: E402

from naver_cafe_crawler.crawl import fetch_raw_articles_for_month, fetch_raw_comments_for_article  # noqa: E402
from naver_cafe_crawler.naver_api import CommentsRestrictedError, parse_cafe_menu_ids  # noqa: E402


def read_roster(wb, sheet: str) -> tuple[list[dict], list[str]]:
    """(수집 대상 게시판 목록, 건너뛴 행 설명) 반환."""
    ws = wb[sheet]
    cafes: list[dict] = []
    skipped: list[str] = []
    seen: set[tuple[str, str]] = set()
    for row in ws.iter_rows(min_row=4, values_only=True):
        if sheet == "넥센":
            car_model, name, url, note = row[2], row[3], row[4], None
        else:
            car_model, name, url, note = row[5], row[6], row[8], row[9]
        if not name or not url:
            continue
        name, car_model = str(name).strip(), str(car_model or "").strip()
        if note and "중단" in str(note):
            skipped.append(f"{name} ({note})")
            continue
        try:
            ids = parse_cafe_menu_ids(str(url))
        except ValueError:
            skipped.append(f"{name} (게시판 URL 아님: {url}{' / ' + str(note).strip() if note else ''})")
            continue
        if ids in seen:
            skipped.append(f"{name} (중복 게시판)")
            continue
        seen.add(ids)
        cafes.append({"name": name, "car_model": car_model, "cafe_id": ids[0], "menu_id": ids[1]})
    return cafes, skipped


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbook", required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=int, required=True)
    parser.add_argument("--out", required=True, help="원본 데이터 JSON 경로")
    parser.add_argument("--delay", type=float, default=0.3)
    args = parser.parse_args()

    wb = openpyxl.load_workbook(args.workbook, read_only=True)
    result: dict = {"year": args.year, "month": args.month, "brands": {}}

    for sheet in ["금호", "한국", "넥센"]:
        cafes, skipped = read_roster(wb, sheet)
        print(f"=== {sheet}: 수집 {len(cafes)}개 게시판, 제외 {len(skipped)}개", file=sys.stderr)
        for s in skipped:
            print(f"  [제외] {s}", file=sys.stderr)
        brand = {"skipped": skipped, "cafes": []}
        for i, cafe in enumerate(cafes, start=1):
            entry = dict(cafe, articles=[], error=None)
            try:
                raw = fetch_raw_articles_for_month(cafe["cafe_id"], cafe["menu_id"], args.year, args.month)
            except Exception as e:  # noqa: BLE001
                entry["error"] = str(e)
                print(f"  [{i}/{len(cafes)}] [실패] {cafe['name']}: {e}", file=sys.stderr)
                brand["cafes"].append(entry)
                continue
            for a in raw:
                art = {
                    "article_id": a.article_id,
                    "datetime": a.write_datetime.isoformat(timespec="seconds"),
                    "subject": a.subject,
                    "views": a.read_count,
                    "likes": a.like_count,
                    "comments": a.comment_count,
                    "writer": a.writer_nickname,
                    "writer_level": a.writer_member_level_name,
                    "comment_items": None,
                    "comment_error": None,
                }
                # 댓글 원문은 금호타이어 게시판 게시글만 (게시글과 같은 배치에서 수집)
                if sheet == "금호" and a.comment_count:
                    try:
                        items = fetch_raw_comments_for_article(cafe["cafe_id"], a.article_id)
                        art["comment_items"] = [
                            {"writer": c.writer, "content": c.content,
                             "datetime": c.write_datetime.isoformat(timespec="seconds")}
                            for c in items
                        ]
                    except CommentsRestrictedError as e:
                        art["comment_error"] = f"회원전용: {e.reason}"
                    except Exception as e:  # noqa: BLE001
                        art["comment_error"] = str(e)
                entry["articles"].append(art)
            print(f"  [{i}/{len(cafes)}] {cafe['name']}: {len(raw)}건", file=sys.stderr)
            brand["cafes"].append(entry)
            time.sleep(args.delay)
        result["brands"][sheet] = brand

    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
