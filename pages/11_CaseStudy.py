"""캠페인 성공사례 자동 생성 페이지.

MediaPromo 패턴을 따라 그리드 + 상세/편집 팝업으로 구성.
Gemini로 카피 자동 생성 → 16:9 슬라이드 HTML 미리보기 → Sheets 저장.
"""
import streamlit as st
import streamlit.components.v1 as components
from datetime import date

from utils.auth import is_admin
from utils.ui import set_current_page
from utils.db import upload_notice_image
from utils.sheets import (
    get_case_studies,
    create_case_study,
    update_case_study,
    delete_case_study,
)
from utils.casestudy_llm import generate_copy
from utils.casestudy_render import build_slide_html
from utils.casestudy_pptx import build_slide_pptx

set_current_page("casestudy")

st.markdown(
    "<div style='background:rgba(214,69,69,0.3); color:#A83232; "
    "border:1px solid rgb(214,69,69); border-radius:8px; "
    "font-size:13px; font-weight:600; padding:9px 14px; margin-bottom:16px;'>"
    "<span style='display:inline-block; font-size:10.5px; font-weight:700; "
    "padding:2px 8px; border-radius:4px; margin-right:10px; letter-spacing:0.02em; "
    "vertical-align:middle; background:#D64545; color:#ffffff;'>공지</span>"
    "※ 외부 자료 활용 시 광고주 정보 및 소재 이미지 가공 필수"
    "</div>",
    unsafe_allow_html=True,
)


GENDER_OPTS = ["M", "F"]
TYPE_OPTS = ["Awareness", "Consideration", "Conversion"]


# ---------------------------------------------------------------------
# 세션 상태
# ---------------------------------------------------------------------

STATE_KEYS = (
    "_cs_popup_open", "_cs_popup_mode", "_cs_popup_id",
    "_cs_f_scope", "_cs_f_advertiser", "_cs_f_brand", "_cs_f_industry",
    "_cs_f_media", "_cs_f_gender", "_cs_f_age",
    "_cs_f_ystart", "_cs_f_yend", "_cs_f_types",
    "_cs_f_objective", "_cs_f_strategy", "_cs_f_insight", "_cs_f_extra",
    "_cs_f_results", "_cs_f_image", "_cs_f_ai",
    "_cs_del_confirm", "_cs_img_uploader", "_cs_step", "_cs_loaded_id",
)


def _reset_state():
    for k in STATE_KEYS:
        st.session_state.pop(k, None)


def _load_into_state(cs: dict):
    st.session_state["_cs_f_scope"] = cs.get("share_scope", "Internal")
    st.session_state["_cs_f_advertiser"] = cs.get("advertiser", "")
    st.session_state["_cs_f_brand"] = cs.get("brand", "")
    st.session_state["_cs_f_industry"] = cs.get("industry", "")
    st.session_state["_cs_f_media"] = cs.get("media", "")
    st.session_state["_cs_f_gender"] = [g for g in cs.get("target_gender", "").split("/") if g]
    st.session_state["_cs_f_age"] = cs.get("target_age", "")
    st.session_state["_cs_f_ystart"] = int(cs.get("period_start") or date.today().year)
    st.session_state["_cs_f_yend"] = int(cs.get("period_end") or date.today().year)
    st.session_state["_cs_f_types"] = cs.get("campaign_types", []) or []
    st.session_state["_cs_f_objective"] = cs.get("objective", "")
    st.session_state["_cs_f_strategy"] = cs.get("strategy", "")
    st.session_state["_cs_f_insight"] = cs.get("insight", "")
    st.session_state["_cs_f_extra"] = cs.get("extra_note", "")
    st.session_state["_cs_f_results"] = cs.get("results", []) or []
    st.session_state["_cs_f_image"] = cs.get("creative_image_url", "")
    st.session_state["_cs_f_ai"] = cs.get("ai", {}) or {}


def _open_view(cs_id: str):
    _reset_state()
    st.session_state["_cs_popup_open"] = True
    st.session_state["_cs_popup_mode"] = "view"
    st.session_state["_cs_popup_id"] = cs_id


