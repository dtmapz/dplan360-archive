import streamlit as st
import io
from utils import db
from utils.auth import get_current_user
from utils.ui import set_current_page
import uuid

set_current_page("creative_guide")

user = get_current_user()
BUCKET = "creative-guides"

guides = db.get_creative_guides()
all_media = db.get_all_media()

media_cat_map = {}
for m in all_media:
    cat = m.get("categories") or {}
    media_cat_map[m["name"]] = cat.get("major_category", "")

guide_map = {}
for g in guides:
    guide_map.setdefault(g["media_name"], {})[g["product_name"]] = g

tab_dl, tab_up = st.tabs(["제작가이드 다운로드", "업로드"])

# ============================
# 다운로드 탭
# ============================
with tab_dl:
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
        st.markdown("<div style='text-align:center;color:var(--text-muted);font-size:12px;padding-top:8px;'>또는</div>",
                    unsafe_allow_html=True)
    with col_f3:
        search_kw = st.text_input("검색", placeholder="🔍 매체명 직접 검색",
                                   label_visibility="collapsed", key="cg_search")

    any_filter = bool(major_filter or search_kw)
    all_media_names = sorted(set([m["name"] for m in all_media] + list(guide_map.keys())))

    def passes_filter(name: str) -> bool:
        if search_kw and search_kw.lower() not in name.lower():
            return False
        if major_filter and media_cat_map.get(name, "") != major_filter:
            return False
        return True

    filtered_names = [n for n in all_media_names if passes_filter(n)] if any_filter else []

    if "cg_selected" not in st.session_state:
        st.session_state["cg_selected"] = {}

    # query_params로 버튼 클릭 처리
    params = st.query_params
    if "cg_toggle" in params:
        raw = params["cg_toggle"]
        if "||" in raw:
            mn, pn = raw.split("||", 1)
            key = (mn, pn)
            st.session_state["cg_selected"][key] = not st.session_state["cg_selected"].get(key, False)
        st.query_params.clear()
        st.rerun()

    if not any_filter:
        st.markdown(
            "<div style='margin:40px auto;max-width:480px;background:rgba(0,0,0,0.04);"
            "border-radius:12px;padding:24px 28px;opacity:0.6;text-align:center;'>"
            "<div style='font-size:14px;font-weight:600;margin-bottom:12px;'>Quick Guide</div>"
            "<div style='font-size:13px;color:var(--text-secondary);text-align:center;line-height:2;'>"
            "① 희망하는 매체를 카테고리에서 직접 선택하거나 검색<br>"
            "② 해당 상품 체크<br>"
            "③ 체크 완료된 파일 확인 후 다운로드 버튼 클릭!"
            "</div></div>",
            unsafe_allow_html=True,
        )
    else:
        for media_name in filtered_names:
            products = guide_map.get(media_name, {})
            if not products:
                continue
            has_any_file = any(bool(g.get("storage_path")) for g in products.values())
            if not has_any_file:
                continue

            col_m, col_div, col_p = st.columns([1, 0.05, 5])
            col_m.markdown(
                f"<div style='font-size:13px;font-weight:500;padding:10px 0;'>{media_name}</div>",
                unsafe_allow_html=True,
            )
            col_div.markdown(
                "<div style='width:1px;height:40px;background:var(--border-strong);margin:4px auto;'></div>",
                unsafe_allow_html=True,
            )
            with col_p:
                btn_parts = []
                for product_name, guide in sorted(products.items()):
                    has_file = bool(guide.get("storage_path"))
                    key = (media_name, product_name)
                    is_on = st.session_state["cg_selected"].get(key, False)
                    label = f"✓ {product_name}" if is_on else product_name
                    encoded = f"{media_name}||{product_name}"

                    if not has_file:
                        btn_parts.append(
                            f"<span style='padding:6px 14px;font-size:13px;border-radius:8px;"
                            f"box-shadow:0 0 0 0.5px #ccc inset;"
                            f"color:#bbb;cursor:not-allowed;display:inline-block;'>{product_name}</span>"
                        )
                    elif is_on:
                        btn_parts.append(
                            f"<a href='?cg_toggle={encoded}' style='text-decoration:none;'>"
                            f"<span style='padding:6px 14px;font-size:13px;border-radius:8px;"
                            f"background:#111;color:#fff;cursor:pointer;display:inline-block;'>{label}</span></a>"
                        )
                    else:
                        btn_parts.append(
                            f"<a href='?cg_toggle={encoded}' style='text-decoration:none;'>"
                            f"<span style='padding:6px 14px;font-size:13px;border-radius:8px;"
                            f"box-shadow:0 0 0 0.5px #999 inset;"
                            f"color:var(--text-primary);cursor:pointer;display:inline-block;'>{product_name}</span></a>"
                        )

                st.markdown(
                    f"<div style='display:flex;flex-wrap:wrap;gap:8px;padding:6px 0;'>"
                    + "".join(btn_parts) +
                    "</div>",
                    unsafe_allow_html=True,
                )

            st.markdown(
                "<div style='border-bottom:0.5px solid var(--border);margin:4px 0 8px 0;'></div>",
                unsafe_allow_html=True,
            )

        # 선택 태그 + 다운로드 버튼
        selected = {k: v for k, v in st.session_state["cg_selected"].items() if v}
        if selected:
            tag_html = "".join(
                f"<span style='font-size:12px;padding:4px 10px;border-radius:20px;"
                f"box-shadow:0 0 0 0.5px #999 inset;"
                f"display:inline-block;margin:3px;'>"
                f"{mn} · {pn}</span>"
                for (mn, pn) in selected
            )
            st.markdown(
                f"<div style='margin-top:16px;margin-bottom:8px;'>{tag_html}</div>",
                unsafe_allow_html=True,
            )
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
        if not upload_media or not upload_product:
            st.error("매체와 상품명을 입력해주세요.")
        else:
            existing = guide_map.get(upload_media, {}).get(upload_product)
            if upload_file:
                file_bytes = upload_file.read()
                storage_path = f"{uuid.uuid4()}.xlsx"
                if existing:
                    if existing.get("storage_path"):
                        db.delete_from_storage(BUCKET, existing["storage_path"])
                    db.upload_to_storage(BUCKET, storage_path, file_bytes)
                    db.update_creative_guide(existing["id"], storage_path)
                else:
                    db.upload_to_storage(BUCKET, storage_path, file_bytes)
                    cat = media_cat_map.get(upload_media, "")
                    db.create_creative_guide(upload_media, cat, upload_product, storage_path)
            else:
                if not existing:
                    cat = media_cat_map.get(upload_media, "")
                    db.create_creative_guide(upload_media, cat, upload_product, None)
                # 이미 존재하면 파일 없이 저장 시 아무 변경 없음 (파일만 덮어쓰기 가능)
            st.session_state["_cg_upload_success"] = f"'{upload_media} · {upload_product}' 저장 완료."
            st.rerun()

    msg = st.session_state.pop("_cg_upload_success", None)
    if msg:
        st.success(msg)
