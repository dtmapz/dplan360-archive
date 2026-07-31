import streamlit as st
from utils.sheets import (
    get_major_categories,
    get_sub_categories,
    get_media_detail,
    update_media_info,
    create_media_info,
    to_download_url,
    has_media_hub,
    get_hub_by_media,
    get_media_notice,
    get_media_notice_any,
    add_hub_item,
    update_hub_item,
    delete_hub_item,
    delete_section,
    upsert_notice,
    delete_notice,
)
from utils.auth import is_admin
from utils.db import upload_notice_image
from st_click_detector import click_detector

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
    prev = st.session_state.get("_current_page")
    if prev and prev != page_name:
        # 페이지 이동 시 진행 중인 다이얼로그 상태 정리
        st.session_state.pop("_active_dialog", None)
    st.session_state["_current_page"] = page_name


def _current_page() -> str:
    return st.session_state.get("_current_page", "unknown")


# ---------------------------------------------------------------------------
# 단일 dialog 디스패처
# ---------------------------------------------------------------------------

def request_detail(media_id: str) -> None:
    """매체 상세 요청. 미디어허브 자료 有 → hub 다이얼로그, 無 → 기존 컨택 다이얼로그.
    항상 조회 모드로 시작 (편집은 팝업 내 [수정]/[편집] 버튼으로만 진입).
    """
    st.session_state[f"edit_{media_id}"] = False  # 조회 모드 강제
    if has_media_hub(media_id):
        st.session_state["_active_dialog"] = ("hub", media_id, _current_page())
    else:
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
    elif kind == "hub":
        _hub_dialog(payload)
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

    col_ratio = [2.0, 1.3, 0.9, 1.4, 2.0, 2.0, 0.9]

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
        is_hub = has_media_hub(m["id"])

        # 미디어허브 배지 (hub 활성 매체만)
        hub_badge = (
            "<span style='display:inline-block;font-size:10px;font-weight:600;"
            "letter-spacing:0.06em;color:#7a5610;background:#F2A93B;"
            "padding:1px 6px;border-radius:3px;margin-left:6px;vertical-align:2px;'>허브</span>"
            if is_hub else ""
        )

        cols = st.columns(col_ratio)
        # 매체명 — 소개서 URL 있으면 하이퍼링크 + 허브 배지
        if intro_url:
            cols[0].markdown(
                f"<a href='{intro_url}' target='_blank' rel='noopener' "
                f"style='color:#0B0B0B; text-decoration:underline; "
                f"text-decoration-color:#B0B0B0; text-underline-offset:3px;' "
                f"title='매체소개서 열기'>{m['name']}</a>{hub_badge}",
                unsafe_allow_html=True,
            )
        else:
            cols[0].markdown(f"{m['name']}{hub_badge}", unsafe_allow_html=True)
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

        # [확인] — 팝업 or 미디어허브 뷰로 자동 라우팅 (has_media_hub 기준)
        if cols[6].button("확인", key=f"view_{key_prefix}_{m['id']}",
                          use_container_width=True, type="secondary"):
            request_detail(m["id"])


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
            # rerun 후 다이얼로그 재오픈 (render_pending_dialog가 이미 pop해서 재세팅 필요)
            st.session_state["_active_dialog"] = ("detail", media_id, _current_page())
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
                # 다이얼로그 재오픈 (hub 편집 영역 계속 사용 가능하도록)
                st.session_state["_active_dialog"] = ("detail", media_id, _current_page())
                st.success("저장되었습니다.")
                st.rerun()

        # ─── 미디어허브 편집 영역 (관리자 전용) ───
        _render_hub_edit_area(media_id)


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


# ---------------------------------------------------------------------------
# 미디어허브 뷰 (팝업 대체)
# ---------------------------------------------------------------------------



_HUB_STYLE_INJECTED_KEY = "_hub_css_injected"


