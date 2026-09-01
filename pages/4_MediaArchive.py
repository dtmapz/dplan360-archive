import streamlit as st
from datetime import date
from utils.auth import is_admin
from utils.ui import set_current_page
from utils.sheets import (
    get_media_archives,
    create_media_archive,
    update_media_archive,
    delete_media_archive,
)

set_current_page("media_archive")

MONTHS = [f"{m}월" for m in range(1, 13)]


# ----------------------------------------------------------------------
# 팝업 세션 관리
# ----------------------------------------------------------------------

POPUP_KEYS = (
    "_ma_popup_open", "_ma_popup_mode", "_ma_popup_id",
    "_ma_f_year", "_ma_f_month", "_ma_f_title", "_ma_f_summary",
    "_ma_f_agenda", "_ma_f_drive_link",
    "_ma_f_published", "_ma_del_confirm",
)


def _reset_popup_state():
    for key in POPUP_KEYS:
        st.session_state.pop(key, None)


def _open_view_popup(archive_id: str):
    _reset_popup_state()
    st.session_state["_ma_popup_open"] = True
    st.session_state["_ma_popup_mode"] = "view"
    st.session_state["_ma_popup_id"] = archive_id


def _fill_edit_fields(a: dict):
    st.session_state["_ma_f_year"] = a["year"]
    st.session_state["_ma_f_month"] = a["month"]
    st.session_state["_ma_f_title"] = a["title"]
    st.session_state["_ma_f_summary"] = a["summary"]
    st.session_state["_ma_f_agenda"] = "\n".join(a.get("agenda") or [])
    st.session_state["_ma_f_drive_link"] = a["drive_link"]
    st.session_state["_ma_f_published"] = a["published_date"]


def _open_edit_popup(a: dict | None = None):
    _reset_popup_state()
    st.session_state["_ma_popup_open"] = True
    st.session_state["_ma_popup_mode"] = "edit"
    if a:
        st.session_state["_ma_popup_id"] = a["id"]
        _fill_edit_fields(a)
    else:
        this_year = date.today().year
        st.session_state["_ma_f_year"] = str(this_year)
        st.session_state["_ma_f_month"] = f"{date.today().month}월"


def _switch_to_edit_mode(a: dict):
    st.session_state["_ma_popup_mode"] = "edit"
    _fill_edit_fields(a)


def _keep_popup():
    st.session_state["_ma_popup_open"] = True


# ----------------------------------------------------------------------
# 카드 렌더
# ----------------------------------------------------------------------

def _render_card(a: dict):
    year_short = a["year"][-2:] if a["year"] else "--"
    card_html = (
        "<div style='border:0.5px solid #ddd;border-radius:8px;overflow:hidden;"
        "background:#fff;'>"
        "<div style='aspect-ratio:16/9;background:linear-gradient(135deg,#16171A 0%,#232323 60%,#2C2C2C 100%);"
        "position:relative;display:flex;flex-direction:column;justify-content:flex-end;padding:14px;color:#fff;'>"
        "<span style='position:absolute;top:12px;right:12px;background:#F2A93B;color:#1C1200;"
        "font-size:10px;font-weight:700;padding:3px 8px;border-radius:4px;'>PDF</span>"
        f"<div style='font-size:26px;font-weight:800;line-height:1;'>{a['month']}</div>"
        f"<div style='font-size:11px;color:#C8C8C8;margin-top:2px;'>{a['year']}</div>"
        "</div>"
        "<div style='padding:12px 14px 14px;'>"
        f"<div style='font-size:14px;font-weight:700;color:#111;margin-bottom:4px;'>{a['title']}</div>"
        f"<div style='font-size:12px;color:#666;min-height:32px;line-height:1.4;'>{a['summary']}</div>"
        "</div></div>"
    )
    st.markdown(card_html, unsafe_allow_html=True)
    if st.button("자세히 보기", key=f"ma_btn_{a['id']}", use_container_width=True):
        _open_view_popup(a["id"])
        st.rerun()


def _render_grid(items: list[dict]):
    if not items:
        st.markdown(
            "<div style='color:#999;text-align:center;padding:40px 0;font-size:13px;'>"
            "등록된 자료가 없습니다.</div>",
            unsafe_allow_html=True,
        )
        return
    cols_per_row = 4
    for i in range(0, len(items), cols_per_row):
        row_items = items[i:i + cols_per_row]
        cols = st.columns(cols_per_row)
        for col, a in zip(cols, row_items):
            with col:
                _render_card(a)


# ----------------------------------------------------------------------
# 팝업 (view + edit)
# ----------------------------------------------------------------------

