import streamlit as st
from datetime import date
from utils.auth import is_admin
from utils.ui import set_current_page
from utils.db import upload_notice_image
from utils.sheets import (
    get_home_promotions,
    create_home_promotion,
    update_home_promotion,
    delete_home_promotion,
    get_major_categories,
    get_sub_categories,
    build_media_cat_map,
)

set_current_page("mediapromo")


CHIP_PRESETS = {
    "amber": {"bg": "#F2A93B", "fg": "#12100C", "label": "앰버 (강조)"},
    "ink":   {"bg": "#111111", "fg": "#FFFFFF", "label": "블랙 (기본)"},
    "line":  {"bg": "transparent", "fg": "#666666", "label": "아웃라인 (보조)"},
}
DEFAULT_CHIP_PRESET = "line"


def _chip_html(name: str, preset_key: str) -> str:
    p = CHIP_PRESETS.get(preset_key, CHIP_PRESETS[DEFAULT_CHIP_PRESET])
    if preset_key == "line":
        return (
            f"<span style='box-shadow:0 0 0 0.5px #999 inset;color:{p['fg']};"
            f"font-size:11px;font-weight:600;padding:3px 9px;border-radius:6px;"
            f"margin-right:6px;'>{name}</span>"
        )
    return (
        f"<span style='background:{p['bg']};color:{p['fg']};font-size:11px;"
        f"font-weight:600;padding:3px 9px;border-radius:6px;margin-right:6px;'>"
        f"{name}</span>"
    )


# ----------------------------------------------------------------------
# 팝업 세션 관리 (단일 팝업 view/edit 모드)
# ----------------------------------------------------------------------

POPUP_KEYS = (
    "_promo_popup_open", "_promo_popup_mode", "_promo_popup_promo_id",
    "_promo_form_cats", "_promo_force_save", "_promo_del_confirm",
    "_promo_f_media", "_promo_f_name", "_promo_f_subtitle",
    "_promo_f_image", "_promo_f_preview",
    "_promo_f_start", "_promo_f_end", "_promo_f_memo",
    "_new_cat_name", "_new_cat_preset",
    "_promo_img_uploader", "_promo_preview_uploader",
)


def _reset_popup_state():
    for key in POPUP_KEYS:
        st.session_state.pop(key, None)


def _open_view_popup(promo_id: str):
    _reset_popup_state()
    st.session_state["_promo_popup_open"] = True
    st.session_state["_promo_popup_mode"] = "view"
    st.session_state["_promo_popup_promo_id"] = promo_id


def _open_edit_popup(promo=None):
    _reset_popup_state()
    st.session_state["_promo_popup_open"] = True
    st.session_state["_promo_popup_mode"] = "edit"
    if promo:
        st.session_state["_promo_popup_promo_id"] = promo["id"]
        st.session_state["_promo_f_media"] = promo["media_name"]
        st.session_state["_promo_f_name"] = promo["name"]
        st.session_state["_promo_f_subtitle"] = promo["subtitle"]
        st.session_state["_promo_f_image"] = promo["image_url"]
        st.session_state["_promo_f_preview"] = promo.get("preview_image_url", "")
        st.session_state["_promo_f_start"] = promo["start_date"]
        st.session_state["_promo_f_end"] = promo["end_date"]
        st.session_state["_promo_f_memo"] = promo["memo"]
        st.session_state["_promo_form_cats"] = list(promo["categories"])
    else:
        st.session_state["_promo_form_cats"] = []


def _switch_to_edit_mode(promo):
    """view → edit 모드 전환 (같은 팝업 안)"""
    st.session_state["_promo_popup_mode"] = "edit"
    st.session_state["_promo_f_media"] = promo["media_name"]
    st.session_state["_promo_f_name"] = promo["name"]
    st.session_state["_promo_f_subtitle"] = promo["subtitle"]
    st.session_state["_promo_f_image"] = promo["image_url"]
    st.session_state["_promo_f_preview"] = promo.get("preview_image_url", "")
    st.session_state["_promo_f_start"] = promo["start_date"]
    st.session_state["_promo_f_end"] = promo["end_date"]
    st.session_state["_promo_f_memo"] = promo["memo"]
    st.session_state["_promo_form_cats"] = list(promo["categories"])


# ----------------------------------------------------------------------
# 필터 UI
# ----------------------------------------------------------------------

SUB_COLS_PER_ROW = 5


