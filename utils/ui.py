import streamlit as st
from utils import db

NAVY = "#1E2761"
ICE = "#CADCFC"


def inject_base_style() -> None:
    st.markdown(
        """
        <style>
        @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');
        html, body, [class*="css"] { font-family: 'Pretendard', sans-serif; }

        .media-card {
            background: #F6F8FC;
            border-radius: 10px;
            padding: 14px 16px;
            margin-bottom: 8px;
            border: 1px solid #E5EAF5;
        }

        .section-title {
            color: #0B0B0B;
            font-weight: 700;
            font-size: 22px;
            margin-top: 28px;
            margin-bottom: 10px;
        }

        .contact-table { width: 100%; border-collapse: collapse; margin-top: 4px; }
        .contact-table td {
            padding: 7px 10px;
            border-bottom: 1px solid #E5EAF5;
            font-size: 14px;
        }
        .contact-table td.label {
            font-weight: 600;
            color: #0B0B0B;
            width: 130px;
            white-space: nowrap;
        }

        /* segmented_control 텍스트를 버튼 텍스트와 동일하게 (14px) */
        div[data-testid="stSegmentedControl"] * { font-size: 14px !important; }

        /* 마일스톤 카드(매체 버튼)와 05 익스팬더 높이 통일 (48px) */
        div[data-testid="stExpander"] { margin-bottom: 8px !important; }
        div[data-testid="stExpander"] summary {
            height: 48px !important;
            box-sizing: border-box !important;
            display: flex !important;
            align-items: center !important;
            padding: 0 14px !important;
        }
        div[data-testid="stExpander"] summary p {
            font-size: 14px !important;
            margin: 0 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def set_current_page(page_name: str) -> None:
    """각 페이지 상단에서 호출. 팝업이 어느 페이지에서 열렸는지 추적하기 위함."""
    st.session_state["_current_page"] = page_name


def _current_page() -> str:
    return st.session_state.get("_current_page", "unknown")


# ---------------------------------------------------------------------------
# 단일 dialog 디스패처
# - 같은 실행(run) 안에서 dialog 함수가 두 번 이상 호출되면 Streamlit이 에러를 내므로,
#   모든 버튼은 session_state에 "어떤 dialog를 열지"만 기록하고, 페이지 마지막에
#   render_pending_dialog() 한 번만 호출해서 실제로 연다.
# - Streamlit의 dialog는 X(닫기)/ESC로 닫아도 session_state가 자동으로 비워지지 않는다.
#   그 상태로 다른 페이지로 이동하면 session_state가 그대로 남아있어 팝업이 다시 떠버린다.
#   이를 막기 위해 dialog를 열 때 "어느 페이지에서 열렸는지"를 같이 저장해두고,
#   현재 페이지와 다르면 자동으로 폐기(클리어)한다.
# ---------------------------------------------------------------------------

def request_detail(media_id: str) -> None:
    st.session_state["_active_dialog"] = ("detail", media_id, _current_page())
    st.rerun()


def request_update(media_id: str) -> None:
    """상세 팝업을 곧바로 수정(편집) 모드로 열기"""
    st.session_state[f"edit_{media_id}"] = True
    st.session_state["_active_dialog"] = ("detail", media_id, _current_page())
    st.rerun()


def request_register() -> None:
    st.session_state["_active_dialog"] = ("register", None, _current_page())
    st.rerun()


def render_pending_dialog() -> None:
    dialog = st.session_state.get("_active_dialog")
    if not dialog:
        return
    kind, payload, origin_page = dialog

    # 팝업을 연 페이지와 현재 페이지가 다르면(=다른 메뉴로 이동) 폐기하고 렌더링하지 않음
    if origin_page != _current_page():
        st.session_state["_active_dialog"] = None
        return

    if kind == "detail":
        _detail_dialog(payload)
    elif kind == "register":
        _register_dialog()


def _close_dialog() -> None:
    st.session_state["_active_dialog"] = None


# ---------------------------------------------------------------------------
# 카드 그리드 (마일스톤, 매체명만 표시, 콘텐츠 양만큼 자동 줄바꿈)
# ---------------------------------------------------------------------------

def render_media_grid(media_list: list[dict], key_prefix: str, n_cols: int = 5) -> None:
    if not media_list:
        st.caption("등록된 매체가 없습니다.")
        return

    rows = (len(media_list) + n_cols - 1) // n_cols
    idx = 0
    for _ in range(rows):
        cols = st.columns(n_cols)
        for c in cols:
            if idx >= len(media_list):
                break
            m = media_list[idx]
            with c:
                if st.button(m["name"], key=f"{key_prefix}_{m['id']}", use_container_width=True):
                    request_detail(m["id"])
            idx += 1


# ---------------------------------------------------------------------------
# 표 형태 결과 (검색 결과 전용 - 상세버튼 포함)
# ---------------------------------------------------------------------------

def render_result_table(media_list: list[dict], key_prefix: str) -> None:
    """검색 결과 표: 매체명 | 담당자 | 직급 | 연락처 | 이메일 | 팀메일 | [업데이트]
    (이미 db.search_media에서 마지막컨택이력 최신순으로 정렬되어 들어옴)"""
    if not media_list:
        st.caption("표시할 매체가 없습니다.")
        return

    col_ratio = [2, 1.4, 1, 1.4, 2, 2, 1.2]

    header = st.columns(col_ratio)
    labels = ["매체명", "담당자", "직급", "연락처", "이메일", "팀메일"]
    for i, c in enumerate(header):
        if i < len(labels):
            c.markdown(
                f"<div style='font-weight:600; color:#0B0B0B; padding-bottom:6px; "
                f"border-bottom:2px solid #0B0B0B; margin-bottom:10px;'>{labels[i]}</div>",
                unsafe_allow_html=True,
            )
        else:
            # 마지막(업데이트 버튼) 컬럼: 밑줄 없이 높이만 맞춰 자리 확보
            c.markdown("<div style='padding-bottom:6px; margin-bottom:10px; min-height:1px;'>&nbsp;</div>", unsafe_allow_html=True)

    for m in media_list:
        contact = (m.get("contacts") or [{}])[0] if m.get("contacts") else {}
        cols = st.columns(col_ratio)
        cols[0].write(m["name"])
        cols[1].write(contact.get("manager_name") or "-")
        cols[2].write(contact.get("position") or "-")
        cols[3].write(contact.get("phone") or "-")
        cols[4].write(contact.get("email") or "-")
        cols[5].write(contact.get("team_email") or "-")
        if cols[6].button("업데이트", key=f"{key_prefix}_{m['id']}"):
            request_update(m["id"])


# ---------------------------------------------------------------------------
# HOME 기본 화면용 컨택포인트 표 (클릭 불가, 단순 조회용)
# ---------------------------------------------------------------------------

def render_contact_table(media_list: list[dict]) -> None:
    import pandas as pd
    rows = []
    for m in media_list:
        contact = (m.get("contacts") or [{}])[0] if m.get("contacts") else {}
        rows.append({
            "매체명": m.get("name"),
            "담당자명": contact.get("manager_name") or "-",
            "직급": contact.get("position") or "-",
            "연락처": contact.get("phone") or "-",
            "이메일": contact.get("email") or "-",
            "팀메일": contact.get("team_email") or "-",
        })
    if not rows:
        st.caption("표시할 매체가 없습니다.")
        return
    df = pd.DataFrame(rows)
    st.dataframe(df, hide_index=True, use_container_width=True)


# ---------------------------------------------------------------------------
# 보조 함수
# ---------------------------------------------------------------------------

def format_updated_at(value: str | None) -> str:
    """ISO(UTC) 문자열을 Asia/Seoul 기준 YYYY-MM-DD 로 변환"""
    if not value:
        return "-"
    from datetime import datetime
    from zoneinfo import ZoneInfo
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        dt_kst = dt.astimezone(ZoneInfo("Asia/Seoul"))
        return dt_kst.strftime("%Y-%m-%d")
    except Exception:
        return value


def render_contact_detail_table(contact: dict) -> None:
    """매체 상세 팝업 내 담당자 컨택포인트 - 5행 표 형태"""
    manager_label = " ".join(
        p for p in [contact.get("manager_name"), contact.get("position")] if p
    ) or "-"
    rows = [
        ("담당자/직급", manager_label),
        ("연락처", contact.get("phone") or "-"),
        ("이메일", contact.get("email") or "-"),
        ("팀메일", contact.get("team_email") or "-"),
        ("마지막 컨택", contact.get("last_contact_date") or "-"),
    ]
    html = "<table class='contact-table'>" + "".join(
        f"<tr><td class='label'>{k}</td><td>{v}</td></tr>" for k, v in rows
    ) + "</table>"
    st.markdown(html, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# 상세/수정 dialog
# ---------------------------------------------------------------------------

@st.dialog("매체 상세 정보")
def _detail_dialog(media_id: str) -> None:
    m = db.get_media_detail(media_id)
    contact = (m.get("contacts") or [{}])[0] if m.get("contacts") else {}
    cat = m.get("categories") or {}

    edit_mode = st.session_state.get(f"edit_{media_id}", False)

    top_l, top_r = st.columns([5, 1])
    with top_l:
        st.markdown(f"### {m['name']}")
    with top_r:
        if st.button("수정", key=f"edit_btn_{media_id}"):
            st.session_state[f"edit_{media_id}"] = not edit_mode
            st.rerun()

    if not edit_mode:
        st.write("**매체소개서**")
        if m.get("intro_doc_url"):
            st.link_button("확인 / 다운로드", m["intro_doc_url"])
        else:
            st.caption("등록된 소개서 링크가 없습니다.")

        st.write("**담당자 컨택 포인트**")
        render_contact_detail_table(contact)

        st.caption(f"업데이트 일자: {format_updated_at(m.get('updated_at'))}")

        if st.button("닫기", key=f"close_{media_id}"):
            _close_dialog()
            st.rerun()

    else:
        majors = db.get_major_categories()
        cur_major = cat.get("major_category", majors[0] if majors else "")
        major = st.selectbox("대분류", majors, index=majors.index(cur_major) if cur_major in majors else 0)

        sub = None
        if major == "05 버티컬 미디어":
            subs = db.get_sub_categories(major)
            cur_sub = cat.get("sub_category")
            options = subs + ["+ 새 중분류 추가"]
            default_idx = options.index(cur_sub) if cur_sub in options else 0
            choice = st.selectbox("중분류", options, index=default_idx)
            sub = st.text_input("새 중분류명 입력") if choice == "+ 새 중분류 추가" else choice

        name = st.text_input("매체명", value=m["name"])
        doc_url = st.text_input("매체소개서 링크", value=m.get("intro_doc_url") or "")

        st.divider()
        manager_name = st.text_input("담당자명*", value=contact.get("manager_name") or "")
        position = st.text_input("직급", value=contact.get("position") or "")
        phone = st.text_input("연락처", value=contact.get("phone") or "")
        email = st.text_input("담당자 메일", value=contact.get("email") or "")
        team_email = st.text_input("팀메일", value=contact.get("team_email") or "")
        last_contact = st.text_input("마지막 컨택일 (YYYY-MM-DD)", value=contact.get("last_contact_date") or "")

        if st.button("저장", type="primary"):
            if not name or not major or not manager_name:
                st.error("매체명 / 대분류 / 담당자명은 필수입니다.")
            else:
                db.update_media(media_id, name, major, sub, doc_url or None)
                db.upsert_contact(contact.get("id"), media_id, manager_name, position or None,
                                   phone or None, email or None, team_email or None, last_contact or None)
                st.session_state[f"edit_{media_id}"] = False
                _close_dialog()
                st.success("저장되었습니다.")
                st.rerun()


@st.dialog("신규 매체 등록")
def _register_dialog() -> None:
    majors = db.get_major_categories()
    major_options = majors + ["+ 새 대분류 추가"]
    major_choice = st.selectbox("대분류*", major_options)
    major = st.text_input("새 대분류명 입력") if major_choice == "+ 새 대분류 추가" else major_choice

    sub = None
    if major == "05 버티컬 미디어":
        subs = db.get_sub_categories(major)
        sub_options = subs + ["+ 새 중분류 추가"]
        sub_choice = st.selectbox("중분류*", sub_options)
        sub = st.text_input("새 중분류명 입력") if sub_choice == "+ 새 중분류 추가" else sub_choice

    name = st.text_input("매체명*")
    doc_url = st.text_input("매체소개서 링크 (드라이브-전체 공개)")

    st.divider()
    manager_name = st.text_input("담당자명*")
    position = st.text_input("직급")
    phone = st.text_input("연락처")
    email = st.text_input("담당자메일")
    team_email = st.text_input("팀메일")
    last_contact = st.text_input("마지막컨택일 (YYYY-MM-DD)")

    if st.button("등록", type="primary"):
        if not major or not name or not manager_name or (major == "05 버티컬 미디어" and not sub):
            st.error("필수값(대분류 / 중분류(05인 경우) / 매체명 / 담당자명)을 확인해주세요.")
        else:
            db.create_media(name, major, sub, doc_url or None, manager_name,
                             position or None, phone or None, email or None,
                             team_email or None, last_contact or None)
            _close_dialog()
            st.success(f"'{name}' 매체가 등록되었습니다.")
            st.rerun()
