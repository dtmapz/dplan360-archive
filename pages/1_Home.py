import streamlit as st
from utils.sheets import (
    search_media,
    get_major_categories,
    get_sub_categories,
    get_media_by_category,
    get_all_media_with_categories,
)
from utils.ui import (
    request_register, render_pending_dialog, render_result_table,
    render_contact_table, render_media_grid, set_current_page,
)

set_current_page("home")

if "search_term" not in st.session_state:
    st.session_state["search_term"] = ""

mode = st.segmented_control(
    "검색 모드", options=["매체", "카테고리", "마일스톤"], default="매체",
    label_visibility="collapsed",
)

if mode == "매체":
    media_keyword = st.text_input(
        "매체명", placeholder="매체명을 입력하세요 (Enter로 검색)",
        label_visibility="collapsed",
    )
    if media_keyword != st.session_state.get("_last_media_keyword", ""):
        st.session_state["_last_media_keyword"] = media_keyword
        st.session_state["search_term"] = media_keyword

elif mode == "카테고리":
    majors = get_major_categories()
    col_major, col_sub = st.columns([1, 1])

    with col_major:
        major_sel = st.selectbox("대분류", majors, label_visibility="collapsed")

    with col_sub:
        if major_sel == "05 버티컬 미디어":
            subs = get_sub_categories(major_sel)
            sub_sel = st.selectbox(
                "중분류", subs, index=None,
                placeholder="중분류를 선택하세요", label_visibility="collapsed",
            )
        else:
            sub_sel = None
            st.selectbox("중분류", ["(해당 없음)"], label_visibility="collapsed", disabled=True)

    if major_sel == "05 버티컬 미디어":
        if sub_sel:
            st.session_state["search_term"] = sub_sel
    else:
        st.session_state["search_term"] = major_sel

if mode != "마일스톤":
    if st.button("+ 신규 매체 등록"):
        request_register()

    st.divider()

    keyword = st.session_state["search_term"]
    if keyword:
        st.markdown("#### 검색 결과")
        results = search_media(keyword)
        render_result_table(results, key_prefix="search")
    else:
        st.markdown("#### 주요 매체 컨택포인트")
        default_list = get_media_by_category("01 매스미디어")
        render_contact_table(default_list)

else:  # mode == "마일스톤"
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