def _render_sub_buttons(subs: list[str], major: str) -> list[str]:
    """중분류 5버튼 그리드. 세션 세트로 다중 선택 상태 관리."""
    st.markdown(
        "<div style='font-size:14px;margin-bottom:6px;'>중분류 <span style='color:#999;font-size:11px;'>(선택 시 필터링)</span></div>",
        unsafe_allow_html=True,
    )
    selected: set = st.session_state.setdefault("_pmo_sub_selected", set())
    for i in range(0, len(subs), SUB_COLS_PER_ROW):
        row = subs[i:i + SUB_COLS_PER_ROW]
        cols = st.columns(SUB_COLS_PER_ROW)
        for col, s in zip(cols, row):
            is_on = s in selected
            if col.button(
                s,
                key=f"_pmo_sub_btn_{major}_{s}",
                type=("primary" if is_on else "secondary"),
                use_container_width=True,
            ):
                if is_on:
                    selected.discard(s)
                else:
                    selected.add(s)
                st.rerun()
    return list(selected & set(subs))


def _render_filters():
    with st.container(border=True):
        c1, c2 = st.columns([1.2, 4])
        majors = ["(전체)"] + get_major_categories()
        selected_major = c1.selectbox("대분류", majors, key="_pmo_major")

        selected_subs: list[str] = []
        with c2:
            if selected_major != "(전체)":
                subs = get_sub_categories(selected_major)
                if subs:
                    selected_subs = _render_sub_buttons(subs, selected_major)
                else:
                    st.selectbox("중분류", ["(해당 없음)"], disabled=True)
            else:
                st.selectbox("중분류", ["(해당 없음)"], disabled=True)

        c3, c4 = st.columns([2, 3])
        promo_cats: list[str] = []
        all_cats = _collect_all_promo_categories()
        if all_cats:
            promo_cats = c3.multiselect(
                "프로모션 카테고리", all_cats, key="_pmo_promo_cats",
                placeholder="전체 (선택 시 필터링)",
            )
        else:
            c3.selectbox("프로모션 카테고리", ["(등록된 카테고리 없음)"], disabled=True)

        d1, d2 = c4.columns(2)
        target_start = d1.date_input(
            "캠페인 시작일", key="_pmo_target_start", value=None,
            help="프로모션 기간과 겹치는 항목만 필터링",
        )
        target_end = d2.date_input(
            "캠페인 종료일", key="_pmo_target_end", value=None,
        )

    return selected_major, selected_subs, promo_cats, target_start, target_end


def _collect_all_promo_categories() -> list[str]:
    seen = []
    for p in get_home_promotions():
        for name, _ in p["categories"]:
            if name and name not in seen:
                seen.append(name)
    return seen


@st.cache_data(ttl=300)
def _get_all_media_lite() -> list[dict]:
    from utils.sheets import _get_all_media_rows, _build_cat_lookup
    rows = _get_all_media_rows()
    lookup = _build_cat_lookup()
    return [
        {
            "name": r["매체명"],
            "major": lookup.get(r.get("카테고리ID", ""), {}).get("major_category", ""),
            "sub": lookup.get(r.get("카테고리ID", ""), {}).get("sub_category", ""),
        }
        for r in rows
    ]


def _apply_filters(promos, major, subs, promo_cats, target_start, target_end):
    no_filter = (major == "(전체)" and not subs and not promo_cats
                 and not target_start and not target_end)
    if no_filter:
        return promos
    media_cat_map = build_media_cat_map()
    media_sub_map = {m["name"]: m.get("sub", "") for m in _get_all_media_lite()}

    filtered = []
    for p in promos:
        if major != "(전체)":
            if media_cat_map.get(p["media_name"], "") != major:
                continue
            if subs and media_sub_map.get(p["media_name"], "") not in subs:
                continue
        if promo_cats:
            names = [n for n, _ in p["categories"]]
            if not any(pc in names for pc in promo_cats):
                continue
        if target_start or target_end:
            p_start = p["start_date"] or date.min
            p_end = p["end_date"] or date.max
            t_start = target_start or date.min
            t_end = target_end or date.max
            # 겹침 조건: p_start <= t_end AND p_end >= t_start
            if not (p_start <= t_end and p_end >= t_start):
                continue
        filtered.append(p)
    return filtered


# ----------------------------------------------------------------------
# 카드 렌더
# ----------------------------------------------------------------------