def _inject_hub_style():
    """미디어허브 뷰 전용 CSS. 세션당 1회 삽입."""
    if st.session_state.get(_HUB_STYLE_INJECTED_KEY):
        return
    st.session_state[_HUB_STYLE_INJECTED_KEY] = True
    st.markdown("""
    <style>
    /* ===== 미디어허브 뷰 스타일 ===== */

    /* 공지 노란 박스: st.container(border=True)에 marker 있는 것을 노란 배경으로 오버라이드 */
    [data-testid="stVerticalBlockBorderWrapper"]:has(.notice-yellow-marker) {
        background: #FFF3D6 !important;
        border: 1px solid rgba(242,169,59,0.5) !important;
        border-radius: 10px !important;
    }

    /* 컬럼 사이 간격 축소 (hub view 내부) */
    [data-testid="stVerticalBlock"]:has(.hub-view-marker) > [data-testid="stHorizontalBlock"] {
        gap: 0.25rem !important;
    }

    /* 버튼 텍스트 강제 한 줄 (hub view 내 모든 버튼) */
    [data-testid="stVerticalBlock"]:has(.hub-view-marker) button p {
        white-space: nowrap !important;
    }
    [data-testid="stVerticalBlock"]:has(.hub-view-marker) button {
        padding-left: 8px !important;
        padding-right: 8px !important;
    }

    /* Expander (자료 추가 · 새 섹션 추가) 미니멀화 */
    [data-testid="stVerticalBlock"]:has(.hub-view-marker) [data-testid="stExpander"] summary {
        font-size: 12px !important;
        color: #7B7770 !important;
    }
    [data-testid="stVerticalBlock"]:has(.hub-view-marker) [data-testid="stExpander"] {
        border: 1px dashed #C8C5BE !important;
        border-radius: 6px !important;
        background: transparent !important;
    }

    .hub-view-marker, .notice-yellow-marker { display: none; }
    </style>
    """, unsafe_allow_html=True)


def _keep_detail_dialog(media_id: str) -> None:
    """Detail 다이얼로그가 rerun 후에도 유지되도록 _active_dialog 재설정."""
    st.session_state["_active_dialog"] = ("detail", media_id, _current_page())
    st.session_state[f"edit_{media_id}"] = True  # 편집 모드 유지


def _render_hub_edit_area(media_id: str) -> None:
    """매체 상세 팝업(편집 모드) 하단에 붙는 hub 편집 영역."""
    _inject_hub_style()
    st.markdown('<span class="hub-view-marker"></span>', unsafe_allow_html=True)

    st.divider()

    # 현재 상태 요약
    sections = get_hub_by_media(media_id, include_intro_doc=False)
    notice = get_media_notice(media_id)
    n_items = sum(len(s["items"]) for s in sections)
    n_secs = len(sections)
    has_content = bool(sections) or bool(notice)

    status = (
        f"활성 · 섹션 {n_secs}개 · 자료 {n_items}개 · 공지 {'있음' if notice else '없음'}"
        if has_content else "비활성 · 자료·공지 없음"
    )

    with st.expander(f"📚 미디어허브 편집 · {status}", expanded=has_content):
        st.markdown(
            "<div style='background:#EEF3FC; border-left:3px solid #4A7BC8; "
            "border-radius:4px; padding:10px 14px; font-size:12px; color:#1a3a8a; "
            "line-height:1.7; margin-bottom:12px;'>"
            "<div style='font-weight:700; margin-bottom:6px;'>💡 저장 방식 안내</div>"
            "<div>• 매체 기본 정보 · 컨택 · 메모: <b>[저장] 버튼 클릭 시 반영</b></div>"
            "<div>• 미디어허브 (공지 · 섹션 · 자료): <b>각 항목마다 즉시 저장</b> · 별도 [저장] 버튼 불필요</div>"
            "<div style='margin-top:6px; color:#4a5a8a;'>자료·공지 하나 이상 등록 시 미디어허브 팝업으로 자동 전환</div>"
            "</div>",
            unsafe_allow_html=True,
        )

        # 공지 편집
        _render_hub_notice(media_id, admin=True, edit_mode=True)

        st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)

        # 섹션 + 자료 편집
        sections_full = get_hub_by_media(media_id, include_intro_doc=True)
        _render_hub_sections(media_id, sections_full, edit_mode=True)

        # 자료·섹션 추가 폼
        _render_hub_add_forms(media_id, sections_full)


