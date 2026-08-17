import streamlit as st
from utils.db import get_client
from utils.sheets import (
    get_org_by_email_sheet,
    is_email_registered,
)

ALLOWED_DOMAIN = "@d-plan360.com"


def get_current_user():
    """세션에서 현재 로그인 사용자 반환. 없으면 None."""
    return st.session_state.get("user", None)


def is_admin():
    """조직도 시트의 role='admin' 인 사용자만 관리자.
    (기존 Supabase user_metadata.role 방식 → Sheets 원본으로 이관)
    """
    user = get_current_user()
    if not user:
        return False
    email = (user.get("email") or "").strip().lower()
    if not email:
        return False
    org = get_org_by_email_sheet(email)
    return bool(org and org.get("role") == "admin")


def logout():
    """로그아웃 처리."""
    sb = get_client()
    try:
        sb.auth.sign_out()
    except Exception:
        pass
    st.session_state.pop("user", None)
    st.rerun()


def render_login_page():
    """로그인/회원가입 화면 렌더링."""
    st.markdown(
        "<style>[data-testid='stSidebar'] { display: none; }</style>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div style='max-width:420px; margin:80px auto;'>",
        unsafe_allow_html=True,
    )

    logo_l, logo_c, logo_r = st.columns([2, 1, 2])
    with logo_c:
        st.image("assets/logo.png", use_container_width=True)

    st.markdown("<div style='height:24px;'></div>", unsafe_allow_html=True)

    tab_login, tab_signup = st.tabs(["로그인", "회원가입"])

    with tab_login:
        email = st.text_input("이메일", key="login_email", placeholder="example@d-plan360.com")
        password = st.text_input("비밀번호", type="password", key="login_pw")

        if st.button("로그인", type="primary", use_container_width=True, key="login_btn"):
            if not email or not password:
                st.error("이메일과 비밀번호를 입력해주세요.")
            else:
                email_norm = email.strip().lower()
                # 조직도 게이트 — 미등록/비활성 사용자는 로그인 자체 차단
                if not is_email_registered(email_norm):
                    st.error("등록되지 않은 사용자입니다. 관리자에게 조직도 등록을 요청해주세요.")
                else:
                    try:
                        sb = get_client()
                        res = sb.auth.sign_in_with_password({"email": email_norm, "password": password})
                        st.session_state["user"] = res.user.__dict__
                        st.rerun()
                    except Exception:
                        st.error("이메일 또는 비밀번호가 올바르지 않습니다.")

    with tab_signup:
        email = st.text_input("이메일 (회사 메일로 가입)", key="signup_email", placeholder="example@d-plan360.com")
        password = st.text_input(
            "비밀번호",
            type="password",
            key="signup_pw",
            placeholder="영문 대소문자, 숫자, 특수기호 필수 포함",
            help="영문 대소문자 + 숫자 + 특수기호(!@#$ 등) 포함 8자 이상"
        )
        password_confirm = st.text_input("비밀번호 확인", type="password", key="signup_pw_confirm")

        if st.button("가입하기", type="primary", use_container_width=True, key="signup_btn"):
            email_norm = (email or "").strip().lower()
            if not email_norm or not password or not password_confirm:
                st.error("모든 항목을 입력해주세요.")
            elif not email_norm.endswith(ALLOWED_DOMAIN):
                st.error(f"D-PLAN360 사내 이메일({ALLOWED_DOMAIN})만 가입 가능합니다.")
            elif not is_email_registered(email_norm):
                st.error(
                    "조직도에 등록되지 않은 이메일입니다. "
                    "관리자에게 조직도 시트 등록을 요청한 뒤 다시 가입해주세요."
                )
            elif len(password) < 8:
                st.error("비밀번호는 8자 이상이어야 합니다.")
            elif password != password_confirm:
                st.error("비밀번호가 일치하지 않습니다.")
            else:
                try:
                    sb = get_client()
                    sb.auth.sign_up({"email": email_norm, "password": password})
                    st.success("가입 완료! Supabase Auth 이메일로 발송된 인증 링크 클릭 후 로그인해주세요.")
                except Exception as e:
                    st.error(f"오류: {str(e)}")

    st.markdown("</div>", unsafe_allow_html=True)
