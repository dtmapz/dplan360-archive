import streamlit as st
import io
from utils import db
from utils.auth import get_current_user
from utils.ui import set_current_page, inject_base_style

set_current_page("creative_guide")

user = get_current_user()
BUCKET = "creative-guides"

st.markdown("## 🎨 CREATIVE GUIDE")

# ---------- 데이터 로드 ----------
guides = db.get_creative_guides()
all_media = db.get_all_media()

# 매체명 → 카테고리 맵 (media 테이블 기준)
media_cat_map = {}
for m in all_media:
    cat = m.get("categories") or {}
    media_cat_map[m["name"]] = cat.get("major_category", "")

# 제작가이드 매체명 → {product_name: guide} 맵
guide_map = {}
for g in guides:
    guide_map.setdefault(g["media_name"], {})[g["product_name"]] = g

# ---------- 필터 ----------
majors = db.get_major_categories()
col_f1, col_f2, col_f3 = st.columns([2, 2, 3])
with col_f1:
    major_filter = st.selectbox("대분류", ["전체"] + majors, label_visibility="collapsed",
                                 key="cg_major", placeholder="대분류")
with col_f2:
    if major_filter and major_filter != "전체":
        subs = db.get_sub_categories(major_filter)
        sub_filter = st.selectbox("중분류", ["전체"] + subs, label_visibility="collapsed",
                                   key="cg_sub", placeholder="중분류")
    else:
        sub_filter = "전체"
        st.selectbox("중분류", ["전체"], label_visibility="collapsed",
                      key="cg_sub_empty", disabled=True)
with col_f3:
    search_kw = st.text_input("매체명 검색", placeholder="🔍 매체명 직접 검색",
                               label_visibility="collapsed", key="cg_search")

# ---------- 표시할 매체 목록 결정 ----------
# guide_map에 있는 매체 + all_media의 매체명 통합
all_media_names = sorted(set(
    [m["name"] for m in all_media] + list(guide_map.keys())
))

# 필터 적용
def passes_filter(name: str) -> bool:
    if search_kw and search_kw.lower() not in name.lower():
        return False
    if major_filter and major_filter != "전체":
        if media_cat_map.get(name, "") != major_filter:
            return False
    return True

filtered_names = [n for n in all_media_names if passes_filter(n)]

# ---------- 선택 상태 ----------
if "cg_selected" not in st.session_state:
    st.session_state["cg_selected"] = {}  # {(media_name, product_name): True}

# ---------- 매체 카드 그리드 ----------
st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
n_cols = 3
rows = (len(filtered_names) + n_cols - 1) // n_cols

for row_i in range(rows):
    cols = st.columns(n_cols)
    for col_i, col in enumerate(cols):
        idx = row_i * n_cols + col_i
        if idx >= len(filtered_names):
            break
        media_name = filtered_names[idx]
        products = guide_map.get(media_name, {})
        has_any_selected = any(
            st.session_state["cg_selected"].get((media_name, p))
            for p in products
        )

        with col:
            # 카드 테두리 강조
            border = "1.5px solid #0B0B0B" if has_any_selected else "0.5px solid var(--border)"
            st.markdown(
                f"<div style='border:{border}; border-radius:8px; overflow:hidden; "
                f"background:var(--surface-2); margin-bottom:8px;'>",
                unsafe_allow_html=True,
            )

            # 헤더
            col_name, col_edit = st.columns([4, 1])
            with col_name:
                expand_key = f"cg_expand_{media_name}"
                if expand_key not in st.session_state:
                    st.session_state[expand_key] = False
                expanded = st.session_state[expand_key]
                chevron = "▲" if expanded else "▼"
                if st.button(
                    f"{media_name} {chevron}",
                    key=f"cg_toggle_{media_name}",
                    use_container_width=True,
                ):
                    st.session_state[expand_key] = not expanded
                    st.rerun()
            with col_edit:
                if st.button("수정", key=f"cg_edit_{media_name}"):
                    st.session_state["cg_edit_media"] = media_name
                    st.rerun()

            # 상품 목록 (펼쳐진 경우)
            if st.session_state.get(f"cg_expand_{media_name}"):
                if products:
                    for product_name, guide in sorted(products.items()):
                        has_file = bool(guide.get("storage_path"))
                        key = (media_name, product_name)
                        if has_file:
                            checked = st.session_state["cg_selected"].get(key, False)
                            new_val = st.checkbox(
                                product_name,
                                value=checked,
                                key=f"cg_check_{media_name}_{product_name}",
                            )
                            if new_val != checked:
                                st.session_state["cg_selected"][key] = new_val
                                st.rerun()
                        else:
                            st.markdown(
                                f"<div style='opacity:0.35; padding:4px 12px; "
                                f"font-size:13px; color:var(--text-muted);'>☐ {product_name}</div>",
                                unsafe_allow_html=True,
                            )
                else:
                    st.caption("등록된 상품이 없습니다.")

            st.markdown("</div>", unsafe_allow_html=True)

