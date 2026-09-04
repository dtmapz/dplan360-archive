"""대행사 실무 가이드 교육자료 HTML 정제 + Supabase Storage 업로드.

편집기로 만든 원본 HTML에서 편집 기능을 걷어내고 뷰어용으로 정제한 뒤,
Supabase Storage(`media-guide-files/media_practice/current.html`)에 올린다.

원본 HTML은 광고주 식별정보가 담긴 스크린샷을 포함할 수 있어 Public 레포에 커밋하지 않는다.
문서 교체 시에도 이 스크립트만 다시 돌리면 된다.

    python3 scripts/upload_media_practice.py "<원본 HTML 경로>"
    python3 scripts/upload_media_practice.py "<원본 HTML 경로>" --local-only
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

STORAGE_PATH = "media_practice/current.html"
LOCAL_OUT = ROOT / "assets" / "media_practice.html"

# 편집기 UI 클래스 — 뷰어에서는 전부 숨긴다.
EDITOR_CHROME = [
    ".bar", ".rail", ".railadd", ".sec-ctl", ".blk-tools",
    ".fig-ctl", ".handle", ".pal", ".plab", ".brand", ".cur",
]

CLEANUP_CSS = f"""
<style id="__viewer_cleanup__">
  /* 편집기 UI 숨김 */
  {", ".join(EDITOR_CHROME)} {{ display: none !important; }}
  button {{ display: none !important; }}
  /* 좌우 스크롤 없이 폭 맞춤 */
  html, body {{ zoom: 0.95; }}
  body {{ margin: 0 !important; }}
  .paper, .frame, .cover {{ max-width: 100% !important; box-sizing: border-box; }}
  h2.sec-title {{ scroll-margin-top: 12px; }}
</style>
"""


def clean(html: str) -> tuple[str, int]:
    """편집 기능을 제거하고 목차 앵커용 id를 부여한다."""
    # 편집기 동작 스크립트 제거
    html = re.sub(r"<script\b[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    # 편집 가능 속성 제거
    for attr in ("contenteditable", "data-ph", "spellcheck"):
        html = re.sub(rf'\s+{attr}="[^"]*"', "", html)
        html = re.sub(rf"\s+{attr}='[^']*'", "", html)
    # 편집 버튼 제거
    html = re.sub(r"<button\b[^>]*>.*?</button>", "", html, flags=re.DOTALL | re.IGNORECASE)

    # 목차 클릭 이동용 id 부여 (s1, s2, ...)
    counter = {"n": 0}

    def _add_id(match: re.Match) -> str:
        counter["n"] += 1
        return match.group(0)[:-1] + f' id="s{counter["n"]}">'

    html = re.sub(r'<h2[^>]*class="[^"]*sec-title[^"]*"[^>]*>', _add_id, html)

    # 뷰어용 스타일 주입
    if "</head>" in html:
        html = html.replace("</head>", CLEANUP_CSS + "</head>", 1)
    else:
        html = CLEANUP_CSS + html

    return html, counter["n"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="편집기로 만든 원본 HTML 경로")
    parser.add_argument(
        "--local-only",
        action="store_true",
        help="Storage 업로드 없이 로컬 정제본만 만든다 (개발용)",
    )
    args = parser.parse_args()

    src = Path(args.source).expanduser()
    if not src.exists():
        print(f"원본을 찾을 수 없습니다: {src}")
        return 1

    cleaned, sections = clean(src.read_text(encoding="utf-8"))

    if sections == 0:
        print("경고: sec-title 섹션을 찾지 못했습니다. 목차 이동이 동작하지 않습니다.")

    LOCAL_OUT.parent.mkdir(parents=True, exist_ok=True)
    LOCAL_OUT.write_text(cleaned, encoding="utf-8")
    size_mb = LOCAL_OUT.stat().st_size / 1024 / 1024
    print(f"정제 완료  섹션 {sections}개  {size_mb:.1f}MB  → {LOCAL_OUT}")

    if args.local_only:
        print("--local-only: Storage 업로드는 건너뜁니다.")
        return 0

    from utils.db import MEDIA_GUIDE_BUCKET, upload_to_storage

    upload_to_storage(MEDIA_GUIDE_BUCKET, STORAGE_PATH, cleaned.encode("utf-8"))
    print(f"업로드 완료  {MEDIA_GUIDE_BUCKET}/{STORAGE_PATH}")
    print("앱에는 캐시(TTL 1시간) 만료 후 반영됩니다. 즉시 확인하려면 앱을 재시작하세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
