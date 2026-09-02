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
# 아젠다 파싱 — "매체명, 아젠다텍스트" 형식
# ----------------------------------------------------------------------

def _parse_agenda_line(line: str) -> tuple[str | None, str]:
    """한 라인을 (매체명, 아젠다텍스트)로 파싱.
    콤마 없거나 매체명이 비면 (None, 원문) 반환 → 필터에서 제외되지만 팝업엔 그대로 노출.

    또한 "신규 미디어&상품 소개..." 처럼 특정 매체가 아닌 일반 소개 라인은
    필터에서 완전 제외 (팝업에만 노출)."""
    line_stripped = line.strip()
    # 매체 매칭 대상이 아닌 예외 프리픽스
    EXCLUDE_PREFIXES = ("신규 미디어", "신규미디어")
    if any(line_stripped.startswith(p) for p in EXCLUDE_PREFIXES):
        return (None, line_stripped)
    if "," not in line:
        return (None, line_stripped)
    head, _, tail = line.partition(",")
    media = head.strip()
    agenda = tail.strip()
    if not media or not agenda:
        return (None, line_stripped)
    return (media, agenda)


def _extract_media_agenda_map(items: list[dict]) -> dict[str, list[str]]:
    """전체 자료에서 {매체명: [아젠다1, 아젠다2, ...]} 맵 생성 (중복 제거·정렬)."""
    m: dict[str, set[str]] = {}
    for a in items:
        for line in a.get("agenda") or []:
            media, agenda_text = _parse_agenda_line(line)
            if not media:
                continue
            m.setdefault(media, set()).add(agenda_text)
    return {k: sorted(v) for k, v in sorted(m.items())}


def _get_matched_lines(a: dict, sel_media: list[str], sel_agenda: list[str]) -> list[str]:
    """이 카드에서 필터 조건에 매칭되는 아젠다 라인들 반환."""
    if not sel_media and not sel_agenda:
        return []
    matched = []
    for line in a.get("agenda") or []:
        media, agenda_text = _parse_agenda_line(line)
        if not media:
            continue
        if sel_media and media not in sel_media:
            continue
        if sel_agenda and agenda_text not in sel_agenda:
            continue
        matched.append(line)
    return matched


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

def _render_card(a: dict, matched_lines: list[str] | None = None, dimmed: bool = False):
    matched_lines = matched_lines or []
    is_match = bool(matched_lines)

    border_style = "1.5px solid #F2A93B" if is_match else "0.5px solid #ddd"
    shadow = "box-shadow:0 0 0 3px rgba(242,169,59,0.12);" if is_match else ""
    wrapper_style = "opacity:0.35;" if dimmed else ""

    match_band = ""
    if matched_lines:
        # 라인마다 매체명은 볼드 처리
        rows = []
        for line in matched_lines:
            media, agenda_text = _parse_agenda_line(line)
            if media:
                rows.append(
                    f"<div style='margin-bottom:2px;'><strong style='color:#3C2703;font-weight:700;'>{media}</strong>"
                    f"<span style='color:#5D3E0A;'>, {agenda_text}</span></div>"
                )
            else:
                rows.append(f"<div style='margin-bottom:2px;color:#5D3E0A;'>{line}</div>")
        match_band = (
            "<div style='background:#FFF8E1;border-top:1px solid #E8B24E;"
            "padding:8px 14px;font-size:11px;line-height:1.45;'>"
            f"<div style='font-family:monospace;font-size:9.5px;font-weight:600;"
            f"letter-spacing:1px;color:#8C6614;margin-bottom:3px;'>MATCHED · {len(matched_lines)}</div>"
            f"{''.join(rows)}"
            "</div>"
        )

    card_html = (
        f"<div style='{wrapper_style}'>"
        f"<div style='border:{border_style};border-radius:8px;overflow:hidden;"
        f"background:#fff;{shadow}'>"
        "<div style='height:96px;background:linear-gradient(135deg,#16171A 0%,#232323 60%,#2C2C2C 100%);"
        "position:relative;display:flex;flex-direction:column;justify-content:flex-end;padding:12px 14px;color:#fff;'>"
        "<span style='position:absolute;top:10px;right:10px;background:#F2A93B;color:#1C1200;"
        "font-size:10px;font-weight:700;padding:2px 7px;border-radius:4px;'>PDF</span>"
        f"<div style='font-size:22px;font-weight:800;line-height:1;'>{a['month']}</div>"
        f"<div style='font-size:11px;color:#C8C8C8;margin-top:2px;'>{a['year']}</div>"
        "</div>"
        "<div style='padding:12px 14px 14px;'>"
        f"<div style='font-size:14px;font-weight:700;color:#111;margin-bottom:4px;'>{a['title']}</div>"
        f"<div style='font-size:12px;color:#666;min-height:32px;line-height:1.4;'>{a['summary']}</div>"
        "</div>"
        f"{match_band}"
        "</div></div>"
    )
    st.markdown(card_html, unsafe_allow_html=True)
    if st.button("자세히 보기", key=f"ma_btn_{a['id']}", use_container_width=True):
        _open_view_popup(a["id"])
        st.rerun()