# ---------- 선택 영역 ----------
selected = {k: v for k, v in st.session_state["cg_selected"].items() if v}
if selected:
    st.markdown(
        "<div style='border:0.5px solid #F2A93B; border-radius:8px; "
        "padding:12px 14px; background:#FFFDF5; margin:12px 0;'>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<div style='font-size:12px; font-weight:500; color:#854F0B; margin-bottom:8px;'>"
        f"선택된 상품 ({len(selected)}개)</div>",
        unsafe_allow_html=True,
    )
    for (mn, pn) in list(selected.keys()):
        col_tag, col_x = st.columns([5, 1])
        col_tag.markdown(
            f"<span style='background:#fff; border:0.5px solid #F2A93B; border-radius:20px; "
            f"padding:4px 10px; font-size:12px;'>{mn} · {pn}</span>",
            unsafe_allow_html=True,
        )
        if col_x.button("×", key=f"cg_remove_{mn}_{pn}"):
            st.session_state["cg_selected"][(mn, pn)] = False
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    # ---------- 다운로드 ----------
    if st.button("선택한 제작가이드 통합 다운로드", type="primary", use_container_width=True):
        try:
            import openpyxl
            merged_wb = openpyxl.Workbook()
            merged_wb.remove(merged_wb.active)

            for (mn, pn) in selected:
                guide = guide_map.get(mn, {}).get(pn)
                if not guide:
                    continue
                file_bytes = db.download_from_storage(BUCKET, guide["storage_path"])
                src_wb = openpyxl.load_workbook(io.BytesIO(file_bytes))
                for sheet_name in src_wb.sheetnames:
                    src_ws = src_wb[sheet_name]
                    new_ws = merged_wb.create_sheet(title=sheet_name[:31])
                    for row in src_ws.iter_rows():
                        for cell in row:
                            new_ws[cell.coordinate].value = cell.value

            buf = io.BytesIO()
            merged_wb.save(buf)
            buf.seek(0)
            st.download_button(
                "📥 다운로드",
                data=buf,
                file_name="통합_제작가이드.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        except Exception as e:
            st.error(f"다운로드 중 오류: {e}")

st.divider()

# ---------- 파일 업로드 / 수정 ----------
st.markdown("#### 제작가이드 추가 / 수정")

edit_media = st.session_state.get("cg_edit_media", "")
media_options = sorted(set([m["name"] for m in all_media]))

col_u1, col_u2 = st.columns([2, 2])
with col_u1:
    upload_media = st.selectbox(
        "매체 선택",
        media_options,
        index=media_options.index(edit_media) if edit_media in media_options else 0,
        key="cg_upload_media",
    )
with col_u2:
    upload_product = st.text_input("상품명", key="cg_upload_product")

upload_file = st.file_uploader("엑셀 파일 업로드 (.xlsx)", type=["xlsx"], key="cg_upload_file")

if st.button("저장", type="primary", key="cg_upload_btn"):
    if not upload_media or not upload_product or not upload_file:
        st.error("매체, 상품명, 파일을 모두 입력해주세요.")
    else:
        existing = guide_map.get(upload_media, {}).get(upload_product)
        storage_path = f"{upload_media}/{upload_product}.xlsx"
        file_bytes = upload_file.read()

        if existing:
            db.delete_from_storage(BUCKET, existing["storage_path"])
            db.upload_to_storage(BUCKET, storage_path, file_bytes)
            db.update_creative_guide(existing["id"], storage_path)
        else:
            db.upload_to_storage(BUCKET, storage_path, file_bytes)
            cat = media_cat_map.get(upload_media, "")
            db.create_creative_guide(upload_media, cat, upload_product, storage_path)

        st.session_state["cg_edit_media"] = ""
        st.success(f"'{upload_media} · {upload_product}' 저장 완료.")
        st.rerun()
