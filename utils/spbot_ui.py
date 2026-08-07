"""SP봇 UI — 사이드바 상단 진입 버튼 + 채팅 dialog."""
import streamlit as st
from utils.spbot_answer import answer


def _inject_style():
    st.markdown(
        """
        <style>
        .spbot-notice {
            font-size: 11px; color: #666;
            background: #FFF8E1; border-left: 3px solid #F2A93B;
            border-radius: 4px; padding: 6px 10px; margin-bottom: 10px;
        }
        .spbot-src {
            font-size: 11px; color: #8a6210;
            background: #FFF8E1; border-radius: 4px;
            padding: 4px 8px; margin: 4px 0;
        }
        .spbot-src a { color: #8a6210; text-decoration: none; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _keep_dialog():
    """내부 rerun 시 다이얼로그가 다시 열리도록 플래그 재세팅."""
    st.session_state["_spbot_open"] = True


@st.dialog("SP봇 · 사내 지식 검색")
def _spbot_dialog():
    # 첫 렌더 시 플래그 pop → X 닫기 시 페이지 이동/rerun에도 재오픈되지 않음
    st.session_state.pop("_spbot_open", None)
    st.markdown(
        "<div class='spbot-notice'>💡 부정확한 답변이 있을 수 있으니 관련 문서를 함께 확인해주세요.</div>",
        unsafe_allow_html=True,
    )

    if "_spbot_chat" not in st.session_state:
        st.session_state["_spbot_chat"] = [{
            "role": "assistant",
            "text": "안녕하세요! 매체 가이드·업무 관련 질문에 답변합니다.\n\n예) *네이버 GFA 계정 이관 절차*",
            "sources": [],
        }]

    # 채팅 히스토리 렌더 (st.chat_message로 markdown 자동 처리)
    for msg in st.session_state["_spbot_chat"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["text"])
            if msg.get("sources"):
                st.markdown("**참고한 내부 문서**")
                for s in msg["sources"][:3]:
                    st.markdown(
                        f"<div class='spbot-src'>📎 "
                        f"<a href='{s['source_link']}' target='_blank'>"
                        f"[{s['doc_id']}] {s['title']}</a> · {s['source_channel']}</div>",
                        unsafe_allow_html=True,
                    )
            if msg.get("web_sources"):
                st.markdown("**참고한 웹 출처**")
                for s in msg["web_sources"][:5]:
                    title = s.get("title") or s.get("uri", "")
                    st.markdown(
                        f"<div class='spbot-src'>🌐 "
                        f"<a href='{s['uri']}' target='_blank'>{title}</a></div>",
                        unsafe_allow_html=True,
                    )

    question = st.chat_input("질문을 입력하세요")
    if question:
        st.session_state["_spbot_chat"].append(
            {"role": "user", "text": question, "sources": []}
        )
        with st.spinner("답변 생성 중..."):
            try:
                result = answer(question)
                st.session_state["_spbot_chat"].append({
                    "role": "assistant",
                    "text": result["text"],
                    "sources": result["sources"],
                    "stage": result["stage"],
                })
            except Exception as e:
                st.session_state["_spbot_chat"].append({
                    "role": "assistant",
                    "text": f"❌ 오류: {e}",
                    "sources": [],
                })
        _keep_dialog()
        st.rerun()

    col1, col2 = st.columns([1, 1])
    if col1.button("대화 초기화", key="_spbot_clear", use_container_width=True):
        st.session_state.pop("_spbot_chat", None)
        _keep_dialog()
        st.rerun()
    if col2.button("닫기", key="_spbot_close",
                   type="primary", use_container_width=True):
        st.rerun()


def render_spbot_trigger():
    """모든 페이지 공통 진입점 — 사이드바에 SP봇 진입 버튼 배치.
    Streamlit이 진짜 floating(position:fixed) 클릭 이벤트를 지원 안 해 사이드바 사용.
    """
    _inject_style()

    with st.sidebar:
        if st.button("💬 SP봇에게 질문", key="_spbot_open_btn",
                     use_container_width=True):
            st.session_state["_spbot_open"] = True
            st.rerun()

    if st.session_state.get("_spbot_open"):
        _spbot_dialog()
