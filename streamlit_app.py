import streamlit as st
from utils.ui import inject_base_style
from utils.auth import (
    get_current_user,
    is_admin,
    logout,
    render_login_page,
    must_change_password,
    render_forced_password_change,
    render_password_change_dialog,
)
from utils.spbot_ui import render_spbot_trigger

st.set_page_config(page_title="D-PLAN360 ARCHIVE", layout="wide")
inject_base_style()

user = get_current_user()
if not user:
    render_login_page()
    st.stop()

if must_change_password():
    render_forced_password_change()
    st.stop()

with st.sidebar:
    st.markdown(
        f"<div style='font-size:14px; color:#aaa; padding-top:8px;'>{user.get('email', '')}</div>",
        unsafe_allow_html=True,
    )
    if st.button("🔑 비밀번호 변경", use_container_width=True):
        render_password_change_dialog()
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

    /* 대행사 실무 가이드 항목: 주간 뉴스룸과 같은 반투명 흰색 16% + 흰 세로선 강조 (선택 여부 무관) */
    [data-testid="stSidebarNav"] a[href*="MediaPractice"] {
        background: rgba(255, 255, 255, 0.16) !important;
        border-left: 3px solid #FFFFFF !important;
        border-radius: 4px !important;
    }
    [data-testid="stSidebarNav"] a[href*="MediaPractice"]:hover {
        background: rgba(255, 255, 255, 0.24) !important;
    }
    [data-testid="stSidebarNav"] a[href*="MediaPractice"] * {
        color: #FFFFFF !important;
        font-weight: 600 !important;
        background: transparent !important;
    }
    [data-testid="stSidebarNav"] li:has(a[href*="MediaPractice"]) {
        background: transparent !important;
    }

    /* 주간 뉴스룸 항목: 항상 반투명 흰색 16% 배경 + 흰 세로선 강조 (선택 여부 무관).
       순백은 어두운 사이드바에서 앰버 실무 가이드보다 먼저 튀어 반투명으로 낮췄다 */
    [data-testid="stSidebarNav"] a[href*="Newsroom"] {
        background: rgba(255, 255, 255, 0.16) !important;
        border-left: 3px solid #FFFFFF !important;
        border-radius: 4px !important;
    }
    [data-testid="stSidebarNav"] a[href*="Newsroom"]:hover {
        background: rgba(255, 255, 255, 0.24) !important;
    }
    [data-testid="stSidebarNav"] a[href*="Newsroom"] * {
        color: #FFFFFF !important;
        font-weight: 600 !important;
        background: transparent !important;
    }
    [data-testid="stSidebarNav"] li:has(a[href*="Newsroom"]) {
        background: transparent !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

home_page = st.Page("pages/1_Home.py", title="매체 검색", icon="🔍", default=True)
media_guide_page = st.Page("pages/6_MediaGuide.py", title="미디어 가이드", icon="❓")
creative_page = st.Page("pages/5_CreativeGuide.py", title="소재 제작 가이드", icon="🎨")
media_archive_page = st.Page("pages/4_MediaArchive.py", title="주요 미디어 자료", icon="📁")
media_news_page = st.Page("pages/13_MediaNews.py", title="미디어 소식 아카이브", icon="📰")
newsroom_page = st.Page("pages/14_Newsroom.py", title="주간 뉴스룸", icon="🗞️")
promotion_page = st.Page("pages/8_Promotion.py", title="SMR&넷플릭스 프로모션 LIVE", icon="🏆")
mediapromo_page = st.Page("pages/9_MediaPromo.py", title="미디어 프로모션", icon="🎁")
calendar_page = st.Page("pages/3_EventCalendar.py", title="디플랜360 캘린더", icon="📅")
# 통합 리포트 다운로더 — 사이드바에서 제외 (2026-09-10).
# 데이터 수집(GCP Cloud Scheduler → Cloud Run)을 중단하며 페이지도 내렸다.
# 코드는 기록 보존을 위해 남겨두며, 되살리려면 아래 두 줄의 주석을 풀면 된다.
# report_page = st.Page("pages/7_ReportDownload.py", title="통합 리포트 다운로더", icon="🔢")
budget_page = st.Page("pages/10_BudgetReference.py", title="업종별 예산 가이드", icon="📊")
casestudy_page = st.Page("pages/11_CaseStudy.py", title="캠페인 성공사례", icon="🏅")
media_practice_page = st.Page("pages/12_MediaPractice.py", title="[중요] 대행사 실무 가이드", icon="📘")
admin_page = st.Page("pages/99_Admin.py", title="액세스 권한 관리", icon="🔐")

pages = {
    "[MEDIA]": [home_page, media_guide_page, media_archive_page, media_news_page, newsroom_page],
    "[PROMOTION]": [promotion_page, mediapromo_page],
    "[SUPPORT]": [calendar_page, creative_page, budget_page, casestudy_page, media_practice_page],
}
if is_admin():
    pages["[ADMIN]"] = [admin_page]

pg = st.navigation(pages)

# SP봇 트리거는 모든 페이지 공통 노출 (로그인 후, 페이지 실행 전)
# 2026-09-02: AI 챗봇 기능 미사용 결정 — 기능/코드는 유지하되 UI 노출만 비활성화.
# 재사용 시 아래 줄 주석만 해제하면 됨.
# render_spbot_trigger()

pg.run()