def _render_promo_card(promo: dict):
    is_active = promo["status"] == "active"
    opacity = "1" if is_active else "0.55"
    grayscale = "0" if is_active else "0.55"

    chip_html = "".join(_chip_html(name, key) for name, key in promo["categories"])
    card_img = promo.get("preview_image_url") or promo["image_url"]
    if card_img:
        img_tag = (
            f"<img src='{card_img}' style='width:100%;aspect-ratio:16/9;"
            f"object-fit:cover;display:block;background:#eee;'/>"
        )
    else:
        img_tag = (
            "<div style='width:100%;aspect-ratio:16/9;background:#f0f0f0;"
            "display:flex;align-items:center;justify-content:center;color:#bbb;"
            "font-size:12px;'>이미지 없음</div>"
        )

    media_span = ""
    if promo["media_name"]:
        media_span = (
            f"<span style='font-size:11px;color:#666;'>{promo['media_name']}</span>"
        )

    header_row = (
        f"<div style='display:flex;align-items:center;gap:8px;margin-bottom:8px;"
        f"min-height:22px;flex-wrap:wrap;'>"
        f"{media_span}{chip_html}"
        f"</div>"
    )

    card_html = (
        f"<div style='opacity:{opacity};filter:grayscale({grayscale});"
        f"border:0.5px solid #ddd;border-top-left-radius:8px;border-top-right-radius:8px;"
        f"overflow:hidden;background:#fff;border-bottom:none;'>"
        f"{img_tag}"
        f"<div style='padding:12px 14px 8px;'>"
        f"{header_row}"
        f"<div style='font-size:14px;font-weight:700;margin-bottom:4px;color:#111;'>{promo['name']}</div>"
        f"<div style='font-size:12px;color:#666;min-height:18px;'>{promo['subtitle']}</div>"
        f"</div></div>"
    )
    st.markdown(card_html, unsafe_allow_html=True)
    if st.button("자세히 보기", key=f"promo_btn_{promo['id']}",
                 use_container_width=True):
        _open_view_popup(promo["id"])
        st.rerun()


def _render_grid(promos: list[dict]):
    if not promos:
        st.markdown(
            "<div style='color:#999;text-align:center;padding:40px 0;font-size:13px;'>"
            "표시할 프로모션이 없습니다.</div>",
            unsafe_allow_html=True,
        )
        return
    cols_per_row = 4
    for i in range(0, len(promos), cols_per_row):
        row_items = promos[i:i + cols_per_row]
        cols = st.columns(cols_per_row)
        for col, promo in zip(cols, row_items):
            with col:
                _render_promo_card(promo)


# ----------------------------------------------------------------------
# 단일 팝업 (view + edit 모드 통합)
# ----------------------------------------------------------------------

def _keep_popup():
    """내부 rerun 시 팝업이 다시 열리도록 플래그 재세팅."""
    st.session_state["_promo_popup_open"] = True


@st.dialog("프로모션")
def render_promo_popup():
    # 첫 렌더 시 플래그 pop → X 닫기 시 필터 변경으로 재오픈되지 않음
    st.session_state.pop("_promo_popup_open", None)
    mode = st.session_state.get("_promo_popup_mode", "view")
    promo_id = st.session_state.get("_promo_popup_promo_id")

    # add 모드는 promo_id=None이지만 mode='edit'
    existing_promo = None
    if promo_id:
        existing_promo = next(
            (p for p in get_home_promotions() if p["id"] == promo_id), None
        )

    if mode == "view":
        _render_view_mode(existing_promo)
    else:
        _render_edit_mode(existing_promo)


def _render_view_mode(promo):
    if not promo:
        st.warning("프로모션 정보를 찾을 수 없습니다.")
        return

    if promo["image_url"]:
        st.image(promo["image_url"], use_container_width=True)

    if promo["media_name"]:
        st.markdown(
            f"<div style='font-size:12px;color:#666;margin-bottom:4px;'>"
            f"{promo['media_name']}</div>",
            unsafe_allow_html=True,
        )

    chip_html = "".join(_chip_html(name, key) for name, key in promo["categories"])
    if chip_html:
        st.markdown(chip_html, unsafe_allow_html=True)

    st.markdown(f"### {promo['name']}")
    if promo["subtitle"]:
        st.caption(promo["subtitle"])

    period = f"{promo['start_date'] or '-'} ~ {promo['end_date'] or '상시'}"
    st.markdown(f"**운영 기간**  \n{period}")

    if promo["memo"]:
        st.markdown(
            f"<div style='background:#FFF8E1;border-left:3px solid #F2A93B;"
            f"border-radius:6px;padding:12px 14px;font-size:12px;margin-top:10px;'>"
            f"{promo['memo']}</div>",
            unsafe_allow_html=True,
        )

    if is_admin():
        st.divider()
        if st.button("✎ 수정하기", key=f"promo_edit_entry_{promo['id']}",
                     use_container_width=True):
            _switch_to_edit_mode(promo)
            _keep_popup()
            st.rerun()