@st.dialog("매체 미디어허브")
def _hub_dialog(media_id: str) -> None:
    """미디어허브 팝업. 조회 전용.
    상단 구조는 매체 상세 팝업(_detail_dialog 조회 모드)과 완전 동일하게 유지 → UI 위계 통일.
    """
    _inject_hub_style()
    st.markdown('<span class="hub-view-marker"></span>', unsafe_allow_html=True)

    media = get_media_detail(media_id)
    if not media or not media.get("name"):
        st.error("매체 정보를 찾을 수 없습니다.")
        return

    admin = is_admin()
    contact = (media.get("contacts") or [{}])[0] if media.get("contacts") else {}

    # === 매체 상세 팝업(조회 모드)와 완전 동일한 상단 구조 ===
    top_l, top_r = st.columns([5, 1])
    with top_l:
        st.markdown(f"### {media['name']}")
    with top_r:
        if admin:
            if st.button("편집", key=f"hub_to_edit_{media_id}"):
                # 편집은 매체 상세 팝업 → 하단 미디어허브 편집 영역에서 수행
                st.session_state[f"edit_{media_id}"] = True
                st.session_state["_active_dialog"] = ("detail", media_id, _current_page())
                st.rerun()

    st.write("**매체소개서**")
    if media.get("intro_doc_url"):
        col_view, col_dl = st.columns([1, 1])
        with col_view:
            st.link_button("확인", media["intro_doc_url"], use_container_width=True)
        with col_dl:
            st.link_button("다운로드", to_download_url(media["intro_doc_url"]),
                          use_container_width=True)
    else:
        st.caption("등록된 소개서 링크가 없습니다.")

    st.write("**담당자 컨택 포인트**")
    render_contact_detail_table(contact)

    if media.get("memo"):
        st.write("**메모**")
        st.markdown(
            f"<div style='background:#F6F8FC; border:1px solid #E5EAF5; "
            f"border-radius:8px; padding:10px 12px; font-size:13px; "
            f"white-space:pre-wrap; line-height:1.5;'>{media['memo']}</div>",
            unsafe_allow_html=True,
        )

    st.caption(f"업데이트 일자: {format_updated_at(media.get('updated_at'))}")
    # === 상단 종료 (여기까지 detail 팝업 조회 모드와 완전 동일) ===

    # ─ 공지 영역 ─ (조회 전용, 있을 때만)
    _render_hub_notice(media_id, admin=False, edit_mode=False)

    # ─ 미디어허브 섹션들 ─ (자동 편입 제외 · 매체소개서는 이미 위에 표시됨)
    #   미디어허브 헤더가 자체 border-top으로 구분선 역할 → st.divider() 불필요
    sections = get_hub_by_media(media_id, include_intro_doc=False)
    if sections:
        _render_hub_sections(media_id, sections, edit_mode=False)