@st.dialog("월간 미디어 자료")
def render_archive_popup():
    st.session_state.pop("_ma_popup_open", None)
    mode = st.session_state.get("_ma_popup_mode", "view")
    archive_id = st.session_state.get("_ma_popup_id")

    existing = None
    if archive_id:
        existing = next((a for a in get_media_archives() if a["id"] == archive_id), None)

    if mode == "view":
        _render_view_mode(existing)
    else:
        _render_edit_mode(existing)


def _render_view_mode(a: dict | None):
    if not a:
        st.warning("자료를 찾을 수 없습니다.")
        return

    st.markdown(
        "<div style='background:#0B0B0B;color:#fff;border-radius:8px;padding:18px 20px;margin-bottom:16px;'>"
        f"<div style='font-size:11px;color:#F2A93B;font-weight:700;margin-bottom:4px;'>{a['year']}년 {a['month']} · SP팀 발간</div>"
        f"<div style='font-size:18px;font-weight:800;'>{a['title']}</div>"
        f"<div style='font-size:12px;color:#C8C8C8;margin-top:4px;'>발행일 {a['published_date'] or '-'}</div>"
        "</div>",
        unsafe_allow_html=True,
    )

    agenda = a.get("agenda") or []
    if agenda:
        st.markdown(
            "<div style='font-size:11px;font-weight:700;color:#999;letter-spacing:.04em;"
            "text-transform:uppercase;margin-bottom:8px;'>주요 아젠다</div>",
            unsafe_allow_html=True,
        )
        items_html = "".join(
            f"<div style='display:flex;gap:10px;font-size:13px;color:#111;padding:6px 0;'>"
            f"<span style='flex:0 0 auto;font-size:11px;font-weight:700;color:#F2A93B;"
            f"background:rgba(242,169,59,0.18);width:20px;height:20px;border-radius:5px;"
            f"display:flex;align-items:center;justify-content:center;'>{i+1}</span>{txt}</div>"
            for i, txt in enumerate(agenda)
        )
        st.markdown(
            f"<div style='background:#FFF8E1;border-left:3px solid #F2A93B;border-radius:6px;"
            f"padding:10px 16px;margin-bottom:20px;'>{items_html}</div>",
            unsafe_allow_html=True,
        )

    st.markdown(
        "<div style='font-size:11px;font-weight:700;color:#999;letter-spacing:.04em;"
        "text-transform:uppercase;margin-bottom:8px;'>원본 파일</div>",
        unsafe_allow_html=True,
    )
    if a["drive_link"]:
        st.markdown(
            "<div style='display:flex;align-items:center;gap:12px;border:0.5px solid #ddd;"
            "border-radius:8px;padding:12px 14px;background:#f5f5f5;'>"
            "<div style='flex:0 0 auto;width:38px;height:38px;border-radius:8px;background:#E3453A;"
            "color:#fff;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:800;'>PDF</div>"
            "<div style='flex:1;min-width:0;'>"
            f"<div style='font-size:13px;font-weight:600;color:#111;'>{a['title']}</div>"
            "<div style='font-size:11px;color:#999;margin-top:2px;'>구글 드라이브에서 원본을 확인합니다</div>"
            "</div></div>",
            unsafe_allow_html=True,
        )
        st.link_button("📄 드라이브에서 열기", a["drive_link"],
                        type="primary", use_container_width=True)
    else:
        st.caption("등록된 파일 링크가 없습니다.")

    if is_admin():
        st.divider()
        if st.button("✎ 수정하기", key=f"ma_edit_entry_{a['id']}", use_container_width=True):
            _switch_to_edit_mode(a)
            _keep_popup()
            st.rerun()