def _render_edit_mode(existing_promo):
    is_edit = existing_promo is not None
    st.markdown("#### 프로모션 수정" if is_edit else "#### 프로모션 등록")

    st.text_input("매체명", key="_promo_f_media",
                  placeholder="예: 네이버GFA, 카카오모먼트",
                  help="필터 매칭을 위해 매체명이 정확히 일치해야 함")
    st.text_input("프로모션명 *", key="_promo_f_name",
                  placeholder="필수 입력")
    st.text_input("부제목", key="_promo_f_subtitle",
                  placeholder="카드 하단 한 줄 설명")

    st.markdown("**상세 이미지** (클릭 후 팝업에서 노출)")
    current_image = st.session_state.get("_promo_f_image", "")
    if current_image:
        st.image(current_image, use_container_width=True)
        if st.button("상세 이미지 제거", key="_promo_img_clear_btn"):
            st.session_state["_promo_f_image"] = ""
            _keep_popup()
            st.rerun()
    up_file = st.file_uploader(
        "상세 이미지 업로드 (최대 5MB, jpg/png/gif/webp)",
        type=["png", "jpg", "jpeg", "gif", "webp"],
        key="_promo_img_uploader",
    )
    if up_file is not None:
        if st.button("상세 이미지 업로드", key="_promo_img_upload_btn", type="primary"):
            try:
                url = upload_notice_image(up_file.read(), up_file.name)
                st.session_state["_promo_f_image"] = url
                st.success("업로드 완료")
                _keep_popup()
                st.rerun()
            except Exception as e:
                st.error(f"업로드 실패: {e}")

    st.markdown("**미리보기 이미지** (카드 썸네일 · 미설정 시 상세 이미지 사용)")
    current_preview = st.session_state.get("_promo_f_preview", "")
    if current_preview:
        st.image(current_preview, use_container_width=True)
        if st.button("미리보기 제거", key="_promo_preview_clear_btn"):
            st.session_state["_promo_f_preview"] = ""
            _keep_popup()
            st.rerun()
    up_preview = st.file_uploader(
        "미리보기 이미지 업로드 (선택)",
        type=["png", "jpg", "jpeg", "gif", "webp"],
        key="_promo_preview_uploader",
    )
    if up_preview is not None:
        if st.button("미리보기 업로드", key="_promo_preview_upload_btn", type="primary"):
            try:
                url = upload_notice_image(up_preview.read(), up_preview.name)
                st.session_state["_promo_f_preview"] = url
                st.success("업로드 완료")
                _keep_popup()
                st.rerun()
            except Exception as e:
                st.error(f"업로드 실패: {e}")

    col_s, col_e = st.columns(2)
    with col_s:
        st.date_input("시작일", key="_promo_f_start")
    with col_e:
        st.date_input("종료일 (미정이면 비워두기)", key="_promo_f_end")

    st.markdown("**카테고리 (칩)**")
    cats = st.session_state.get("_promo_form_cats", [])
    for i, (cname, ckey) in enumerate(cats):
        c1, c2, c3 = st.columns([2, 2, 1])
        c1.markdown(_chip_html(cname, ckey), unsafe_allow_html=True)
        c2.caption(CHIP_PRESETS[ckey]["label"])
        if c3.button("삭제", key=f"cat_del_{i}"):
            st.session_state["_promo_form_cats"].pop(i)
            _keep_popup()
            st.rerun()

    new_c1, new_c2, new_c3 = st.columns([2, 2, 1])
    new_c1.text_input(
        "카테고리명", key="_new_cat_name",
        label_visibility="collapsed", placeholder="예: 보너스",
    )
    new_c2.selectbox(
        "색상", options=list(CHIP_PRESETS.keys()),
        format_func=lambda k: CHIP_PRESETS[k]["label"],
        key="_new_cat_preset", label_visibility="collapsed",
    )
    if new_c3.button("추가", key="_cat_add_btn"):
        nm = (st.session_state.get("_new_cat_name") or "").strip()
        preset = st.session_state.get("_new_cat_preset") or DEFAULT_CHIP_PRESET
        if nm:
            existing_names = [n for n, _ in cats]
            if nm in existing_names:
                st.warning(f"'{nm}' 카테고리가 이미 있습니다.")
            else:
                st.session_state["_promo_form_cats"].append((nm, preset))
                _keep_popup()
                st.rerun()

    st.text_area("메모 (상세 팝업에만 노출)", key="_promo_f_memo")

    st.divider()
    save_col, cancel_col, del_col = st.columns([2, 1, 1])

    if save_col.button("저장", key="promo_save_btn", type="primary",
                       use_container_width=True):
        name_val = (st.session_state.get("_promo_f_name") or "").strip()
        if not name_val:
            st.error("프로모션명은 필수입니다.")
            return

        _save_promotion(is_edit, existing_promo)
        return

    if cancel_col.button("취소", key="promo_cancel_btn",
                        use_container_width=True):
        _reset_popup_state()
        st.rerun()

    if is_edit:
        if not st.session_state.get("_promo_del_confirm"):
            if del_col.button("삭제", key="promo_del_btn",
                             use_container_width=True):
                st.session_state["_promo_del_confirm"] = True
                _keep_popup()
                st.rerun()
        else:
            st.error("정말 삭제하시겠습니까?")
            dc1, dc2 = st.columns(2)
            if dc1.button("삭제 확정", key="promo_del_confirm_btn",
                         type="primary", use_container_width=True):
                delete_home_promotion(existing_promo["row"])
                _reset_popup_state()
                st.rerun()
            if dc2.button("취소", key="promo_del_cancel_btn",
                         use_container_width=True):
                st.session_state.pop("_promo_del_confirm", None)
                _keep_popup()
                st.rerun()


