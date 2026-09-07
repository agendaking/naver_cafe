"""T-05: 카카오톡 채널 통계 xls -> xlsx 변환 + 완전성 검증.

형님이 카카오톡 채널 관리자센터에서 매달 수동으로 다운로드해오는 xls
파일을 입력받아, 대상 월의 날짜가 하루도 안 빠졌는지 확인하고 PRD 3.3
스키마 그대로 xlsx로 저장한다.

수치가 관리자센터 화면과 실제로 맞는지는 자동화할 수 없는 부분이라
(형님이 직접 대조), 여기서는 형식/완전성만 검증한다.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from naver_cafe_crawler.kakao import load_kakao_xls, validate_month_completeness, write_kakao_workbook  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="관리자센터에서 다운로드한 원본 xls 경로")
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=int, required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    data = load_kakao_xls(args.source)
    print(f"친구수 통계: {len(data.friends)}행, 조회수/방문자수: {len(data.views)}행")
    print(f"메시지 발송 요약: {data.message_summary}")

    friend_errors = validate_month_completeness(
        [f.date for f in data.friends], args.year, args.month
    )
    view_errors = validate_month_completeness(
        [v.date for v in data.views], args.year, args.month
    )

    ok = True
    for label, errors in [("친구수 통계", friend_errors), ("조회수와 방문자수", view_errors)]:
        for e in errors:
            print(f"[검증 실패] {label}: {e}", file=sys.stderr)
            ok = False

    if data.message_summary is None:
        print("[검증 실패] 메시지 발송 요약 블록을 찾지 못함", file=sys.stderr)
        ok = False

    if not ok:
        sys.exit(1)

    write_kakao_workbook(args.out, data)
    print(f"[검증 통과] 날짜 누락/중복 없음. Wrote {args.out}")
    print("※ 수치 자체가 카카오톡 채널 관리자센터 화면과 일치하는지는 직접 대조 확인 필요.")


if __name__ == "__main__":
    main()
