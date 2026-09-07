"""T-07: 네이버 블로그 / 티스토리 이벤트 콘텐츠 수집.

URL이 매달 바뀌므로 제목 또는 발행일로 그 달의 게시글을 찾는다. 한쪽
플랫폼에서 실패해도(파싱 구조 변경 등) 다른 플랫폼/전체 배치는 죽지 않고,
실패 사실을 명확한 로그로 남긴 뒤 그 항목만 스킵한다 (PRD 4장).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from naver_cafe_crawler.blog import (  # noqa: E402
    BlogFetchError,
    fetch_naver_blog_stats,
    fetch_tistory_stats,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--naver-blog-id", default="kumhotire_official")
    parser.add_argument("--tistory-domain", default="blog.kumhotire.co.kr")
    parser.add_argument("--title", help="찾을 게시글 제목")
    parser.add_argument("--date", help="찾을 게시글 발행일 (YYYY-MM-DD)")
    args = parser.parse_args()

    if not args.title and not args.date:
        parser.error("--title 또는 --date 중 하나는 지정해야 함")

    results = {}

    try:
        results["naver_blog"] = fetch_naver_blog_stats(
            args.naver_blog_id, title=args.title, target_date=args.date
        )
        r = results["naver_blog"]
        print(f"[OK] 네이버 블로그: {r.url} 좋아요={r.likes} 댓글={r.comments}")
    except BlogFetchError as e:
        print(f"[SKIP] 네이버 블로그 수집 실패: {e}", file=sys.stderr)

    try:
        results["tistory"] = fetch_tistory_stats(
            args.tistory_domain, title=args.title, target_date=args.date
        )
        r = results["tistory"]
        print(f"[OK] 티스토리: {r.url} 좋아요={r.likes} 댓글={r.comments}")
    except BlogFetchError as e:
        print(f"[SKIP] 티스토리 수집 실패: {e}", file=sys.stderr)

    if not results:
        print("[검증 실패] 두 플랫폼 모두 실패", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
