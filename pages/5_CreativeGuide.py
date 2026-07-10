import streamlit as st
import io
from utils import db
from utils.auth import get_current_user
from utils.ui import set_current_page
import uuid

set_current_page("creative_guide")

user = get_current_user()
BUCKET = "creative-guides"

# ---------- 데이터 로드 ----------
guides = db.get_creative_guides()
all_media = db.get_all_media()

media_cat_map = {}
for m in all_media:
    cat = m.get("categories") or {}
    media_cat_map[m["name"]] = cat.get("major_category", "")

guide_map = {}
for g in guides:
    guide_map.setdefault(g["media_name"], {})[g["product_name"]] = g

# ---------- 탭 ----------
tab_dl, tab_up = st.tabs(["제작가이드 다운로드", "업로드"])

# ============================
# 다운로드 탭
# ============================
with tab_dl:
    # 필터
    majors = db.get_major_categories()
    col_f1, col_f2, col_or, col_f3 = st.columns([2, 2, 0.4, 3])
    with col_f1:
        major_filter = st.selectbox(
            "대분류", [""] + majors, label_visibility="collapsed",
            key="cg_major", format_func=lambda x: "대분류 선택" if x == "" else x,
        )
    with col_f2:
        if major_filter:
            subs = db.get_sub_categories(major_filter)
            sub_filter = st.selectbox(
                "중분류", [""] + subs, label_visibility="collapsed",
                key="cg_sub", format_func=lambda x: "중분류" if x == "" else x,
            )
        else:
            sub_filter = ""
            st.selectbox("중분류", ["중분류"], label_visibility="collapsed",
                          key="cg_sub_empty", disabled=True)
    with col_or:
        st.markdown("<div style='text-align:center; color:var(--text-muted); "
                    "font-size:12px; padding-top:8px;'>또는</div>", unsafe_allow_html=True)
    with col_f3:
        search_kw = st.text_input(
            "검색", placeholder="🔍 매체명 직접 검색",
            label_visibility="collapsed", key="cg_search",
        )

    # 필터 적용 여부
    any_filter = bool(major_filter or search_kw)

    # 표시할 매체 목록
    all_media_names = sorted(set([m["name"] for m in all_media] + list(guide_map.keys())))

    def passes_filter(name: str) -> bool:
        if search_kw and search_kw.lower() not in name.lower():
            return False
        if major_filter:
            if media_cat_map.get(name, "") != major_filter:
                return False
        return True

    filtered_names = [n for n in all_media_names if passes_filter(n)] if any_filter else []

    # 선택 상태
    if "cg_selected" not in st.session_state:
        st.session_state["cg_selected"] = {}

    # 아무것도 선택 안 했을 때 Quick Guide
    if not any_filter:
        st.markdown(
            "<div style='margin:40px auto; max-width:340px; background:rgba(0,0,0,0.04); "
            "border-radius:12px; padding:24px 28px; opacity:0.6; text-align:center;'>"
            "<div style='font-size:14px; font-weight:600; margin-bottom:12px;'>Quick Guide</div>"
            "<div style='font-size:13px; color:var(--text-secondary); text-align:left; line-height:2;'>"
            "① 희망하는 매체를 카테고리에서 직접 선택하거나 검색<br>"
            "② 해당 상품 체크<br>"
            "③ 체크 완료된 파일 확인 후 다운로드 버튼 클릭!"
            "</div></div>",
            unsafe_allow_html=True,
        )
    else:
        # 매체 리스트 (매체명 | 구분선 | 상품 태그 가로 나열)
        st.markdown(
            "<style>"
            ".cg-list{border:0.5px solid var(--border);border-radius:8px;overflow:hidden;background:var(--surface-2);margin-bottom:12px;}"
            ".cg-row{display:flex;align-items:center;gap:12px;padding:10px 14px;border-bottom:0.5px solid var(--border);}"
            ".cg-row:last-child{border-bottom:none;}"
            ".cg-mname{font-size:13px;font-weight:500;color:var(--text-primary);min-width:80px;white-space:nowrap;}"
            ".cg-div{width:1px;height:20px;background:var(--border-strong);flex-shrink:0;}"
            ".cg-tags{display:flex;flex-wrap:wrap;gap:6px;}"
            ".cg-tag{display:inline-flex;align-items:center;gap:5px;padding:4px 10px;border-radius:20px;"
            "font-size:12px;border:0.5px solid var(--border);background:var(--surface-1);"
            "color:var(--text-secondary);cursor:pointer;white-space:nowrap;}"
            ".cg-tag-on{background:#0B0B0B;border-color:#0B0B0B;color:#fff;}"
            ".cg-tag-dim{opacity:0.35;cursor:not-allowed;}"
            "</style>",
            unsafe_allow_html=True,
        )

        st.markdown("<div class='cg-list'>", unsafe_allow_html=True)
        for media_name in filtered_names:
            products = guide_map.get(media_name, {})
            tags_html = ""
            for product_name in sorted(products.keys()):
                guide = products[product_name]
                has_file = bool(guide.get("storage_path"))
                key = (media_name, product_name)
                is_on = st.session_state["cg_selected"].get(key, False)
                if not has_file:
                    tags_html += f"<span class='cg-tag cg-tag-dim'>{product_name}</span>"
                elif is_on:
                    tags_html += f"<span class='cg-tag cg-tag-on'>✓ {product_name}</span>"
                else:
                    tags_html += f"<span class='cg-tag'>{product_name}</span>"

            st.markdown(
                f"<div class='cg-row'>"
                f"<span class='cg-mname'>{media_name}</span>"
                f"<div class='cg-div'></div>"
                f"<div class='cg-tags'>{tags_html}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

            # 각 상품별 숨겨진 체크박스 (태그 클릭 대신 expander 없이 상태 토글)
            if products:
                for product_name in sorted(products.keys()):
                    guide = products[product_name]
                    has_file = bool(guide.get("storage_path"))
                    if not has_file:
                        continue
                    key = (media_name, product_name)
                    checked = st.session_state["cg_selected"].get(key, False)
                    new_val = st.checkbox(
                        f"{media_name} · {product_name}",
                        value=checked,
                        key=f"cg_check_{media_name}_{product_name}",
                        label_visibility="collapsed",
                    )
                    if new_val != checked:
                        st.session_state["cg_selected"][key] = new_val
                        st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)

        # 선택 영역 (태그 스타일, 선택=블랙, 미선택=회색)
        selected = {k: v for k, v in st.session_state["cg_selected"].items() if v}
        if selected:
            st.markdown(
                "<style>"
                ".sel-tag{display:inline-flex;align-items:center;gap:6px;padding:6px 12px;"
                "border-radius:20px;font-size:12px;font-weight:500;border:0.5px solid #0B0B0B;"
                "background:#0B0B0B;color:#fff;margin:3px;}"
                "</style>",
                unsafe_allow_html=True,
            )
            tags_selected = "".join(
                f"<span class='sel-tag'>{mn} · {pn}</span>"
                for (mn, pn) in selected
            )
            st.markdown(
                f"<div style='margin:10px 0;'>{tags_selected}</div>",
                unsafe_allow_html=True,
            )
            # × 제거 버튼
            for (mn, pn) in list(selected.keys()):
                if st.button(f"× {mn} · {pn}", key=f"cg_remove_{mn}_{pn}"):
                    st.session_state["cg_selected"][(mn, pn)] = False
                    st.rerun()

            if st.button("선택한 제작가이드 통합 다운로드", type="primary", use_container_width=True):
                try:
                    import openpyxl
                    from copy import copy
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
                                    if cell.has_style:
                                        new_ws[cell.coordinate].font = copy(cell.font)
                                        new_ws[cell.coordinate].fill = copy(cell.fill)
                                        new_ws[cell.coordinate].border = copy(cell.border)
                                        new_ws[cell.coordinate].alignment = copy(cell.alignment)
                                        new_ws[cell.coordinate].number_format = cell.number_format
                            for col_dim in src_ws.column_dimensions.values():
                                new_ws.column_dimensions[col_dim.index].width = col_dim.width
                            for row_dim in src_ws.row_dimensions.values():
                                new_ws.row_dimensions[row_dim.index].height = row_dim.height
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