def _render_edit_mode(existing: dict | None):
    is_edit = existing is not None
    st.markdown("#### 월간 자료 수정" if is_edit else "#### 월간 자료 등록")

    c1, c2 = st.columns(2)
    this_year = date.today().year
    year_options = [str(y) for y in range(this_year, this_year - 4, -1)]
    with c1:
        cur_year = st.session_state.get("_ma_f_year") or str(this_year)
        idx = year_options.index(cur_year) if cur_year in year_options else 0
        st.selectbox("연도 *", year_options, index=idx, key="_ma_f_year")
    with c2:
        cur_month = st.session_state.get("_ma_f_month") or MONTHS[0]
        idx = MONTHS.index(cur_month) if cur_month in MONTHS else 0
        st.selectbox("월 *", MONTHS, index=idx, key="_ma_f_month")

    st.text_input("제목 *", key="_ma_f_title", placeholder="예: 9월 미디어 트렌드 & 매체 업데이트")
    st.text_area("카드 요약 설명", key="_ma_f_summary", placeholder="카드에 노출되는 한 줄 설명")
    st.text_area(
        "주요 아젠다 (한 줄에 하나)", key="_ma_f_agenda", height=120,
        placeholder="숏폼 광고 상품 개편\n네이버GFA 신규 타겟팅 옵션 출시",
    )
    st.date_input("발행일", key="_ma_f_published_date",
                  value=date.fromisoformat(st.session_state["_ma_f_published"])
                  if st.session_state.get("_ma_f_published") else date.today())

    st.text_input(
        "구글 드라이브 링크 *", key="_ma_f_drive_link",
        placeholder="https://drive.google.com/file/d/... (링크 보기 권한 필요)",
        help="파일을 드라이브에 업로드한 뒤 '링크가 있는 모든 사용자' 보기 권한으로 공유 링크를 붙여넣으세요.",
    )

    st.divider()
    save_col, cancel_col, del_col = st.columns([2, 1, 1])

    if save_col.button("저장", key="ma_save_btn", type="primary", use_container_width=True):
        title_val = (st.session_state.get("_ma_f_title") or "").strip()
        drive_link_val = (st.session_state.get("_ma_f_drive_link") or "").strip()
        if not title_val:
            st.error("제목은 필수입니다.")
            return
        if not drive_link_val:
            st.error("구글 드라이브 링크는 필수입니다.")
            return
        _save_archive(is_edit, existing)
        return

    if cancel_col.button("취소", key="ma_cancel_btn", use_container_width=True):
        _reset_popup_state()
        st.rerun()

    if is_edit:
        if not st.session_state.get("_ma_del_confirm"):
            if del_col.button("삭제", key="ma_del_btn", use_container_width=True):
                st.session_state["_ma_del_confirm"] = True
                _keep_popup()
                st.rerun()
        else:
            st.error("정말 삭제하시겠습니까?")
            dc1, dc2 = st.columns(2)
            if dc1.button("삭제 확정", key="ma_del_confirm_btn", type="primary", use_container_width=True):
                delete_media_archive(existing["row"])
                _reset_popup_state()
                st.rerun()
            if dc2.button("취소", key="ma_del_cancel_btn", use_container_width=True):
                st.session_state.pop("_ma_del_confirm", None)
                _keep_popup()
                st.rerun()


def _save_archive(is_edit: bool, existing: dict | None):
    year = st.session_state.get("_ma_f_year")
    month = st.session_state.get("_ma_f_month")
    title = (st.session_state.get("_ma_f_title") or "").strip()
    summary = (st.session_state.get("_ma_f_summary") or "").strip()
    agenda = [
        line.strip() for line in (st.session_state.get("_ma_f_agenda") or "").split("\n")
        if line.strip()
    ]
    published = st.session_state.get("_ma_f_published_date")
    published_str = published.isoformat() if isinstance(published, date) else ""
    drive_link = (st.session_state.get("_ma_f_drive_link") or "").strip()

    payload = {
        "year": year, "month": month, "title": title, "summary": summary,
        "agenda": agenda, "drive_link": drive_link, "published_date": published_str,
    }

    if is_edit:
        payload["id"] = existing["id"]
        payload["created_at"] = existing["created_at"]
        update_media_archive(existing["row"], payload)
    else:
        create_media_archive(payload)

    _reset_popup_state()
    st.rerun()


# ----------------------------------------------------------------------
# 페이지 본문
# ----------------------------------------------------------------------

admin = is_admin()

head_col, btn_col = st.columns([5, 1])
with head_col:
    st.markdown("<div style='font-size:20px;font-weight:700;color:#111;'>월간 미디어 자료</div>", unsafe_allow_html=True)
    st.markdown(
        "<div style='font-size:12px;color:#666;margin-bottom:16px;'>"
        "SP팀에서 매월 발간하는 미디어 자료를 모아봅니다. 카드를 눌러 주요 아젠다와 원본 PDF를 확인하세요.</div>",
        unsafe_allow_html=True,
    )
if admin:
    if btn_col.button("＋ 자료 등록", key="ma_add_btn", use_container_width=True):
        _open_edit_popup(None)
        st.rerun()

all_archives = get_media_archives()

years = sorted({a["year"] for a in all_archives if a["year"]}, reverse=True)
with st.container(border=True):
    c1, c2 = st.columns([1, 1])
    year_filter = c1.selectbox("연도", ["전체"] + years, key="ma_year_filter")
    month_filter = c2.selectbox("월", ["전체"] + MONTHS, key="ma_month_filter")

filtered = all_archives
if year_filter != "전체":
    filtered = [a for a in filtered if a["year"] == year_filter]
if month_filter != "전체":
    filtered = [a for a in filtered if a["month"] == month_filter]

_render_grid(filtered)

if st.session_state.get("_ma_popup_open"):
    render_archive_popup()