def _render_hub_notice(media_id: str, admin: bool, edit_mode: bool) -> None:
    notice = get_media_notice(media_id)
    notice_any = get_media_notice_any(media_id) if admin else None

    if notice:
        # 마크다운을 미리 HTML로 변환해서 단일 st.markdown에 포함 (노란 박스 안에 완전히 포함되도록)
        import markdown as _md_parser
        html_body = _md_parser.markdown(
            notice["content"],
            extensions=["tables", "nl2br", "fenced_code"],
        )
        st.markdown(
            f"<div style='background:#FFF3D6; border:1px solid rgba(242,169,59,0.5); "
            f"border-radius:10px; padding:16px 20px; margin-bottom:16px;'>"
            f"<div style='display:inline-block; font-size:10px; letter-spacing:0.16em;"
            f"font-weight:700; color:#7a5610; background:#F2A93B;"
            f"padding:3px 10px; border-radius:3px; margin-bottom:12px;'>공지</div>"
            f"<div style='font-size:13px; line-height:1.6; color:#0B0B0B;'>"
            f"{html_body}"
            f"</div></div>",
            unsafe_allow_html=True,
        )

    if admin and edit_mode:
        with st.expander("📢 공지 편집", expanded=st.session_state.get("_hub_notice_edit", False)):
            current = notice_any["content"] if notice_any else ""
            current_active = notice_any["active"] if notice_any else True

            notice_key = f"_notice_ta_{media_id}"
            up_key = f"_notice_upload_{media_id}"
            last_fp_key = f"_notice_last_upload_{media_id}"
            err_key = f"_notice_err_{media_id}"
            suc_key = f"_notice_suc_{media_id}"

            # 초기화 (첫 진입 시만)
            if notice_key not in st.session_state:
                st.session_state[notice_key] = current

            # === 콜백 정의 (위젯 렌더 전 실행 → session_state 수정 안전) ===
            def _handle_upload():
                uploader = st.session_state.get(up_key)
                if uploader is None:
                    return
                fingerprint = f"{uploader.name}_{uploader.size}"
                if st.session_state.get(last_fp_key) == fingerprint:
                    return
                st.session_state[last_fp_key] = fingerprint
                try:
                    url = upload_notice_image(uploader.getvalue(), uploader.name)
                    st.session_state[notice_key] = (
                        st.session_state.get(notice_key, "")
                        + f"\n\n![{uploader.name}]({url})\n\n"
                    )
                    st.session_state[suc_key] = "이미지 업로드 완료 · 편집창에 추가됨"
                except Exception as e:
                    st.session_state[err_key] = f"업로드 실패: {e}"

            # === UI 렌더 ===
            # 본문 편집창 (자유 텍스트 · 이미지 마크다운은 자동 삽입됨)
            st.markdown("**공지 내용**")
            st.text_area(
                "공지 내용",
                key=notice_key,
                height=240,
                placeholder=("공지할 내용을 자유롭게 입력하세요.\n\n"
                            "아래 [이미지 추가]로 이미지를 삽입할 수 있습니다."),
                label_visibility="collapsed",
            )

            # 이전 콜백 결과 메시지
            err_msg = st.session_state.pop(err_key, None)
            if err_msg:
                st.error(err_msg)
            suc_msg = st.session_state.pop(suc_key, None)
            if suc_msg:
                st.success(suc_msg)

            # 이미지 추가 (on_change 콜백)
            with st.container(border=True):
                st.markdown("🖼 **이미지 추가**")
                st.file_uploader(
                    "이미지 파일 선택 (PNG · JPG · GIF · WEBP · 5MB 이하)",
                    type=["png", "jpg", "jpeg", "gif", "webp"],
                    key=up_key,
                    on_change=_handle_upload,
                    accept_multiple_files=False,
                    label_visibility="visible",
                )
                st.caption("파일 선택 시 자동 업로드 → 편집창에 추가됩니다.")

            # 실시간 미리보기
            preview_content = st.session_state.get(notice_key, "")
            if preview_content.strip():
                st.markdown("**미리보기**")
                with st.container(border=True):
                    st.markdown(preview_content, unsafe_allow_html=False)

            active_key = f"notice_active_{media_id}"
            active_val = st.checkbox(
                "공지 활성화 (해제 시 조회에서 숨김)",
                value=current_active, key=active_key,
            )

            # 저장/삭제 콜백 (on_click로 실행되어 위젯 상태 수정 안전)
            def _handle_notice_save():
                content_to_save = st.session_state.get(notice_key, "").strip()
                if not content_to_save:
                    st.session_state[err_key] = "공지 내용을 입력하세요."
                    return
                active = st.session_state.get(active_key, True)
                try:
                    upsert_notice(media_id, content_to_save, active=active)
                    st.session_state[suc_key] = "공지 저장 완료"
                except Exception as e:
                    st.session_state[err_key] = f"저장 실패: {e}"

            def _handle_notice_delete():
                try:
                    delete_notice(media_id)
                    st.session_state.pop(notice_key, None)
                    st.session_state[suc_key] = "공지 삭제 완료"
                except Exception as e:
                    st.session_state[err_key] = f"삭제 실패: {e}"

            c1, c2, _ = st.columns([1.4, 1.6, 2])
            with c1:
                st.button("저장", type="primary", key=f"notice_save_{media_id}",
                          on_click=_handle_notice_save, use_container_width=True)
            with c2:
                if notice_any:
                    st.button("공지 삭제", key=f"notice_del_{media_id}",
                              on_click=_handle_notice_delete, use_container_width=True)