def _open_edit(cs: dict | None = None):
    _reset_state()
    st.session_state["_cs_popup_open"] = True
    st.session_state["_cs_popup_mode"] = "edit"
    if cs:
        st.session_state["_cs_popup_id"] = cs["id"]
        _load_into_state(cs)
        st.session_state["_cs_loaded_id"] = cs["id"]
    else:
        st.session_state["_cs_f_scope"] = "Internal"
        st.session_state["_cs_f_ystart"] = date.today().year
        st.session_state["_cs_f_yend"] = date.today().year
        st.session_state["_cs_f_results"] = [
            {"kpi_name": "", "value": ""},
            {"kpi_name": "", "value": ""},
            {"kpi_name": "", "value": ""},
        ]
        st.session_state["_cs_f_types"] = []
        st.session_state["_cs_f_gender"] = []
        st.session_state["_cs_loaded_id"] = "__new__"


def _keep_open():
    st.session_state["_cs_popup_open"] = True


# ---------------------------------------------------------------------
# 카드 그리드
# ---------------------------------------------------------------------

def _summary_chips(cs: dict) -> str:
    chips = []
    scope = cs.get("share_scope", "Internal")
    scope_bg = "#16A34A" if scope.lower() == "external" else "#35476B"
    scope_fg = "#fff" if scope.lower() == "external" else "#E5E9F0"
    chips.append(
        f"<span style='background:{scope_bg};color:{scope_fg};font-size:10px;font-weight:700;"
        f"padding:2px 7px;border-radius:3px;letter-spacing:1px;'>{scope.upper()}</span>"
    )
    if cs.get("media"):
        chips.append(
            f"<span style='background:#EEF2FF;color:#4C7DFF;font-size:10.5px;font-weight:700;"
            f"padding:2px 7px;border-radius:3px;'>{cs['media']}</span>"
        )
    return " ".join(chips)


def _render_card(cs: dict):
    ai = cs.get("ai", {}) or {}
    title = ai.get("title") or cs.get("brand") or "(제목 없음)"
    title_plain = title.replace("[", "").replace("]", "")

    img_url = cs.get("creative_image_url") or ""
    if img_url:
        img_tag = (
            f"<img src='{img_url}' style='width:100%;aspect-ratio:16/9;"
            f"object-fit:cover;display:block;background:#eee;'/>"
        )
    else:
        img_tag = (
            "<div style='width:100%;aspect-ratio:16/9;background:linear-gradient(135deg,#D4C5B0,#A89578);"
            "display:flex;align-items:center;justify-content:center;color:rgba(255,255,255,0.7);"
            "font-size:11px;letter-spacing:1.5px;'>CAMPAIGN CREATIVE</div>"
        )

    period = ""
    if cs.get("period_start") or cs.get("period_end"):
        period = f"{cs.get('period_start', '')} ~ {cs.get('period_end', '')}"

    # KPI 요약 (최대 3개, 한 행)
    kpi_html = ""
    results = [r for r in (cs.get("results", []) or []) if r.get("kpi_name") or r.get("value")][:3]
    if results:
        cells = "".join(
            f"<div style='flex:1;min-width:0;'>"
            f"<div style='font-size:10px;color:#6B7280;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'>{(r.get('kpi_name') or '').strip()}</div>"
            f"<div style='font-size:16px;font-weight:800;color:#4C7DFF;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'>{(r.get('value') or '').strip()}</div>"
            f"</div>"
            for r in results
        )
        kpi_html = (
            f"<div style='margin-top:8px;padding:8px 10px;background:#F5F7FB;border-left:3px solid #4C7DFF;"
            f"display:flex;gap:10px;'>{cells}</div>"
        )

    card_html = (
        f"<div style='border:0.5px solid #ddd;border-top-left-radius:8px;border-top-right-radius:8px;"
        f"overflow:hidden;background:#fff;border-bottom:none;'>"
        f"{img_tag}"
        f"<div style='padding:12px 14px 8px;'>"
        f"<div style='display:flex;gap:6px;margin-bottom:8px;min-height:22px;flex-wrap:wrap;'>{_summary_chips(cs)}</div>"
        f"<div style='font-size:11px;color:#666;margin-bottom:2px;'>{cs.get('brand', '')} · {cs.get('advertiser', '')}</div>"
        f"<div style='font-size:14px;font-weight:700;margin-bottom:4px;color:#111;'>{title_plain}</div>"
        f"<div style='font-size:11px;color:#999;'>{period}</div>"
        f"{kpi_html}"
        f"</div></div>"
    )
    st.markdown(card_html, unsafe_allow_html=True)
    if st.button("자세히 보기", key=f"cs_btn_{cs['id']}", use_container_width=True):
        _open_view(cs["id"])
        st.rerun()


