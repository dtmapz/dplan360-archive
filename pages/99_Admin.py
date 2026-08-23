import streamlit as st
from utils.auth import get_current_user, is_admin
from utils.ui import set_current_page

set_current_page("admin")

user = get_current_user()

if not is_admin():
    st.warning("관리자 전용 페이지입니다.")
    st.stop()

st.markdown(
    "<div style='font-size:20px;font-weight:700;margin-bottom:4px;'>⚙️ 관리자</div>",
    unsafe_allow_html=True,
)
st.markdown(
    "<div style='font-size:13px;color:var(--text-muted);margin-bottom:20px;'>"
    "조직도·화이트리스트 관리 기능</div>",
    unsafe_allow_html=True,
)

# ============================
# 조직도 → Supabase 화이트리스트 동기화
# ============================
st.markdown(
    "<div style='font-size:15px;font-weight:600;margin-bottom:4px;'>"
    "🔄 조직도 → 회원가입 화이트리스트 동기화</div>",
    unsafe_allow_html=True,
)
st.markdown(
    "<div style='font-size:12px;color:var(--text-muted);margin-bottom:12px;'>"
    "조직도 시트(organization 탭)의 활성 이메일을 Supabase 화이트리스트에 반영합니다.<br>"
    "시트에서 사라진(또는 is_active=N 처리된) 이메일은 화이트리스트에서 제거됩니다."
    "<br>※ GitHub Actions로 매일 새벽 자동 실행되지만, 즉시 반영이 필요할 때만 클릭하세요."
    "</div>",
    unsafe_allow_html=True,
)

if st.button("동기화 실행", type="primary", key="sync_org_btn"):
    with st.spinner("동기화 중..."):
        try:
            from utils.org_sync import sync_allowlist
            result = sync_allowlist()
            st.success(
                f"완료: 활성 {result['total']}명 · "
                f"추가 {len(result['added'])}건 · "
                f"제거 {len(result['removed'])}건 · "
                f"유지 {result['kept']}건"
            )
            if result["added"]:
                with st.expander(f"추가된 이메일 ({len(result['added'])}건)"):
                    st.write("\n".join(f"- {e}" for e in result["added"]))
            if result["removed"]:
                with st.expander(f"제거된 이메일 ({len(result['removed'])}건)"):
                    st.write("\n".join(f"- {e}" for e in result["removed"]))
        except Exception as e:
            st.error(f"동기화 실패: {e}")
