import re
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from utils.auth import get_current_user
from utils.db import MEDIA_GUIDE_BUCKET, get_service_client
from utils.ui import set_current_page

st.set_page_config(page_title="대행사 실무 가이드 | D-PLAN360", layout="wide")
set_current_page("대행사 실무 가이드")

user = get_current_user()
if not user:
    st.stop()

# 본문 HTML은 Public 레포에 커밋하지 않는다 (교육자료 스크린샷에 광고주 식별정보 포함 가능).
# Supabase Storage(authenticated 권한)에 두고 서버사이드에서 받아 iframe srcdoc으로 주입한다.
# 브라우저가 Storage에 직접 접근하지 않으므로 CORS·공유권한 이슈가 없고 렌더링은 로컬 파일과 동일.
STORAGE_PATH = "media_practice/current.html"
# 로컬 개발용 폴백 (.gitignore 처리됨)
LOCAL_FALLBACK = Path(__file__).resolve().parent.parent / "assets" / "media_practice.html"

DOC_TITLE = "대행사 만족도를 이끌어 낼 수 있는 실무"
DOC_EYEBROW = "실무 교육자료"
DOC_META = ["최종 업데이트 2026-09-04", "섹션 8개"]

SECTIONS = [
    "업무에 임하는 마인드",
    "캠페인 준비 단계",
    "소재 세팅",
    "애드포지션 · 게재보고",
    "모니터링",
    "리포팅",
    "기타",
    "마무리",
]

@st.cache_data(ttl=3600, show_spinner="교육자료를 불러오는 중...")
def _load_doc_html() -> str:
    """Storage에서 본문 HTML을 받아온다. 실패 시 로컬 폴백.

    버킷을 anon에 열지 않기 위해 service_role로 읽는다. 경로가 상수라 사용자 입력이
    끼어들 여지가 없고, 이 키는 서버사이드에만 머문다(브라우저로 나가지 않음).
    """
    try:
        sb = get_service_client()
        return sb.storage.from_(MEDIA_GUIDE_BUCKET).download(STORAGE_PATH).decode("utf-8")
    except Exception:
        if LOCAL_FALLBACK.exists():
            return LOCAL_FALLBACK.read_text(encoding="utf-8")
        raise


try:
    body_html = _load_doc_html()
except Exception as e:
    st.error(
        "본문 파일을 불러오지 못했습니다. "
        f"Storage `{MEDIA_GUIDE_BUCKET}/{STORAGE_PATH}` 업로드 여부를 확인해주세요.\n\n`{e}`"
    )
    st.stop()

# Extract inner <body> so we can compose our own wrapper with header + TOC.
m = re.search(r"<body[^>]*>(.*)</body>", body_html, flags=re.DOTALL | re.IGNORECASE)
body_inner = m.group(1) if m else body_html
head_styles = "".join(re.findall(r"<style\b[^>]*>.*?</style>", body_html, flags=re.DOTALL | re.IGNORECASE))
head_links = "".join(re.findall(r'<link\b[^>]*rel="stylesheet"[^>]*>', body_html, flags=re.IGNORECASE))

toc_items = "".join(
    f'<li><a role="button" tabindex="0" data-target="s{i}">'
    f'<span class="num">{i:02d}</span>{title}</a></li>'
    for i, title in enumerate(SECTIONS, start=1)
)

meta_line = " &nbsp;·&nbsp; ".join(DOC_META)

viewer = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;600;700&display=swap">
{head_links}
{head_styles}
<style>
  html, body {{ margin:0; padding:0; background:#fff; font-family:'IBM Plex Sans KR', -apple-system, system-ui, sans-serif; }}
  .doc-header {{
    background: linear-gradient(180deg, #FFF8E7 0%, #FFFDF6 100%);
    border: 1px solid #F0D48A;
    border-radius: 10px;
    padding: 22px 24px;
    margin: 8px 12px 14px;
  }}
  .doc-header .eyebrow {{ font-size:10.5px; color:#7A4E0A; font-weight:700; letter-spacing:0.14em; margin-bottom:6px; }}
  .doc-header .title   {{ font-size:22px; font-weight:700; color:#0B0B0B; margin:0 0 8px; text-wrap:balance; }}
  .doc-header .meta    {{ font-size:11px; color:#444; }}
  .toc {{ background:#FAFAFA; border:1px solid #e5e5e5; border-radius:8px; padding:16px 20px; margin:0 12px 14px; }}
  .toc-title {{ font-size:11px; font-weight:700; letter-spacing:0.1em; color:#444; margin-bottom:10px; }}
  .toc ol {{ margin:0; padding:0; list-style:none; columns:2; column-gap:24px; }}
  .toc li {{ font-size:12.5px; padding:4px 0; break-inside:avoid; }}
  .toc li a {{ color:#0B0B0B; text-decoration:none; display:flex; gap:8px; border-bottom:1px dashed transparent; padding:2px 0; cursor:pointer; }}
  .toc li a:hover {{ border-bottom-color:#F2A93B; }}
  .toc li a:focus-visible {{ outline:2px solid #F2A93B; outline-offset:2px; }}
  .toc li .num {{ color:#F2A93B; font-weight:700; font-variant-numeric:tabular-nums; min-width:22px; }}
</style>
</head>
<body>
  <div class="doc-header">
    <div class="eyebrow">{DOC_EYEBROW}</div>
    <div class="title">{DOC_TITLE}</div>
    <div class="meta">{meta_line}</div>
  </div>
  <div class="toc">
    <div class="toc-title">목차</div>
    <ol>{toc_items}</ol>
  </div>
  {body_inner}
<script>
  // 목차 클릭 → 해당 섹션으로 스크롤.
  // srcdoc iframe에서는 href="#id" 앵커가 상위 앱을 재이동시켜 로그인 화면으로 튀므로
  // 반드시 JS scrollIntoView로 처리할 것.
  (function () {{
    function jump(id) {{
      var el = document.getElementById(id);
      if (el) el.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
    }}
    document.querySelectorAll('.toc a[data-target]').forEach(function (a) {{
      a.addEventListener('click', function (e) {{
        e.preventDefault();
        jump(a.getAttribute('data-target'));
      }});
      a.addEventListener('keydown', function (e) {{
        if (e.key === 'Enter' || e.key === ' ') {{
          e.preventDefault();
          jump(a.getAttribute('data-target'));
        }}
      }});
    }});
  }})();
</script>
</body>
</html>"""

components.html(viewer, height=1500, scrolling=True)