def _tsv_to_markdown_table(text: str) -> str:
    """엑셀/시트 클립보드 TSV → 마크다운 표 변환. 첫 행 헤더."""
    lines = [l for l in text.strip().split("\n") if l.strip()]
    if not lines:
        return ""
    rows = [line.split("\t") for line in lines]
    n_cols = max(len(r) for r in rows) if rows else 0
    if n_cols == 0:
        return ""
    header = rows[0] + [""] * (n_cols - len(rows[0]))
    md_lines = ["| " + " | ".join(header) + " |"]
    md_lines.append("|" + "|".join(["---"] * n_cols) + "|")
    for row in rows[1:]:
        row_padded = row + [""] * (n_cols - len(row))
        md_lines.append("| " + " | ".join(row_padded) + " |")
    return "\n".join(md_lines)




def _render_hub_sections(media_id: str, sections: list[dict], edit_mode: bool) -> None:
    if not sections:
        if edit_mode:
            st.info("아직 등록된 자료가 없습니다. 하단 '+ 새 자료 추가' 폼을 이용해주세요.")
        return

    total_items = sum(len(s["items"]) for s in sections)
    # 상위 컨테이너 헤더 (섹션 이름과 위계 구분: 큰 폰트 + 상단 구분선)
    st.markdown(
        f"<div style='margin-top:28px; padding-top:14px; border-top:1px solid #C8C5BE;'>"
        f"<div style='font-size:17px; font-weight:700; color:#0B0B0B; letter-spacing:-0.01em;'>"
        f"📚 미디어 허브"
        f"<span style='font-size:11px; color:#7B7770; font-weight:400; margin-left:10px;'>"
        f"섹션 {len(sections)}개 · 자료 {total_items}개</span>"
        f"</div></div>",
        unsafe_allow_html=True,
    )

    for si, section in enumerate(sections):
        _render_hub_section(media_id, section, si, len(sections), edit_mode)


def _render_hub_section(media_id: str, section: dict, section_idx: int,
                        total_sections: int, edit_mode: bool) -> None:
    # 섹션 헤더 (편집 모드에서만 "섹션 삭제" 텍스트 링크 표시)
    if edit_mode:
        header_html = (
            f"<div style='display:flex; justify-content:space-between; align-items:baseline;"
            f"margin-top:24px; padding-bottom:8px; border-bottom:1px solid #E5EAF5;'>"
            f"<div style='font-size:15px; font-weight:600; color:#0B0B0B;'>"
            f"{section['name']}</div>"
            f"<a href='#' id='sec_del|{section['name']}' "
            f"style='color:#B84A3A; font-size:12px; text-decoration:underline;"
            f"text-underline-offset:3px; text-decoration-color:#B84A3A;'>섹션 삭제</a>"
            f"</div>"
        )
        clicked = click_detector(header_html, key=f"sec_head_{media_id}_{section['name']}")
        if clicked == f"sec_del|{section['name']}":
            last = st.session_state.get(f"_last_click_sec_{section['name']}")
            if clicked != last:
                st.session_state[f"_last_click_sec_{section['name']}"] = clicked
                st.session_state[f"_sec_del_confirm_{section['name']}"] = True
                _keep_detail_dialog(media_id)
                st.rerun()
    else:
        st.markdown(
            f"<div style='margin-top:24px; padding-bottom:8px; border-bottom:1px solid #E5EAF5;'>"
            f"<div style='font-size:15px; font-weight:600; color:#0B0B0B;'>"
            f"{section['name']}</div></div>",
            unsafe_allow_html=True,
        )

    # 섹션 삭제 확인
    if edit_mode and st.session_state.get(f"_sec_del_confirm_{section['name']}"):
        st.warning(f"'{section['name']}' 섹션과 하위 {len(section['items'])}개 자료를 모두 삭제합니다. (자동 편입 항목 제외)")
        d1, d2, _ = st.columns([1, 1, 4])
        with d1:
            if st.button("삭제 확정", type="primary", key=f"sec_del_ok_{section['name']}"):
                delete_section(media_id, section["name"])
                st.session_state.pop(f"_sec_del_confirm_{section['name']}", None)
                st.session_state.pop(f"_last_click_sec_{section['name']}", None)
                _keep_detail_dialog(media_id)
                st.rerun()
        with d2:
            if st.button("취소", key=f"sec_del_cancel_{section['name']}"):
                st.session_state.pop(f"_sec_del_confirm_{section['name']}", None)
                st.session_state.pop(f"_last_click_sec_{section['name']}", None)
                _keep_detail_dialog(media_id)
                st.rerun()

    # 자료 목록
    items = section["items"]
    for ii, item in enumerate(items):
        _render_hub_item(media_id, section["name"], item, ii, len(items), items, edit_mode)

    # 섹션 하단: [+ 자료 추가] 인라인 폼 (편집 모드)
    if edit_mode:
        _render_add_item_form(media_id, section["name"])


