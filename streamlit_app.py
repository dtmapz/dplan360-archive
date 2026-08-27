import streamlit as st
from utils.ui import inject_base_style
from utils.auth import get_current_user, is_admin, logout, render_login_page
from utils.spbot_ui import render_spbot_trigger

st.set_page_config(page_title="D-PLAN360 ARCHIVE", layout="wide")
inject_base_style()

user = get_current_user()
if not user:
    render_login_page()
    st.stop()

with st.sidebar:
    col_email, col_btn = st.columns([2, 1])
    with col_email:
        st.markdown(
            f"<div style='font-size:14px; color:#aaa; padding-top:8px;'>{user.get('email', '')}</div>",
            unsafe_allow_html=True,
        )
    with col_btn:
        if st.button("로그아웃", use_container_width=True):
            logout()

st.markdown(
    """
    <style>
    [data-testid="stSidebar"] { background-color: #0B0B0B; }
    [data-testid="stSidebar"] * { color: #FFFFFF !important; }
    [data-testid="stSidebarNav"] a span { font-size: 16px !important; }
    [data-testid="stLogo"] img { height: 48px !important; max-width: none !important; }
    [data-testid="stSidebar"] [data-testid="stButton"] button {
        background-color: #0B0B0B !important;
        color: #FFFFFF !important;
        border: 1px solid #F2A93B !important;
        font-size: 13px !important;
    }

    /* 사이드바 네비게이션 폰트 크기 조정 */
    [data-testid="stSidebarNav"] details summary {
        font-size: 14px !important;
        font-weight: 600 !important;
    }

    [data-testid="stSidebarNav"] details ul li a span {
        font-size: 11px !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

home_page = st.Page("pages/1_Home.py", title="매체 검색", icon="🔍", default=True)
media_guide_page = st.Page("pages/6_MediaGuide.py", title="미디어 가이드", icon="❓")
creative_page = st.Page("pages/5_CreativeGuide.py", title="소재 제작 가이드", icon="🎨")
promotion_page = st.Page("pages/8_Promotion.py", title="SMR&넷플릭스 프로모션 LIVE", icon="🏆")
mediapromo_page = st.Page("pages/9_MediaPromo.py", title="미디어 프로모션", icon="🎁")
calendar_page = st.Page("pages/3_EventCalendar.py", title="디플랜360 캘린더", icon="📅")
report_page = st.Page("pages/7_ReportDownload.py", title="통합 리포트 다운로더", icon="🔢")
budget_page = st.Page("pages/10_BudgetReference.py", title="미디어믹스 레퍼런스", icon="📊")
casestudy_page = st.Page("pages/11_CaseStudy.py", title="캠페인 성공사례", icon="🏅")
admin_page = st.Page("pages/99_Admin.py", title="관리자", icon="⚙️")

pages = {
    "[MEDIA]": [home_page, media_guide_page, creative_page],
    "[PROMOTION]": [promotion_page, mediapromo_page],
    "[SUPPORT]": [calendar_page, report_page, budget_page, casestudy_page],
}
if is_admin():
    pages["[ADMIN]"] = [admin_page]

pg = st.navigation(pages)

# SP봇 트리거는 모든 페이지 공통 노출 (로그인 후, 페이지 실행 전)
render_spbot_trigger()

pg.run()