# ============================
# 업로드 탭
# ============================
with tab_up:
    media_options = sorted(set([m["name"] for m in all_media]))

    col_u1, col_u2 = st.columns([2, 2])
    with col_u1:
        upload_media = st.selectbox("매체 선택", media_options, key="cg_upload_media")
    with col_u2:
        upload_product = st.text_input("상품명", key="cg_upload_product")

    upload_file = st.file_uploader("엑셀 파일 업로드 (.xlsx)", type=["xlsx"], key="cg_upload_file")

    if st.button("저장", type="primary", key="cg_upload_btn"):
        if not upload_media or not upload_product or not upload_file:
            st.error("매체, 상품명, 파일을 모두 입력해주세요.")
        else:
            existing = guide_map.get(upload_media, {}).get(upload_product)
            storage_path = f"{uuid.uuid4()}.xlsx"
            file_bytes = upload_file.read()
            if existing:
                db.delete_from_storage(BUCKET, existing["storage_path"])
                db.upload_to_storage(BUCKET, storage_path, file_bytes)
                db.update_creative_guide(existing["id"], storage_path)
            else:
                db.upload_to_storage(BUCKET, storage_path, file_bytes)
                cat = media_cat_map.get(upload_media, "")
                db.create_creative_guide(upload_media, cat, upload_product, storage_path)
            st.success(f"'{upload_media} · {upload_product}' 저장 완료.")
            st.rerun()
