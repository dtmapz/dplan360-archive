import streamlit as st
from utils.ui import inject_base_style
from utils.auth import get_current_user, is_admin, logout, render_login_page

st.set_page_config(page_title="D-PLAN360 ARCHIVE", layout="wide")
inject_base_style()

# 로그인 체크
user = get_current_user()
if not user:
    render_login_page()
    st.stop()

# 사이드바 로고 + 로그아웃
st.logo("assets/m_logo_w-1.png", size="large")

with st.sidebar:
    col_email, col_btn = st.columns([2, 1])
    with col_email:
        st.markdown(
            f"<div style='font-size:12px; color:#aaa; padding-top:8px;'>{user.get('email', '')}</div>",
            unsafe_allow_html=True,
        )
    with col_btn:
        if st.button("로그아웃", use_container_width=True):
            logout()

st.markdown(
    """
    <style>
    [data-testid="stSidebar"] [data-testid="stButton"] button {
        background-color: #0B0B0B !important;
        color: #FFFFFF !important;
        border: 1px solid #F2A93B !important;
        font-size: 13px !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# 사이드바 CSS (블랙)
st.markdown(
    """
    <style>
    [data-testid="stSidebar"] { background-color: #0B0B0B; }
    [data-testid="stSidebar"] * { color: #FFFFFF !important; }
    [data-testid="stSidebarNav"] a span { font-size: 16px !important; }
    [data-testid="stLogo"] img { height: 48px !important; max-width: none !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

# 페이지 등록
home_page = st.Page("pages/1_Home.py", title="HOME", icon="🔍", default=True)
milestone_page = st.Page("pages/2_Milestone.py", title="MILESTONE", icon="🗺️")

pages = [home_page, milestone_page]

# 관리자 전용 페이지 (추후 추가)
# if is_admin():
#     admin_page = st.Page("pages/admin.py", title="관리자", icon="🔐")
#     pages.append(admin_page)

pg = st.navigation(pages)
pg.run()