def _hub_item_link_html(item: dict) -> str:
    """자료 제목을 하이퍼링크 스타일로 렌더. 링크 아이콘(↗) 표시."""
    return (
        f"<a href='{item['url']}' target='_blank' rel='noopener' "
        f"style='color:#0B0B0B; text-decoration:none; font-size:14px; font-weight:500;"
        f"display:inline-flex; align-items:center; gap:6px; line-height:1.4;'>"
        f"<span style='border-bottom:1px solid #C8C5BE; padding-bottom:1px;'>{item['title']}</span>"
        f"<span style='color:#F2A93B; font-size:12px;'>↗</span>"
        f"</a>"
    )


def _render_hub_item(media_id: str, section_name: str, item: dict,
                     item_idx: int, total_items: int, all_items: list,
                     edit_mode: bool) -> None:
    is_auto = item.get("auto", False)  # 소개서 자동 편입

    if not edit_mode or is_auto:
        # 조회 모드 (또는 자동 편입 아이템)
        desc_html = f"<div style='font-size:12px;color:#7B7770;margin-top:3px;'>{item['desc']}</div>" if item.get("desc") else ""
        auto_badge = "<span style='font-size:10px;color:#7B7770;margin-left:8px;'>·자동 편입</span>" if is_auto else ""
        st.markdown(
            f"<div style='padding:10px 0;border-bottom:1px dashed #E5EAF5;'>"
            f"{_hub_item_link_html(item)}{auto_badge}{desc_html}"
            f"</div>",
            unsafe_allow_html=True,
        )
        return

    # 편집 모드 — 제목·설명 좌, 편집·삭제 우 (↑↓ 없음)
    e1, e2, e3 = st.columns([6, 1, 1])
    with e1:
        desc_html = f"<div style='font-size:11px;color:#7B7770;margin-top:2px;'>{item['desc']}</div>" if item.get("desc") else ""
        st.markdown(
            f"<div style='padding:6px 0 4px;'>{_hub_item_link_html(item)}{desc_html}</div>",
            unsafe_allow_html=True,
        )
    with e2:
        if st.button("편집", key=f"item_edit_{item['row']}", use_container_width=True):
            st.session_state[f"_item_edit_{item['row']}"] = True
            _keep_detail_dialog(media_id)
            st.rerun()
    with e3:
        if st.button("삭제", key=f"item_del_{item['row']}", use_container_width=True):
            st.session_state[f"_item_del_confirm_{item['row']}"] = True
            _keep_detail_dialog(media_id)
            st.rerun()

    # 자료 편집 폼
    if st.session_state.get(f"_item_edit_{item['row']}"):
        with st.container(border=True):
            new_title = st.text_input("제목", value=item["title"], key=f"edit_title_{item['row']}")
            new_url = st.text_input("URL", value=item["url"], key=f"edit_url_{item['row']}")
            new_desc = st.text_input("설명 (선택)", value=item["desc"], key=f"edit_desc_{item['row']}")
            f1, f2, _ = st.columns([1, 1, 4])
            with f1:
                if st.button("저장", type="primary", key=f"edit_save_{item['row']}"):
                    if new_title.strip() and new_url.strip():
                        update_hub_item(
                            item["row"], media_id, section_name, "",
                            new_title.strip(), new_url.strip(), new_desc.strip(), item["order"],
                        )
                        st.session_state.pop(f"_item_edit_{item['row']}", None)
                        _keep_detail_dialog(media_id)
                        st.rerun()
                    else:
                        st.error("제목과 URL은 필수입니다.")
            with f2:
                if st.button("취소", key=f"edit_cancel_{item['row']}"):
                    st.session_state.pop(f"_item_edit_{item['row']}", None)
                    _keep_detail_dialog(media_id)
                    st.rerun()

    # 자료 삭제 확인
    if st.session_state.get(f"_item_del_confirm_{item['row']}"):
        st.warning(f"'{item['title']}' 자료를 삭제합니다.")
        d1, d2, _ = st.columns([1, 1, 4])
        with d1:
            if st.button("삭제 확정", type="primary", key=f"del_ok_{item['row']}"):
                delete_hub_item(item["row"])
                st.session_state.pop(f"_item_del_confirm_{item['row']}", None)
                _keep_detail_dialog(media_id)
                st.rerun()
        with d2:
            if st.button("취소", key=f"del_cancel_{item['row']}"):
                st.session_state.pop(f"_item_del_confirm_{item['row']}", None)
                _keep_detail_dialog(media_id)
                st.rerun()


