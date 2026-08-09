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
            overflow-wrap: anywhere; word-break: break-word;
        }
        .spbot-src a {
            color: #8a6210; text-decoration: none;
            overflow-wrap: anywhere; word-break: break-word;
        }
        /* SP봇 다이얼로그 안 채팅 메시지 텍스트 줄바꿈 강제 */
        [data-testid="stDialog"] [data-testid="stChatMessage"] {
            overflow-wrap: anywhere; word-break: break-word;
        }
        [data-testid="stDialog"] [data-testid="stChatMessage"] a {
            overflow-wrap: anywhere; word-break: break-all;
        }
        [data-testid="stDialog"] [data-testid="stChatMessage"] p,
        [data-testid="stDialog"] [data-testid="stChatMessage"] li {
            overflow-wrap: anywhere; word-break: break-word;
            max-width: 100%;
        }
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
            "qna_sources": [],
        }]

    # 채팅 히스토리 렌더 (st.chat_message로 markdown 자동 처리)
    for msg in st.session_state["_spbot_chat"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["text"])
            stage = msg.get("stage")
            if stage:
                stage_label = {
                    "internal": "🟢 내부 자료 기반",
                    "web": "🌐 웹 검색 기반 (내부 자료 불충분)",
                    "no_candidates_web": "🌐 웹 검색 기반 (매칭 문서 없음)",
                }.get(stage, "")
                if stage_label:
                    st.caption(stage_label)
            if msg.get("sources"):
                st.markdown("**참고한 내부 문서**")
                for s in msg["sources"][:3]:
                    st.markdown(
                        f"<div class='spbot-src'>📎 "
                        f"<a href='{s['source_link']}' target='_blank'>"
                        f"[{s['doc_id']}] {s['title']}</a> · {s['source_channel']}</div>",
                        unsafe_allow_html=True,
                    )
            if msg.get("qna_sources"):
                st.markdown("**참고한 게시판 글**")
                for q in msg["qna_sources"][:3]:
                    qna_id = q.get("qna_id", "")
                    title = q.get("title", "")
                    qna_link = f"http://works.dplan360.emato.net/page/qnaDetail.php?id={qna_id}"
                    st.markdown(
                        f"<div class='spbot-src'>📋 "
                        f"<a href='{qna_link}' target='_blank'>"
                        f"[Q{qna_id}] {title}</a></div>",
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
            {"role": "user", "text": question, "sources": [], "qna_sources": []}
        )
        with st.spinner("답변 생성 중..."):
            try:
                result = answer(question)
                st.session_state["_spbot_chat"].append({
                    "role": "assistant",
                    "text": result["text"],
                    "sources": result.get("sources", []),
                    "qna_sources": result.get("qna_sources", []),
                    "stage": result["stage"],
                })
            except Exception as e:
                st.session_state["_spbot_chat"].append({
                    "role": "assistant",
                    "text": f"❌ 오류: {e}",
                    "sources": [],
                    "qna_sources": [],
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
