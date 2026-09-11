import pandas as pd
import streamlit as st
from datetime import date
from utils.auth import is_admin
from utils.ui import set_current_page, media_color, click_cards
from utils.sheets import (
    get_media_archives,
    create_media_archive,
    update_media_archive,
    delete_media_archive,
    get_all_media,
    MEDIA_ARCHIVE_DEFAULT_PUBLISHER as DPLAN,
)

set_current_page("media_archive")

MONTHS = [f"{m}월" for m in range(1, 13)]
ALL_PUBLISHERS = "전체"


# ----------------------------------------------------------------------
# 아젠다 파싱 — 배포주체에 따라 형식이 다르다
#   · 디플랜360 발간 자료 : "매체명, 아젠다텍스트"  (한 문서가 여러 매체를 다룸)
#   · 매체 배포 자료      : "아젠다텍스트"만        (문서 전체가 그 매체 것이라 매체명이 중복)
# ----------------------------------------------------------------------

def _agenda_texts(a: dict) -> list[str]:
    """아젠다 항목(dict)에서 텍스트만 뽑아낸다."""
    return [it.get("text", "") for it in (a.get("agenda") or []) if it.get("text")]


def _parse_agenda_line(line: str, publisher: str = DPLAN) -> tuple[str | None, str]:
    """한 라인을 (매체명, 아젠다텍스트)로 파싱.

    배포주체가 매체면 콤마로 자르지 않고 **배포주체를 매체로 자동 귀속**한다.
    덕분에 아젠다 안에 콤마가 있어도(`PMax, 신규 지면`) 안전하다.
    실수로 "구글, ..." 처럼 배포주체명을 앞에 붙여 입력한 경우는 떼어내 준다.
    """
    line_stripped = (line or "").strip()
    if not line_stripped:
        return (None, "")

    if publisher and publisher != DPLAN:
        prefix = f"{publisher},"
        if line_stripped.startswith(prefix):
            line_stripped = line_stripped[len(prefix):].strip()
        return (publisher, line_stripped) if line_stripped else (None, "")

    # ── 이하 디플랜360 발간 자료: 기존 동작 그대로 ──
    EXCLUDE_PREFIXES = ("신규 미디어", "신규미디어")
    if any(line_stripped.startswith(pf) for pf in EXCLUDE_PREFIXES):
        return (None, line_stripped)
    if "," not in line_stripped:
        return (None, line_stripped)
    head, _, tail = line_stripped.partition(",")
    media, agenda = head.strip(), tail.strip()
    if not media or not agenda:
        return (None, line_stripped)
    return (media, agenda)


def _extract_publisher_map(items: list[dict]) -> dict[str, dict[str, list[str]]]:
    """{배포주체: {매체명: [아젠다...]}} 맵 생성 (중복 제거·정렬)."""
    out: dict[str, dict[str, set]] = {}
    for a in items:
        pub = a.get("publisher") or DPLAN
        bucket = out.setdefault(pub, {})
        for txt in _agenda_texts(a):
            media, agenda_text = _parse_agenda_line(txt, pub)
            if not media or not agenda_text:
                continue
            bucket.setdefault(media, set()).add(agenda_text)
    return {p: {m: sorted(v) for m, v in sorted(b.items())} for p, b in sorted(out.items())}


def _get_matched_lines(a: dict, sel_media: list[str], sel_agenda: list[str]) -> list[str]:
    """이 카드에서 필터 조건에 매칭되는 아젠다 라인(원문 텍스트)들 반환."""
    if not sel_media and not sel_agenda:
        return []
    pub = a.get("publisher") or DPLAN
    matched = []
    for txt in _agenda_texts(a):
        media, agenda_text = _parse_agenda_line(txt, pub)
        if not media:
            continue
        if sel_media and media not in sel_media:
            continue
        if sel_agenda and agenda_text not in sel_agenda:
            continue
        matched.append(txt)
    return matched


# ----------------------------------------------------------------------
# 팝업 세션 관리
# ----------------------------------------------------------------------