def _render_add_item_form(media_id: str, section_name: str) -> None:
    """섹션 하단 인라인 '+ 자료 추가' 확장 폼 (섹션별)."""
    exp_key = f"_add_item_expander_{media_id}_{section_name}"
    with st.expander("＋ 자료 추가", expanded=st.session_state.get(exp_key, False)):
        title = st.text_input("제목", key=f"add_item_title_{media_id}_{section_name}")
        url = st.text_input("URL", key=f"add_item_url_{media_id}_{section_name}",
                           placeholder="https://...")
        desc = st.text_input("설명 (선택)", key=f"add_item_desc_{media_id}_{section_name}")
        if st.button("추가", type="primary",
                    key=f"add_item_submit_{media_id}_{section_name}",
                    use_container_width=True):
            if not title.strip() or not url.strip():
                st.error("제목·URL은 필수입니다.")
            else:
                add_hub_item(
                    media_id, section_name, "",
                    title.strip(), url.strip(), desc.strip(), "",
                )
                # 입력값 초기화
                for k in [f"add_item_title_{media_id}_{section_name}",
                          f"add_item_url_{media_id}_{section_name}",
                          f"add_item_desc_{media_id}_{section_name}"]:
                    st.session_state.pop(k, None)
                st.success(f"'{title.strip()}' 추가 완료")
                _keep_detail_dialog(media_id)
                st.rerun()


def _render_hub_add_forms(media_id: str, sections: list[dict]) -> None:
    """페이지 하단: '+ 새 섹션 추가' 폼."""
    st.markdown("<div style='height:32px;'></div>", unsafe_allow_html=True)

    exp_key = f"_add_section_expander_{media_id}"
    with st.expander("＋ 새 섹션 추가", expanded=st.session_state.get(exp_key, False)):
        st.caption("첫 자료를 등록하면 해당 이름으로 섹션이 생성됩니다.")
        new_sec = st.text_input("섹션명", key=f"new_sec_name_{media_id}",
                                placeholder="예: 벤치마크 데이터")
        sec_order_val = st.number_input(
            "섹션 순서 (숫자 작을수록 위쪽 배치)",
            min_value=0, value=len(sections) * 10, step=1,
            key=f"new_sec_order_{media_id}",
        )
        title = st.text_input("첫 자료 제목", key=f"new_sec_title_{media_id}")
        url = st.text_input("첫 자료 URL", key=f"new_sec_url_{media_id}",
                           placeholder="https://...")
        desc = st.text_input("첫 자료 설명 (선택)", key=f"new_sec_desc_{media_id}")
        if st.button("섹션 만들기", type="primary",
                    key=f"new_sec_submit_{media_id}", use_container_width=True):
            if not new_sec.strip() or not title.strip() or not url.strip():
                st.error("섹션명·제목·URL은 필수입니다.")
            else:
                add_hub_item(
                    media_id, new_sec.strip(), int(sec_order_val),
                    title.strip(), url.strip(), desc.strip(), "",
                )
                for k in [f"new_sec_name_{media_id}", f"new_sec_title_{media_id}",
                          f"new_sec_url_{media_id}", f"new_sec_desc_{media_id}"]:
                    st.session_state.pop(k, None)
                st.success(f"'{new_sec.strip()}' 섹션 생성 완료")
                _keep_detail_dialog(media_id)
                st.rerun()
