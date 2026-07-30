import streamlit as st
from utils.sheets import (
    get_major_categories,
    get_sub_categories,
    get_media_detail,
    update_media_info,
    create_media_info,
    to_download_url,
)

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

        div[data-testid="stSegmentedControl"] * { font-size: 14px !important; }

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
        div[data-testid="stTabs"] button p {
            font-size: 13px !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def set_current_page(page_name: str) -> None:
    st.session_state["_current_page"] = page_name


def _current_page() -> str:
    return st.session_state.get("_current_page", "unknown")


# ---------------------------------------------------------------------------
# 단일 dialog 디스패처
# ---------------------------------------------------------------------------

def request_detail(media_id: str) -> None:
    st.session_state["_active_dialog"] = ("detail", media_id, _current_page())
    st.rerun()


def request_update(media_id: str) -> None:
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

    if origin_page != _current_page():
        st.session_state["_active_dialog"] = None
        return

    st.session_state["_active_dialog"] = None

    if kind == "detail":
        _detail_dialog(payload)
    elif kind == "register":
        _register_dialog()
    elif kind == "mail":
        _mail_dialog(payload)


def _close_dialog() -> None:
    st.session_state["_active_dialog"] = None


# ---------------------------------------------------------------------------
# 카드 그리드
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
# 검색 결과 표
# ---------------------------------------------------------------------------

def render_result_table(media_list: list[dict], key_prefix: str) -> None:
    if not media_list:
        st.caption("표시할 매체가 없습니다.")
        return

    col_ratio = [1.8, 1.2, 0.9, 1.3, 1.9, 1.9, 1, 0.9]

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
            c.markdown("<div style='padding-bottom:6px; margin-bottom:10px; min-height:1px;'>&nbsp;</div>", unsafe_allow_html=True)

    for m in media_list:
        contact = (m.get("contacts") or [{}])[0] if m.get("contacts") else {}
        phone = contact.get("phone") or ""
        email = contact.get("email") or ""
        team_email = contact.get("team_email") or ""
        intro_url = m.get("intro_doc_url") or ""

        cols = st.columns(col_ratio)
        # 매체명 — 소개서 URL 있으면 하이퍼링크
        if intro_url:
            cols[0].markdown(
                f"<a href='{intro_url}' target='_blank' rel='noopener' "
                f"style='color:#0B0B0B; text-decoration:underline; "
                f"text-decoration-color:#B0B0B0; text-underline-offset:3px;' "
                f"title='매체소개서 열기'>{m['name']}</a>",
                unsafe_allow_html=True,
            )
        else:
            cols[0].write(m["name"])
        cols[1].write(contact.get("manager_name") or "-")
        cols[2].write(contact.get("position") or "-")

        if phone:
            cols[3].markdown(
                f"<a href='tel:{phone.replace('-','')}' style='color:#0B0B0B;'>{phone}</a>",
                unsafe_allow_html=True,
            )
        else:
            cols[3].write("-")

        cols[4].write(email or "-")
        cols[5].write(team_email or "-")

        if cols[6].button("업데이트", key=f"upd_{key_prefix}_{m['id']}", use_container_width=True):
            request_update(m["id"])

        has_email = bool(email or team_email)
        if has_email:
            if cols[7].button("메일", key=f"mail_{key_prefix}_{m['id']}", use_container_width=True):
                st.session_state["_active_dialog"] = ("mail", (email, team_email), _current_page())
                st.rerun()
        else:
            cols[7].button("메일", key=f"mail_{key_prefix}_{m['id']}", disabled=True, use_container_width=True)


# ---------------------------------------------------------------------------
# HOME 기본 컨택포인트 표
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
    if not value:
        return "-"
    if "T" not in str(value):
        return str(value)
    from datetime import datetime
    from zoneinfo import ZoneInfo
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        dt_kst = dt.astimezone(ZoneInfo("Asia/Seoul"))
        return dt_kst.strftime("%Y-%m-%d")
    except Exception:
        return value


def render_contact_detail_table(contact: dict) -> None:
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
    m = get_media_detail(media_id)
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
            col_view, col_dl = st.columns([1, 1])
            with col_view:
                st.link_button("확인", m["intro_doc_url"], use_container_width=True)
            with col_dl:
                st.link_button("다운로드", to_download_url(m["intro_doc_url"]),
                              use_container_width=True)
        else:
            st.caption("등록된 소개서 링크가 없습니다.")

        st.write("**담당자 컨택 포인트**")
        render_contact_detail_table(contact)

        if m.get("memo"):
            st.write("**메모**")
            st.markdown(
                f"<div style='background:#F6F8FC; border:1px solid #E5EAF5; "
                f"border-radius:8px; padding:10px 12px; font-size:13px; "
                f"white-space:pre-wrap; line-height:1.5;'>{m['memo']}</div>",
                unsafe_allow_html=True,
            )

        st.caption(f"업데이트 일자: {format_updated_at(m.get('updated_at'))}")

        if st.button("닫기", key=f"close_{media_id}"):
            _close_dialog()
            st.rerun()

    else:
        majors = get_major_categories()
        cur_major = cat.get("major_category", majors[0] if majors else "")
        major = st.selectbox("대분류", majors, index=majors.index(cur_major) if cur_major in majors else 0)

        sub = None
        if major == "05 버티컬 미디어":
            subs = get_sub_categories(major)
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
        memo = st.text_area("메모", value=m.get("memo") or "", height=80,
                            placeholder="계약 조건 · 특약사항 · 담당자 부재 정보 등 자유 입력")

        if st.button("저장", type="primary"):
            if not name or not major or not manager_name:
                st.error("매체명 / 대분류 / 담당자명은 필수입니다.")
            else:
                update_media_info(
                    media_id,
                    name=name,
                    major=major,
                    sub=sub,
                    doc_url=doc_url or None,
                    manager_name=manager_name,
                    position=position or None,
                    phone=phone or None,
                    email=email or None,
                    team_email=team_email or None,
                    last_contact=last_contact or None,
                    memo=memo or None,
                )
                st.session_state[f"edit_{media_id}"] = False
                _close_dialog()
                st.success("저장되었습니다.")
                st.rerun()


@st.dialog("신규 매체 등록")
def _register_dialog() -> None:
    majors = get_major_categories()
    major_options = majors + ["+ 새 대분류 추가"]
    major_choice = st.selectbox("대분류*", major_options)
    major = st.text_input("새 대분류명 입력") if major_choice == "+ 새 대분류 추가" else major_choice

    sub = None
    if major == "05 버티컬 미디어":
        subs = get_sub_categories(major)
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
    memo = st.text_area("메모", value="", height=80,
                        placeholder="계약 조건 · 특약사항 · 담당자 부재 정보 등 자유 입력")

    if st.button("등록", type="primary"):
        if not major or not name or not manager_name or (major == "05 버티컬 미디어" and not sub):
            st.error("필수값(대분류 / 중분류(05인 경우) / 매체명 / 담당자명)을 확인해주세요.")
        else:
            create_media_info(
                name=name,
                major=major,
                sub=sub,
                doc_url=doc_url or None,
                manager_name=manager_name,
                position=position or None,
                phone=phone or None,
                email=email or None,
                team_email=team_email or None,
                last_contact=last_contact or None,
                memo=memo or None,
            )
            _close_dialog()
            st.success(f"'{name}' 매체가 등록되었습니다.")
            st.rerun()


@st.dialog("메일 보내기")
def _mail_dialog(payload) -> None:
    email, team_email = payload

    if email and team_email:
        to_addr, cc_addr = email, team_email
    elif team_email:
        to_addr, cc_addr = team_email, ""
    else:
        to_addr, cc_addr = email, ""

    mailto = f"mailto:{to_addr}" + (f"?cc={cc_addr}" if cc_addr else "")
    works_params = f"orderType=new&to={to_addr}" + (f"&cc={cc_addr}" if cc_addr else "")
    works = f"https://mail.worksmobile.com/w/compose?{works_params}"

    st.markdown(
        f"<a href='{mailto}' style='display:block; background:#0B0B0B; color:#fff; "
        f"padding:10px 0; border-radius:8px; font-size:14px; text-decoration:none; "
        f"text-align:center; margin-bottom:8px;'>Outlook으로 보내기</a>"
        f"<a href='{works}' target='_blank' style='display:block; background:#03C75A; color:#fff; "
        f"padding:10px 0; border-radius:8px; font-size:14px; text-decoration:none; "
        f"text-align:center;'>네이버웍스로 보내기</a>",
        unsafe_allow_html=True,
    )
    st.caption("💡 Outlook: Win+I → 앱 → Outlook → MAILTO: Outlook 지정 시 발송 가능")