def _render_grid(items: list[dict]):
    if not items:
        st.markdown(
            "<div style='color:#999;text-align:center;padding:40px 0;font-size:13px;'>"
            "등록된 성공사례가 없습니다.</div>",
            unsafe_allow_html=True,
        )
        return
    cols_per_row = 3
    for i in range(0, len(items), cols_per_row):
        row = items[i:i + cols_per_row]
        cols = st.columns(cols_per_row)
        for col, cs in zip(cols, row):
            with col:
                _render_card(cs)


# ---------------------------------------------------------------------
# 팝업 (view / edit 통합)
# ---------------------------------------------------------------------

@st.dialog(" ", width="large")
def render_popup():
    st.session_state.pop("_cs_popup_open", None)
    mode = st.session_state.get("_cs_popup_mode", "view")
    cs_id = st.session_state.get("_cs_popup_id")

    existing = None
    if cs_id:
        existing = next((x for x in get_case_studies() if x["id"] == cs_id), None)

    if mode == "view":
        _view(existing)
    else:
        _edit(existing)


def _view(cs: dict | None):
    if not cs:
        st.warning("사례를 찾을 수 없습니다.")
        return

    ai = cs.get("ai", {}) or {}
    # 슬라이드 프리뷰 (다이얼로그를 최대한 채우도록 확대)
    popup_scale = 0.68
    html_body = build_slide_html(cs, ai, standalone=True, scale=popup_scale)
    components.html(html_body, height=int(720 * popup_scale) + 40, scrolling=False)

    st.divider()

    # 요약 정보
    c1, c2 = st.columns(2)
    c1.markdown(f"**광고주 · 브랜드**  \n{cs.get('advertiser', '-')} · {cs.get('brand', '-')}")
    c2.markdown(f"**업종**  \n{cs.get('industry', '-')}")
    c3, c4 = st.columns(2)
    c3.markdown(f"**매체**  \n{cs.get('media', '-')}")
    c4.markdown(f"**기간**  \n{cs.get('period_start', '-')} ~ {cs.get('period_end', '-')}")
    c5, c6 = st.columns(2)
    c5.markdown(f"**타겟**  \n{cs.get('target_gender', '-')} · {cs.get('target_age', '-')}")
    c6.markdown(f"**타입**  \n{', '.join(cs.get('campaign_types', [])) or '-'}")

    with st.expander("사용자 원본 입력", expanded=False):
        st.markdown("**Objective**"); st.text(cs.get("objective") or "-")
        st.markdown("**Strategy**"); st.text(cs.get("strategy") or "-")
        st.markdown("**Insight**"); st.text(cs.get("insight") or "-")
        if cs.get("extra_note"):
            st.markdown("**추가 메모**"); st.text(cs["extra_note"])

    # 다운로드
    full_html = build_slide_html(cs, ai, standalone=True, scale=1.0)
    dl_a, dl_b = st.columns(2)
    dl_a.download_button(
        "HTML 슬라이드 다운로드",
        data=full_html.encode("utf-8"),
        file_name=f"{cs.get('brand', 'case_study')}_{cs['id']}.html",
        mime="text/html",
        use_container_width=True,
    )
    try:
        pptx_bytes = build_slide_pptx(cs, ai)
        dl_b.download_button(
            "PPTX 다운로드",
            data=pptx_bytes,
            file_name=f"{cs.get('brand', 'case_study')}_{cs['id']}.pptx",
            mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            use_container_width=True,
            type="primary",
        )
    except Exception as e:
        dl_b.error(f"PPTX 생성 실패: {e}")

    if is_admin():
        st.divider()
        cA, cB = st.columns(2)
        if cA.button("✎ 수정", key=f"cs_edit_{cs['id']}", use_container_width=True):
            st.session_state["_cs_popup_mode"] = "edit"
            # 필드 로딩은 _edit()의 자가치유 가드가 전담 (_cs_loaded_id 불일치 감지 시 자동 로드)
            st.session_state.pop("_cs_loaded_id", None)
            _keep_open()
            st.rerun()
        if not st.session_state.get("_cs_del_confirm"):
            if cB.button("삭제", key=f"cs_del_{cs['id']}", use_container_width=True):
                st.session_state["_cs_del_confirm"] = True
                _keep_open()
                st.rerun()
        else:
            st.error("정말 삭제하시겠습니까?")
            dc1, dc2 = st.columns(2)
            if dc1.button("삭제 확정", key=f"cs_del_ok_{cs['id']}", type="primary", use_container_width=True):
                delete_case_study(cs["row"])
                _reset_state()
                st.rerun()
            if dc2.button("취소", key=f"cs_del_cancel_{cs['id']}", use_container_width=True):
                st.session_state.pop("_cs_del_confirm", None)
                _keep_open()
                st.rerun()