def _render_grid(items: list[dict], sel_media: list[str], sel_agenda: list[str]):
    if not items:
        st.markdown(
            "<div style='color:#999;text-align:center;padding:40px 0;font-size:13px;'>"
            "등록된 자료가 없습니다.</div>",
            unsafe_allow_html=True,
        )
        return
    has_filter = bool(sel_media or sel_agenda)
    cols_per_row = 4
    for i in range(0, len(items), cols_per_row):
        row_items = items[i:i + cols_per_row]
        cols = st.columns(cols_per_row)
        for col, a in zip(cols, row_items):
            with col:
                matched = _get_matched_lines(a, sel_media, sel_agenda) if has_filter else []
                dimmed = has_filter and not matched
                _render_card(a, matched_lines=matched, dimmed=dimmed)


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
        # 현재 필터에서 매칭된 라인은 팝업에서도 강조
        sel_media = st.session_state.get("ma_media_filter") or []
        sel_agenda = st.session_state.get("ma_agenda_filter") or []
        matched_set = set(_get_matched_lines(a, sel_media, sel_agenda)) if (sel_media or sel_agenda) else set()

        rows = []
        for i, txt in enumerate(agenda):
            is_hit = txt in matched_set
            row_bg = "background:#FFE8A3;" if is_hit else ""
            hit_mark = "<span style='margin-left:auto;font-size:10px;font-weight:700;color:#8C6614;'>MATCHED</span>" if is_hit else ""
            rows.append(
                f"<div style='display:flex;gap:10px;align-items:center;font-size:13px;color:#111;"
                f"padding:6px 8px;border-radius:4px;margin-bottom:2px;{row_bg}'>"
                f"<span style='flex:0 0 auto;font-size:11px;font-weight:700;color:#F2A93B;"
                f"background:rgba(242,169,59,0.18);width:20px;height:20px;border-radius:5px;"
                f"display:flex;align-items:center;justify-content:center;'>{i+1}</span>"
                f"<span style='flex:1;'>{txt}</span>{hit_mark}</div>"
            )
        st.markdown(
            f"<div style='background:#FFF8E1;border-left:3px solid #F2A93B;border-radius:6px;"
            f"padding:10px 12px;margin-bottom:20px;'>{''.join(rows)}</div>",
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
media_agenda_map = _extract_media_agenda_map(all_archives)
media_options = list(media_agenda_map.keys())

with st.container(border=True):
    fc1, fc2, fc3 = st.columns([1.2, 2, 0.6])
    sel_media = fc1.multiselect(
        "매체", media_options, key="ma_media_filter",
        placeholder="전체 (선택 시 필터링)",
        help="데이터에서 자동 추출된 매체 목록",
    )
    # 아젠다 옵션: 선택된 매체의 아젠다만 (매체 없으면 전체 매체 아젠다 통합)
    if sel_media:
        agenda_options = sorted({ag for m in sel_media for ag in media_agenda_map.get(m, [])})
    else:
        agenda_options = sorted({ag for lst in media_agenda_map.values() for ag in lst})
    sel_agenda = fc2.multiselect(
        "아젠다", agenda_options, key="ma_agenda_filter",
        placeholder="전체 (선택 시 필터링)",
        help="매체를 먼저 선택하면 해당 매체의 아젠다만 표시됩니다",
    )
    fc3.markdown("<div style='height:26px;'></div>", unsafe_allow_html=True)
    if fc3.button("초기화", key="ma_reset_filter", use_container_width=True):
        st.session_state.pop("ma_media_filter", None)
        st.session_state.pop("ma_agenda_filter", None)
        st.rerun()

_render_grid(all_archives, sel_media, sel_agenda)

if st.session_state.get("_ma_popup_open"):
    render_archive_popup()
