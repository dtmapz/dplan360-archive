import streamlit as st
from utils.db import get_client

ALLOWED_DOMAIN = "@d-plan360.com"


def get_current_user():
    """세션에서 현재 로그인 사용자 반환. 없으면 None."""
    return st.session_state.get("user", None)


def is_admin():
    """현재 사용자가 admin role인지 확인."""
    user = get_current_user()
    if not user:
        return False
    meta = user.get("user_metadata") or {}
    return meta.get("role") == "admin"


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
                try:
                    sb = get_client()
                    res = sb.auth.sign_in_with_password({"email": email, "password": password})
                    st.session_state["user"] = res.user.__dict__
                    st.rerun()
                except Exception as e:
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
            if not email or not password or not password_confirm:
                st.error("모든 항목을 입력해주세요.")
            elif not email.endswith(ALLOWED_DOMAIN):
                st.error(f"D-PLAN360 사내 이메일({ALLOWED_DOMAIN})만 가입 가능합니다.")
            elif len(password) < 8:
                st.error("비밀번호는 8자 이상이어야 합니다.")
            elif password != password_confirm:
                st.error("비밀번호가 일치하지 않습니다.")
            else:
                try:
                    sb = get_client()
                    sb.auth.sign_up({"email": email, "password": password})
                    st.success("가입 완료! Supabase Auth 이메일로 발송된 인증 링크 클릭 후 로그인해주세요.")
                except Exception as e:
                    st.error(f"오류: {str(e)}")

    st.markdown("</div>", unsafe_allow_html=True)
