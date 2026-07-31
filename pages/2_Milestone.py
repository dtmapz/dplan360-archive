import streamlit as st
from utils.sheets import (
    get_all_media_with_categories,
    get_major_categories,
    get_sub_categories,
)
from utils.ui import (
    render_media_grid, render_pending_dialog, set_current_page,
)

set_current_page("milestone")

all_media = get_all_media_with_categories()

majors = get_major_categories()
m01_04 = [m for m in majors if not m.startswith("05")]
cat_05 = [m for m in majors if m.startswith("05")]

left, mid, right = st.columns(3)


def render_major_section(major: str, all_media: list[dict]) -> None:
    with st.container(border=True):
        st.markdown(f"<div class='section-title'>{major}</div>", unsafe_allow_html=True)
        media_list = [m for m in all_media
                      if (m.get("categories") or {}).get("major_category") == major]
        render_media_grid(media_list, key_prefix=major.replace(" ", "_"), n_cols=2)


# 좌: 01, 02 / 중: 03, 04 / 우: 05
with left:
    for major in [m for m in m01_04 if m.startswith("01") or m.startswith("02")]:
        render_major_section(major, all_media)

with mid:
    for major in [m for m in m01_04 if m.startswith("03") or m.startswith("04")]:
        render_major_section(major, all_media)

with right:
    if cat_05:
        major = cat_05[0]
        with st.container(border=True):
            st.markdown(f"<div class='section-title'>{major}</div>", unsafe_allow_html=True)
        subs = get_sub_categories(major)
        sub_cols = st.columns(2)
        for i, sub in enumerate(subs):
            with sub_cols[i % 2]:
                with st.expander(sub, expanded=False):
                    media_list = [
                        m for m in all_media
                        if (m.get("categories") or {}).get("major_category") == major
                        and (m.get("categories") or {}).get("sub_category") == sub
                    ]
                    render_media_grid(media_list, key_prefix=f"05_{sub}", n_cols=1)

render_pending_dialog()
st.markdown(
    "<div style='margin-top:40px; padding-top:14px; border-top:0.5px solid #0B0B0B; "
    "font-size:11px; color:#9099B0; text-align:center;'>"
    "본 플랫폼은 D-PLAN360 내부 전용이며, 무단 배포 및 외부 공유를 금합니다. "
    "&nbsp;|&nbsp; 관리자: sp@d-plan360.com</div>",
    unsafe_allow_html=True,
)