POPUP_KEYS = (
    "_ma_popup_open", "_ma_popup_mode", "_ma_popup_id",
    "_ma_f_year", "_ma_f_month", "_ma_f_title", "_ma_f_summary",
    "_ma_f_agenda_rows", "_ma_f_publisher", "_ma_f_memo", "_ma_f_drive_link",
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
    st.session_state["_ma_f_agenda_rows"] = [dict(it) for it in (a.get("agenda") or [])]
    st.session_state["_ma_f_publisher"] = a.get("publisher") or DPLAN
    st.session_state["_ma_f_memo"] = a.get("memo") or ""
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
        st.session_state["_ma_f_agenda_rows"] = []
        st.session_state["_ma_f_publisher"] = DPLAN


def _switch_to_edit_mode(a: dict):
    st.session_state["_ma_popup_mode"] = "edit"
    _fill_edit_fields(a)


def _keep_popup():
    st.session_state["_ma_popup_open"] = True


# ----------------------------------------------------------------------
# 카드 렌더
# ----------------------------------------------------------------------

def _card_html(a: dict, matched_lines: list[str] | None = None, dimmed: bool = False) -> str:
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
            media, agenda_text = _parse_agenda_line(line, a.get("publisher") or DPLAN)
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

    # 배포주체별 색 + 이름 칩 — 색은 빠른 스캔용, 칩은 확인용(색만으로 구분하지 않는다)
    _pub = a.get("publisher") or DPLAN
    _c1, _c2 = media_color(_pub)

    card_html = (
        f"<div style='{wrapper_style}'>"
        f"<div style='border:{border_style};border-radius:8px;overflow:hidden;"
        f"background:#fff;{shadow}'>"
        f"<div style='height:96px;background:linear-gradient(135deg,{_c1} 0%,{_c2} 100%);"
        "position:relative;display:flex;flex-direction:column;justify-content:flex-end;padding:12px 14px;color:#fff;'>"
        f"<span style='position:absolute;top:10px;left:10px;background:rgba(255,255,255,0.93);color:{_c1};"
        f"font-size:10px;font-weight:700;padding:2px 7px;border-radius:4px;'>{_pub}</span>"
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
    # 버튼 없이 카드 전체를 클릭 영역으로 — 필터 표시(앰버 테두리·MATCHED·흐림)는 카드 안에 그대로 있다
    return f"<a href='#' id='arch__{a['id']}'>{card_html}</a>"


_GRID_CSS = (
    "<style>"
    ".ma-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;align-items:start;}"
    ".ma-grid a{display:block;border-radius:8px;}"
    # 마우스를 올리면 앰버 테두리 — 필터에 걸린 카드의 인라인 그림자보다 우선
    ".ma-grid a:hover > div > div{box-shadow:0 0 0 1.5px #F2A93B !important;}"
    "</style>"
)


def _render_grid(items: list[dict], sel_media: list[str], sel_agenda: list[str]):
    if not items:
        st.markdown(
            "<div style='color:#999;text-align:center;padding:40px 0;font-size:13px;'>"
            "등록된 자료가 없습니다.</div>",
            unsafe_allow_html=True,
        )
        return
    has_filter = bool(sel_media or sel_agenda)
    cards = []
    for a in items:
        matched = _get_matched_lines(a, sel_media, sel_agenda) if has_filter else []
        dimmed = has_filter and not matched
        cards.append(_card_html(a, matched_lines=matched, dimmed=dimmed))

    # "자세히 보기" 버튼 대신 카드 자체를 클릭 (주간 뉴스룸과 같은 방식, utils/ui.click_cards)
    target = click_cards(_GRID_CSS + f"<div class='ma-grid'>{''.join(cards)}</div>",
                         key="ma_grid_det", nonce_key="_ma_click_nonce")
    if target and target.startswith("arch__"):
        _open_view_popup(target.split("__", 1)[1])
        st.rerun()


# ----------------------------------------------------------------------
# 팝업 (view + edit)
# ----------------------------------------------------------------------

# 팝업 상단 타이틀 텍스트는 노출하지 않는다(문서 헤더가 이미 제목 역할을 함).
# st.dialog 는 title 인자가 필수라 공백을 넘겨 텍스트만 비우고 닫기(X)는 유지한다.
@st.dialog(" ")
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
        f"<div style='font-size:11px;color:#F2A93B;font-weight:700;margin-bottom:4px;'>{a['year']}년 {a['month']} · {a.get('publisher') or DPLAN} 발간</div>"
        f"<div style='font-size:18px;font-weight:800;'>{a['title']}</div>"
        f"<div style='font-size:12px;color:#C8C8C8;margin-top:4px;'>발행일 {a['published_date'] or '-'}</div>"
        "</div>",
        unsafe_allow_html=True,
    )

    agenda_items = a.get("agenda") or []
    if agenda_items:
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
        for i, item in enumerate(agenda_items):
            txt = item.get("text", "")
            is_hit = txt in matched_set
            row_bg = "background:#FFE8A3;" if is_hit else ""
            hit_mark = "<span style='margin-left:auto;font-size:10px;font-weight:700;color:#8C6614;'>MATCHED</span>" if is_hit else ""
            # 주간 뉴스룸에 연동되는 아젠다는 배지로 구분
            nr_mark = ("<span style='flex:0 0 auto;font-size:9.5px;font-weight:700;color:#0F5E86;"
                       "background:rgba(15,94,134,0.12);padding:1px 6px;border-radius:4px;'>뉴스룸</span>"
                       if item.get("newsroom") else "")
            rows.append(
                f"<div style='display:flex;gap:10px;align-items:center;font-size:13px;color:#111;"
                f"padding:6px 8px;border-radius:4px;margin-bottom:2px;{row_bg}'>"
                f"<span style='flex:0 0 auto;font-size:11px;font-weight:700;color:#F2A93B;"
                f"background:rgba(242,169,59,0.18);width:20px;height:20px;border-radius:5px;"
                f"display:flex;align-items:center;justify-content:center;'>{i+1}</span>"
                f"<span style='flex:1;'>{txt}</span>{nr_mark}{hit_mark}</div>"
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

    # 메모 — 매체 팝업과 동일한 표시 규격. 관리자 전용이 아니라 전체 사용자에게 보인다.
    if a.get("memo"):
        st.write("")
        st.markdown(
            f"<div style='background:#F6F8FC; border:1px solid #E5EAF5; "
            f"border-radius:8px; padding:10px 12px; font-size:13px; "
            f"white-space:pre-wrap; line-height:1.5;'>{a['memo']}</div>",
            unsafe_allow_html=True,
        )

    if is_admin():
        st.divider()
        if st.button("✎ 수정하기", key=f"ma_edit_entry_{a['id']}", use_container_width=True):
            _switch_to_edit_mode(a)
            _keep_popup()
            st.rerun()


def _render_edit_mode(existing: dict | None):
    is_edit = existing is not None
    st.markdown("#### 자료 수정" if is_edit else "#### 자료 등록")

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

    # 배포주체 — 자유 입력을 막아 "구글 / Google" 표기 혼선을 방지한다
    pub_options = [DPLAN] + [m["name"] for m in get_all_media() if m.get("name")]
    cur_pub = st.session_state.get("_ma_f_publisher") or DPLAN
    if cur_pub not in pub_options:
        pub_options.append(cur_pub)
    st.selectbox(
        "배포주체 *", pub_options, index=pub_options.index(cur_pub), key="_ma_f_publisher",
        help="디플랜360 발간 자료인지, 매체가 배포한 자료인지 선택합니다.",
    )
    is_media_pub = (st.session_state.get("_ma_f_publisher") or DPLAN) != DPLAN

    st.text_input("제목 *", key="_ma_f_title", placeholder="예: 9월 미디어 트렌드 & 매체 업데이트")
    st.text_area("카드 요약 설명", key="_ma_f_summary", placeholder="카드에 노출되는 한 줄 설명")

    st.markdown(
        "<div style='font-size:14px;font-weight:600;margin-bottom:3px;'>주요 아젠다</div>"
        "<ul style='margin:0 0 8px;padding-left:17px;font-size:11px;color:#888;line-height:1.7;'>"
        "<li>디플랜360 발간 자료는 매체명, 아젠다 / 매체 발간 자료는 아젠다만 입력해주세요.</li>"
        "<li>‘뉴스룸 연동’을 체크한 아젠다만 주간 뉴스룸에 노출됩니다.</li>"
        "</ul>",
        unsafe_allow_html=True,
    )
    # 위젯 key(_ma_w_*)와 저장 key(_ma_f_*)를 분리 — 스텝 전환 시 값 소실 방지 (§17-16)
    _rows = st.session_state.get("_ma_f_agenda_rows") or []
    # 빈 리스트를 그대로 넘기면 Streamlit이 컬럼 구조를 추론하지 못해 편집이 불가능해진다.
    # (신규 등록 시 표가 비활성으로 보이던 원인) → 컬럼·dtype을 명시한 DataFrame으로 전달한다.
    _df = pd.DataFrame([dict(r) for r in _rows], columns=["text", "newsroom"])
    _df["text"] = _df["text"].fillna("").astype(str)
    _df["newsroom"] = _df["newsroom"].fillna(False).astype(bool)
    edited = st.data_editor(
        _df,
        key="_ma_w_agenda_editor",
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "text": st.column_config.TextColumn(
                "아젠다",
                width="large",
                help=("예: 데모그래픽 타게팅 개편" if is_media_pub else "예: 구글, 퍼포먼스 max 업데이트"),
            ),
            "newsroom": st.column_config.CheckboxColumn("뉴스룸 연동", width="small", default=False),
        },
    )
    try:
        _recs = edited.to_dict("records")   # DataFrame으로 반환되는 경우
    except AttributeError:
        _recs = list(edited)
    st.session_state["_ma_f_agenda_rows"] = [
        {"text": str(r.get("text") or "").strip(), "newsroom": bool(r.get("newsroom"))}
        for r in _recs if str(r.get("text") or "").strip()
    ]
    st.date_input("발행일", key="_ma_f_published_date",
                  value=date.fromisoformat(st.session_state["_ma_f_published"])
                  if st.session_state.get("_ma_f_published") else date.today())

    st.text_input(
        "구글 드라이브 링크 *", key="_ma_f_drive_link",
        placeholder="https://drive.google.com/file/d/... (링크 보기 권한 필요)",
        help="파일을 드라이브에 업로드한 뒤 '링크가 있는 모든 사용자' 보기 권한으로 공유 링크를 붙여넣으세요.",
    )

    # 메모 — 매체 등록 팝업(utils/ui.py)의 메모와 동일 규격. 일반 사용자에게도 노출된다.
    st.text_area(
        "메모", key="_ma_f_memo", height=80,
        placeholder="자료 활용 시 참고사항 · 문의처 · 특이사항 등 자유 입력",
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
    agenda = st.session_state.get("_ma_f_agenda_rows") or []
    published = st.session_state.get("_ma_f_published_date")
    published_str = published.isoformat() if isinstance(published, date) else ""
    drive_link = (st.session_state.get("_ma_f_drive_link") or "").strip()

    payload = {
        "year": year, "month": month, "title": title, "summary": summary,
        "agenda": agenda, "drive_link": drive_link, "published_date": published_str,
        "publisher": st.session_state.get("_ma_f_publisher") or DPLAN,
        "memo": (st.session_state.get("_ma_f_memo") or "").strip(),
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
    # 페이지 상단 타이틀·서브카피는 노출하지 않는다 (사이드바 메뉴명이 이미 제목 역할)
    st.markdown("<div style='height:4px;'></div>", unsafe_allow_html=True)
if admin:
    if btn_col.button("＋ 자료 등록", key="ma_add_btn", use_container_width=True):
        _open_edit_popup(None)
        st.rerun()

all_archives = get_media_archives()
publisher_map = _extract_publisher_map(all_archives)

# 배포주체 옵션 — 디플랜360을 항상 맨 앞에 두고 나머지 매체는 가나다순
pub_options = [ALL_PUBLISHERS] + sorted(
    publisher_map.keys(), key=lambda x: (x != DPLAN, x)
)

with st.container(border=True):
    fc0, fc1, fc2, fc3 = st.columns([1.1, 1.3, 1.9, 0.55])

    sel_pub = fc0.selectbox(
        "배포주체", pub_options, key="ma_pub_filter",
        help="디플랜360 발간 자료 / 매체가 배포한 자료를 구분합니다",
    )
    # 배포주체가 매체면 그 자체가 곧 매체이므로 매체 선택은 비활성화한다
    is_media_pub = sel_pub not in (ALL_PUBLISHERS, DPLAN)

    if sel_pub == ALL_PUBLISHERS:
        merged: dict[str, set] = {}
        for bucket in publisher_map.values():
            for m, ags in bucket.items():
                merged.setdefault(m, set()).update(ags)
        media_map = {m: sorted(v) for m, v in sorted(merged.items())}
    else:
        media_map = publisher_map.get(sel_pub, {})

    sel_media = fc1.multiselect(
        "매체", list(media_map.keys()), key="ma_media_filter",
        placeholder="배포주체로 자동 지정됨" if is_media_pub else "전체 (선택 시 필터링)",
        disabled=is_media_pub,
        help="매체가 배포한 자료는 배포주체가 곧 매체라 선택이 필요 없습니다"
             if is_media_pub else "데이터에서 자동 추출된 매체 목록",
    )
    if is_media_pub:
        sel_media = []  # 비활성 상태의 잔여 선택값이 필터에 영향을 주지 않도록

    # 아젠다 옵션: 선택된 매체의 아젠다만 (매체 미선택이면 현재 배포주체 전체)
    if sel_media:
        agenda_options = sorted({ag for m in sel_media for ag in media_map.get(m, [])})
    else:
        agenda_options = sorted({ag for lst in media_map.values() for ag in lst})

    sel_agenda = fc2.multiselect(
        "아젠다", agenda_options, key="ma_agenda_filter",
        placeholder="전체 (선택 시 필터링)",
        help="매체를 먼저 선택하면 해당 매체의 아젠다만 표시됩니다",
    )
    fc3.markdown("<div style='height:26px;'></div>", unsafe_allow_html=True)
    if fc3.button("초기화", key="ma_reset_filter", use_container_width=True):
        for k in ("ma_pub_filter", "ma_media_filter", "ma_agenda_filter"):
            st.session_state.pop(k, None)
        st.rerun()

visible_archives = (
    all_archives if sel_pub == ALL_PUBLISHERS
    else [a for a in all_archives if (a.get("publisher") or DPLAN) == sel_pub]
)

_render_grid(visible_archives, sel_media, sel_agenda)

if st.session_state.get("_ma_popup_open"):
    render_archive_popup()