def _save_promotion(is_edit, existing_promo):
    media_name = (st.session_state.get("_promo_f_media") or "").strip()
    name = (st.session_state.get("_promo_f_name") or "").strip()
    subtitle = (st.session_state.get("_promo_f_subtitle") or "").strip()
    image_url = (st.session_state.get("_promo_f_image") or "").strip()
    preview_url = (st.session_state.get("_promo_f_preview") or "").strip()
    memo = (st.session_state.get("_promo_f_memo") or "").strip()
    start_d = st.session_state.get("_promo_f_start")
    end_d = st.session_state.get("_promo_f_end")
    cats = list(st.session_state.get("_promo_form_cats", []))

    start_str = start_d.isoformat() if isinstance(start_d, date) else ""
    end_str = end_d.isoformat() if isinstance(end_d, date) else ""

    if is_edit:
        update_home_promotion(existing_promo["row"], media_name, name, subtitle,
                              image_url, cats, start_str, end_str, memo,
                              preview_image_url=preview_url)
    else:
        create_home_promotion(media_name, name, subtitle, image_url,
                              cats, start_str, end_str, memo,
                              preview_image_url=preview_url)
    _reset_popup_state()
    st.rerun()


# ----------------------------------------------------------------------
# 페이지 본문
# ----------------------------------------------------------------------

admin = is_admin()

head_col, btn_col = st.columns([5, 1])
head_col.markdown("### 매체 프로모션")
if admin:
    if btn_col.button("+ 등록", key="promo_add_btn", use_container_width=True):
        _open_edit_popup(None)
        st.rerun()

major, subs, promo_cats, target_start, target_end = _render_filters()

all_promos = get_home_promotions()
filtered = _apply_filters(all_promos, major, subs, promo_cats, target_start, target_end)

today = date.today()
ongoing = [p for p in filtered if p["status"] == "active" and (p["start_date"] is None or p["start_date"] <= today)]
upcoming = [p for p in filtered if p["status"] == "active" and p["start_date"] and p["start_date"] > today]
ended = [p for p in filtered if p["status"] == "inactive"]

tab_labels = [
    f"진행중 ({len(ongoing)})",
    f"진행예정 ({len(upcoming)})",
    f"지난달 종료 ({len(ended)})",
]
t1, t2, t3 = st.tabs(tab_labels)
with t1:
    _render_grid(ongoing)
with t2:
    _render_grid(upcoming)
with t3:
    _render_grid(ended)

if st.session_state.get("_promo_popup_open"):
    render_promo_popup()