def _edit(existing: dict | None):
    is_edit = existing is not None

    # 자가치유 가드: 어떤 경로로 진입했든(수정 버튼 클릭, 다이얼로그 재실행 등)
    # 현재 로드된 캠페인 기본 정보가 existing과 다르면 여기서 다시 채워 넣는다.
    # 필드 로딩 책임을 이 한 곳으로 모아 두 곳에서 따로 관리하다 어긋나는 문제를 방지.
    desired_id = existing["id"] if is_edit else "__new__"
    if st.session_state.get("_cs_loaded_id") != desired_id:
        if is_edit:
            _load_into_state(existing)
        st.session_state["_cs_loaded_id"] = desired_id

    st.markdown("#### 성공사례 수정" if is_edit else "#### 성공사례 등록")

    step = st.session_state.setdefault("_cs_step", 1)

    # 스텝 인디케이터
    s1_style = "background:#0F1E3D;color:#fff;" if step == 1 else "background:#E5E9F0;color:#6B7280;"
    s2_style = "background:#0F1E3D;color:#fff;" if step == 2 else "background:#E5E9F0;color:#6B7280;"
    st.markdown(
        f"<div style='display:flex;gap:8px;margin-bottom:12px;'>"
        f"<div style='flex:1;padding:8px 12px;border-radius:4px;font-size:13px;font-weight:600;{s1_style}'>① 기본 정보</div>"
        f"<div style='flex:1;padding:8px 12px;border-radius:4px;font-size:13px;font-weight:600;{s2_style}'>② 카피 생성 &amp; 미리보기</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    if step == 1:
        # 주의: 위젯 key와 저장용 session_state key를 분리한다.
        # Streamlit은 위젯이 렌더링되지 않는 스텝(예: step2)으로 넘어가면 그 위젯의
        # session_state 값을 자동으로 삭제한다 — key="_cs_f_*"를 위젯에 직접 물려두면
        # step2 진입 시 광고주/브랜드 등 입력값이 통째로 사라지는 버그가 재현됨(2026-09).
        # 그래서 위젯은 "_cs_w_*" 키로 렌더링하고, 반환값을 안정적인 "_cs_f_*"에 매번 복사한다.
        c1, c2 = st.columns([1, 2])
        scope_opts = ["Internal", "External"]
        scope_val = st.session_state.get("_cs_f_scope", "Internal")
        st.session_state["_cs_f_scope"] = c1.radio(
            "공개 범위", scope_opts,
            index=scope_opts.index(scope_val) if scope_val in scope_opts else 0,
            key="_cs_w_scope", horizontal=True,
        )
        st.session_state["_cs_f_media"] = c2.text_input(
            "매체 *", value=st.session_state.get("_cs_f_media", ""),
            key="_cs_w_media", placeholder="예: Meta, Google, Kakao",
        )

        c1, c2 = st.columns(2)
        st.session_state["_cs_f_advertiser"] = c1.text_input(
            "광고주 *", value=st.session_state.get("_cs_f_advertiser", ""), key="_cs_w_advertiser",
        )
        st.session_state["_cs_f_brand"] = c2.text_input(
            "브랜드 *", value=st.session_state.get("_cs_f_brand", ""), key="_cs_w_brand",
        )

        c1, c2 = st.columns(2)
        st.session_state["_cs_f_industry"] = c1.text_input(
            "업종", value=st.session_state.get("_cs_f_industry", ""),
            key="_cs_w_industry", placeholder="예: Beauty / Skincare",
        )
        st.session_state["_cs_f_age"] = c2.text_input(
            "타겟 연령 *", value=st.session_state.get("_cs_f_age", ""),
            key="_cs_w_age", placeholder="예: 2049, 4050",
        )

        c1, c2 = st.columns(2)
        st.session_state["_cs_f_gender"] = c1.multiselect(
            "타겟 성별 *", GENDER_OPTS, default=st.session_state.get("_cs_f_gender", []),
            key="_cs_w_gender",
        )
        st.session_state["_cs_f_types"] = c2.multiselect(
            "캠페인 타입 *", TYPE_OPTS, default=st.session_state.get("_cs_f_types", []),
            key="_cs_w_types", help="3개 모두 선택 시 FULL-FUNNEL 로 자동 축약",
        )

        c1, c2 = st.columns(2)
        st.session_state["_cs_f_ystart"] = c1.number_input(
            "시작 연도 *", min_value=2000, max_value=2100, step=1,
            value=int(st.session_state.get("_cs_f_ystart") or date.today().year),
            key="_cs_w_ystart",
        )
        st.session_state["_cs_f_yend"] = c2.number_input(
            "종료 연도 *", min_value=2000, max_value=2100, step=1,
            value=int(st.session_state.get("_cs_f_yend") or date.today().year),
            key="_cs_w_yend",
        )

        st.markdown("**성과 KPI** (2~4개 · 첫 KPI가 강조 표시)")
        results = st.session_state.get("_cs_f_results", [])
        for i, r in enumerate(results):
            rc1, rc2, rc3 = st.columns([2, 2, 0.5])
            r["kpi_name"] = rc1.text_input(
                "KPI 이름", value=r.get("kpi_name", ""),
                key=f"_cs_kpi_name_{i}", label_visibility="collapsed",
                placeholder="예: ROAS",
            )
            r["value"] = rc2.text_input(
                "수치", value=r.get("value", ""),
                key=f"_cs_kpi_val_{i}", label_visibility="collapsed",
                placeholder="예: +36%",
            )
            if rc3.button("×", key=f"_cs_kpi_del_{i}"):
                results.pop(i)
                st.session_state["_cs_f_results"] = results
                _keep_open()
                st.rerun()
        st.session_state["_cs_f_results"] = results
        if len(results) < 4:
            if st.button("+ KPI 추가", key="_cs_kpi_add"):
                results.append({"kpi_name": "", "value": ""})
                st.session_state["_cs_f_results"] = results
                _keep_open()
                st.rerun()

        st.session_state["_cs_f_objective"] = st.text_area(
            "캠페인 목표 (Objective) *", value=st.session_state.get("_cs_f_objective", ""),
            key="_cs_w_objective", height=90,
            placeholder="배경·문제·해결 과제를 자유롭게 서술 → AI가 bullet로 정리",
        )
        st.session_state["_cs_f_strategy"] = st.text_area(
            "캠페인 전략 (Strategy) *", value=st.session_state.get("_cs_f_strategy", ""),
            key="_cs_w_strategy", height=90,
            placeholder="실행한 액션 중심 → AI가 3개 bullet로 정리",
        )
        st.session_state["_cs_f_insight"] = st.text_area(
            "인사이트 / 테스트 (Insight) *", value=st.session_state.get("_cs_f_insight", ""),
            key="_cs_w_insight", height=90,
            placeholder="A/B 테스트 결과·학습·시사점 → AI가 bullet로 정리",
        )
        st.session_state["_cs_f_extra"] = st.text_area(
            "추가 메모 (extra_note)", value=st.session_state.get("_cs_f_extra", ""),
            key="_cs_w_extra", height=60,
            placeholder="선택 · AI가 title/caption/bullet 작성 시 보조 힌트로만 활용",
        )

        st.markdown("**크리에이티브 이미지** (16:9 권장)")
        current_img = st.session_state.get("_cs_f_image", "")
        if current_img:
            st.image(current_img, use_container_width=True)
            if st.button("이미지 제거", key="_cs_img_clear"):
                st.session_state["_cs_f_image"] = ""
                _keep_open()
                st.rerun()
        up = st.file_uploader(
            "이미지 업로드 (jpg/png/gif/webp)",
            type=["png", "jpg", "jpeg", "gif", "webp"],
            key="_cs_img_uploader",
        )
        if up is not None:
            if st.button("업로드", key="_cs_img_upload_btn", type="primary"):
                try:
                    url = upload_notice_image(up.read(), up.name)
                    st.session_state["_cs_f_image"] = url
                    st.success("업로드 완료")
                    _keep_open()
                    st.rerun()
                except Exception as e:
                    st.error(f"업로드 실패: {e}")

        st.divider()
        nxt_c, cancel1_c = st.columns([2, 1])
        if nxt_c.button("② 카피 생성 단계로 이동 →", type="primary", use_container_width=True):
            err = _validate(_collect_form())
            if err:
                st.error(err)
            else:
                st.session_state["_cs_step"] = 2
                _keep_open()
                st.rerun()
        if cancel1_c.button("취소", key="_cs_cancel_step1", use_container_width=True):
            _reset_state()
            st.rerun()

    elif step == 2:
        cs_now = _collect_form()

        back_c, _ = st.columns([1, 3])
        if back_c.button("← ① 기본 정보 수정", use_container_width=True):
            st.session_state["_cs_step"] = 1
            _keep_open()
            st.rerun()

        gen_c1, gen_c2 = st.columns([1, 1])
        if gen_c1.button("🤖 AI 카피 생성 / 재생성", type="primary", use_container_width=True):
            err = _validate(cs_now)
            if err:
                st.error(err)
            else:
                with st.spinner("Gemini 카피 생성 중..."):
                    try:
                        ai = generate_copy(cs_now)
                        st.session_state["_cs_f_ai"] = ai
                        st.success("생성 완료 — 아래에서 편집 가능")
                    except Exception as e:
                        st.error(f"AI 생성 실패: {e}")
            _keep_open()
            st.rerun()

        ai = st.session_state.get("_cs_f_ai", {}) or {}
        if ai:
            with st.expander("AI 생성 결과 편집", expanded=True):
                ai["eyebrow"] = st.text_input("Eyebrow", value=ai.get("eyebrow", ""), key="_cs_ai_eyebrow")
                ai["title"] = st.text_area(
                    "Title (강조할 부분은 [대괄호]로 감쌈, \\n 로 줄바꿈)",
                    value=ai.get("title", ""), key="_cs_ai_title", height=90,
                )
                ai["caption"] = st.text_input("Caption", value=ai.get("caption", ""), key="_cs_ai_caption")
                ai["challenge_bullets"] = [
                    b.strip() for b in st.text_area(
                        "Challenge bullets (한 줄에 하나)",
                        value="\n".join(ai.get("challenge_bullets", []) or []),
                        key="_cs_ai_ch", height=100,
                    ).splitlines() if b.strip()
                ]
                ai["approach_bullets"] = [
                    b.strip() for b in st.text_area(
                        "Approach bullets (한 줄에 하나)",
                        value="\n".join(ai.get("approach_bullets", []) or []),
                        key="_cs_ai_ap", height=100,
                    ).splitlines() if b.strip()
                ]
                ai["insight_bullets"] = [
                    b.strip() for b in st.text_area(
                        "Insight bullets (한 줄에 하나)",
                        value="\n".join(ai.get("insight_bullets", []) or []),
                        key="_cs_ai_in", height=100,
                    ).splitlines() if b.strip()
                ]
                st.session_state["_cs_f_ai"] = ai

            st.markdown("**슬라이드 미리보기**")
            components.html(
                build_slide_html(cs_now, ai, standalone=True, scale=0.55),
                height=int(720 * 0.55) + 40,
                scrolling=False,
            )
            try:
                pptx_bytes = build_slide_pptx(cs_now, ai)
                st.download_button(
                    "🎁 PPTX 미리 다운로드 (저장 전)",
                    data=pptx_bytes,
                    file_name=f"{cs_now.get('brand', 'case_study')}_preview.pptx",
                    mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    use_container_width=True,
                )
            except Exception as e:
                st.warning(f"PPTX 미리보기 실패: {e}")
        else:
            st.info("위의 AI 카피 생성 버튼을 눌러주세요.")

        st.divider()
        save_c, cancel_c = st.columns([2, 1])
        if save_c.button("💾 저장", type="primary", use_container_width=True):
            cs_final = _collect_form()
            cs_final["ai"] = st.session_state.get("_cs_f_ai", {}) or {}
            err = _validate(cs_final, require_ai=True)
            if err:
                st.error(err)
                return
            if is_edit:
                cs_final["id"] = existing["id"]
                cs_final["created_at"] = existing.get("created_at", date.today().isoformat())
                update_case_study(existing["row"], cs_final)
                st.success("수정 완료")
            else:
                new_id = create_case_study(cs_final)
                st.success(f"등록 완료 ({new_id})")
            _reset_state()
            st.rerun()

        if cancel_c.button("취소", key="_cs_cancel_step2", use_container_width=True):
            _reset_state()
            st.rerun()


# ---------------------------------------------------------------------
# 폼 → dict / 검증
# ---------------------------------------------------------------------

def _collect_form() -> dict:
    return {
        "share_scope": st.session_state.get("_cs_f_scope", "Internal"),
        "advertiser": (st.session_state.get("_cs_f_advertiser") or "").strip(),
        "brand": (st.session_state.get("_cs_f_brand") or "").strip(),
        "industry": (st.session_state.get("_cs_f_industry") or "").strip(),
        "media": (st.session_state.get("_cs_f_media") or "").strip(),
        "target_gender": "/".join(st.session_state.get("_cs_f_gender") or []),
        "target_age": (st.session_state.get("_cs_f_age") or "").strip(),
        "period_start": str(st.session_state.get("_cs_f_ystart") or ""),
        "period_end": str(st.session_state.get("_cs_f_yend") or ""),
        "campaign_types": st.session_state.get("_cs_f_types") or [],
        "objective": (st.session_state.get("_cs_f_objective") or "").strip(),
        "strategy": (st.session_state.get("_cs_f_strategy") or "").strip(),
        "insight": (st.session_state.get("_cs_f_insight") or "").strip(),
        "extra_note": (st.session_state.get("_cs_f_extra") or "").strip(),
        "results": [
            {"kpi_name": (r.get("kpi_name") or "").strip(),
             "value": (r.get("value") or "").strip()}
            for r in st.session_state.get("_cs_f_results", [])
            if (r.get("kpi_name") or r.get("value"))
        ],
        "creative_image_url": st.session_state.get("_cs_f_image", ""),
    }


def _validate(cs: dict, require_ai: bool = False) -> str | None:
    required = [
        ("advertiser", "광고주"), ("brand", "브랜드"), ("media", "매체"),
        ("target_age", "타겟 연령"),
        ("objective", "캠페인 목표"), ("strategy", "캠페인 전략"),
        ("insight", "인사이트"),
    ]
    for k, label in required:
        if not cs.get(k):
            return f"{label}은 필수입니다."
    if not cs.get("target_gender"):
        return "타겟 성별을 선택하세요."
    if not cs.get("campaign_types"):
        return "캠페인 타입을 1개 이상 선택하세요."
    ys, ye = int(cs.get("period_start") or 0), int(cs.get("period_end") or 0)
    if ye < ys:
        return "종료 연도는 시작 연도 이후여야 합니다."
    results = cs.get("results", [])
    if len(results) < 2:
        return "성과 KPI는 최소 2개 필요합니다."
    if len(results) > 4:
        return "성과 KPI는 최대 4개까지 가능합니다."
    if require_ai:
        ai = cs.get("ai", {}) or {}
        if not ai.get("title"):
            return "AI 카피를 먼저 생성해주세요."
    return None


# ---------------------------------------------------------------------
# 본문
# ---------------------------------------------------------------------

admin = is_admin()

head_c, btn_c = st.columns([5, 1])
if admin:
    if btn_c.button("+ 신규 등록", use_container_width=True):
        _open_edit(None)
        st.rerun()

# 필터
all_items = get_case_studies()

f1, f2, f3 = st.columns([1, 1, 1])
media_opts = sorted({x["media"] for x in all_items if x.get("media")})
sel_media = f1.multiselect("매체", media_opts, key="_cs_flt_media")
scope_opts = ["Internal", "External"]
sel_scope = f2.multiselect("공개 범위", scope_opts, key="_cs_flt_scope")
type_opts = TYPE_OPTS
sel_type = f3.multiselect("캠페인 타입", type_opts, key="_cs_flt_type")

def _match(cs):
    if sel_media and cs.get("media") not in sel_media:
        return False
    if sel_scope and cs.get("share_scope") not in sel_scope:
        return False
    if sel_type and not (set(sel_type) & set(cs.get("campaign_types", []))):
        return False
    return True

items = [x for x in all_items if _match(x)]
st.caption(f"총 {len(items)}건")

_render_grid(items)

if st.session_state.get("_cs_popup_open"):
    render_popup()
