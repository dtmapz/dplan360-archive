import streamlit as st
from notion_client import Client
from st_click_detector import click_detector
from utils.auth import get_current_user
from utils.ui import set_current_page
from datetime import date

set_current_page("media_guide")

user = get_current_user()

# ============================
# Notion API 연결
# ============================
NOTION_TOKEN = st.secrets.get("NOTION_TOKEN", "")

if not NOTION_TOKEN:
    st.error("Notion API 토큰이 설정되지 않았습니다. Streamlit Secrets를 확인해주세요.")
    st.stop()

notion = Client(auth=NOTION_TOKEN)


# ============================
# Notion 유틸 함수
# ============================
@st.cache_data(ttl=600)
def get_hub_children():
    """워크스페이스에서 DPLAN360 허브를 찾고, 그 하위 매체 페이지 목록 반환"""
    # 1. Search로 최상위 페이지 중 허브 찾기
    resp = notion.search(filter={"property": "object", "value": "page"}, page_size=100)
    hub_id = None
    for page in resp["results"]:
        parent = page.get("parent", {})
        if parent.get("type") == "workspace":
            hub_id = page["id"]
            break
    if not hub_id:
        return []

    # 2. 허브 페이지의 블록 조회
    results = []
    cursor = None
    while True:
        resp = notion.blocks.children.list(block_id=hub_id, start_cursor=cursor, page_size=100)
        results.extend(resp["results"])
        if not resp["has_more"]:
            break
        cursor = resp["next_cursor"]

    # 3. child_page 추출 (직접 + column_list 내부)
    pages = []
    for block in results:
        if block["type"] == "child_page":
            pages.append({
                "id": block["id"],
                "title": block["child_page"]["title"],
            })
        elif block["type"] == "column_list" and block.get("has_children"):
            # column_list > column > child_page
            columns = notion.blocks.children.list(block_id=block["id"], page_size=100)["results"]
            for col in columns:
                if col["type"] == "column" and col.get("has_children"):
                    col_children = notion.blocks.children.list(block_id=col["id"], page_size=100)["results"]
                    for child in col_children:
                        if child["type"] == "child_page":
                            pages.append({
                                "id": child["id"],
                                "title": child["child_page"]["title"],
                            })
    return pages


@st.cache_data(ttl=600)
def get_sub_pages(page_id: str):
    """매체 페이지의 하위 가이드 페이지 목록"""
    results = []
    cursor = None
    while True:
        resp = notion.blocks.children.list(block_id=page_id, start_cursor=cursor, page_size=100)
        results.extend(resp["results"])
        if not resp["has_more"]:
            break
        cursor = resp["next_cursor"]
    pages = []
    for block in results:
        if block["type"] == "child_page":
            pages.append({
                "id": block["id"],
                "title": block["child_page"]["title"],
            })
    return pages


@st.cache_data(ttl=600)
def get_page_blocks(page_id: str):
    """페이지의 모든 블록 가져오기"""
    results = []
    cursor = None
    while True:
        resp = notion.blocks.children.list(block_id=page_id, start_cursor=cursor, page_size=100)
        results.extend(resp["results"])
        if not resp["has_more"]:
            break
        cursor = resp["next_cursor"]
    return results


def get_page_meta(page_id: str):
    """페이지 메타 정보 (제목, 최종 수정일)"""
    page = notion.pages.retrieve(page_id=page_id)
    last_edited = page.get("last_edited_time", "")[:10]
    return last_edited


# ============================
# 블록 렌더링
# ============================
def extract_rich_text(rich_text_list):
    """Notion rich_text 배열을 문자열로 변환"""
    text = ""
    for rt in rich_text_list:
        content = rt.get("plain_text", "")
        annotations = rt.get("annotations", {})
        if annotations.get("bold"):
            content = f"**{content}**"
        if annotations.get("italic"):
            content = f"*{content}*"
        if annotations.get("strikethrough"):
            content = f"~~{content}~~"
        if annotations.get("code"):
            content = f"`{content}`"
        if rt.get("href"):
            content = f"[{content}]({rt['href']})"
        text += content
    return text


def render_blocks(blocks):
    """블록 리스트를 Streamlit 위젯으로 렌더링"""
    for block in blocks:
        btype = block["type"]

        if btype == "heading_1":
            text = extract_rich_text(block["heading_1"].get("rich_text", []))
            st.markdown(f"## {text}")

        elif btype == "heading_2":
            text = extract_rich_text(block["heading_2"].get("rich_text", []))
            st.markdown(f"### {text}")

        elif btype == "heading_3":
            text = extract_rich_text(block["heading_3"].get("rich_text", []))
            st.markdown(f"#### {text}")

        elif btype == "paragraph":
            text = extract_rich_text(block["paragraph"].get("rich_text", []))
            if text:
                st.markdown(text)

        elif btype == "bulleted_list_item":
            text = extract_rich_text(block["bulleted_list_item"].get("rich_text", []))
            st.markdown(f"- {text}")

        elif btype == "numbered_list_item":
            text = extract_rich_text(block["numbered_list_item"].get("rich_text", []))
            st.markdown(f"1. {text}")

        elif btype == "to_do":
            text = extract_rich_text(block["to_do"].get("rich_text", []))
            checked = block["to_do"].get("checked", False)
            mark = "☑" if checked else "☐"
            st.markdown(f"{mark} {text}")

        elif btype == "toggle":
            text = extract_rich_text(block["toggle"].get("rich_text", []))
            with st.expander(text):
                if block.get("has_children"):
                    child_blocks = get_page_blocks(block["id"])
                    render_blocks(child_blocks)

        elif btype == "callout":
            text = extract_rich_text(block["callout"].get("rich_text", []))
            icon = block["callout"].get("icon", {})
            emoji = icon.get("emoji", "💡") if icon.get("type") == "emoji" else "💡"
            st.markdown(
                f"<div style='background:#FFF8E1;border-left:3px solid #F2A93B;"
                f"border-radius:6px;padding:12px 14px;font-size:14px;margin:8px 0;'>"
                f"{emoji} {text}</div>",
                unsafe_allow_html=True,
            )

        elif btype == "quote":
            text = extract_rich_text(block["quote"].get("rich_text", []))
            st.markdown(f"> {text}")

        elif btype == "code":
            text = extract_rich_text(block["code"].get("rich_text", []))
            lang = block["code"].get("language", "")
            st.code(text, language=lang)

        elif btype == "divider":
            st.divider()

        elif btype == "image":
            img = block["image"]
            if img["type"] == "file":
                url = img["file"]["url"]
            elif img["type"] == "external":
                url = img["external"]["url"]
            else:
                url = None
            if url:
                caption = extract_rich_text(img.get("caption", []))
                st.image(url, caption=caption if caption else None)

        elif btype == "table":
            if block.get("has_children"):
                table_rows = get_page_blocks(block["id"])
                if table_rows:
                    rows_data = []
                    for row_block in table_rows:
                        if row_block["type"] == "table_row":
                            cells = row_block["table_row"]["cells"]
                            row = [extract_rich_text(cell) for cell in cells]
                            rows_data.append(row)
                    if rows_data:
                        header = rows_data[0]
                        body = rows_data[1:]
                        table_html = "<table style='border-collapse:collapse;width:100%;font-size:13px;margin:8px 0;'>"
                        table_html += "<tr>" + "".join(
                            f"<th style='border:0.5px solid var(--border);padding:8px 12px;"
                            f"background:var(--surface-1);font-weight:600;text-align:left;'>{h}</th>"
                            for h in header
                        ) + "</tr>"
                        for row in body:
                            table_html += "<tr>" + "".join(
                                f"<td style='border:0.5px solid var(--border);padding:8px 12px;"
                                f"text-align:left;'>{c}</td>"
                                for c in row
                            ) + "</tr>"
                        table_html += "</table>"
                        st.markdown(table_html, unsafe_allow_html=True)

        elif btype == "bookmark":
            url = block["bookmark"].get("url", "")
            caption = extract_rich_text(block["bookmark"].get("caption", []))
            if url:
                st.markdown(f"🔗 [{caption or url}]({url})")

        elif btype == "embed":
            url = block["embed"].get("url", "")
            if url:
                st.markdown(f"🔗 [임베드 링크]({url})")

        # 미지원 블록은 조용히 스킵


# ============================
# 목차 생성
# ============================
def build_toc(blocks):
    """heading 블록에서 목차 추출"""
    toc = []
    for block in blocks:
        btype = block["type"]
        if btype in ("heading_1", "heading_2", "heading_3"):
            text = extract_rich_text(block[btype].get("rich_text", []))
            level = int(btype[-1])
            toc.append({"text": text, "level": level})
    return toc


# ============================
# 검색 기능
# ============================
@st.cache_data(ttl=600)
def search_all_guides(_media_pages):
    """모든 가이드 페이지의 텍스트를 수집 (검색용)"""
    all_text = []
    for media in _media_pages:
        sub_pages = get_sub_pages(media["id"])
        for guide in sub_pages:
            blocks = get_page_blocks(guide["id"])
            texts = []
            for b in blocks:
                btype = b["type"]
                if btype in ("paragraph", "heading_1", "heading_2", "heading_3",
                             "bulleted_list_item", "numbered_list_item", "callout", "quote"):
                    t = extract_rich_text(b[btype].get("rich_text", []))
                    if t:
                        texts.append(t)
            all_text.append({
                "media": media["title"],
                "guide": guide["title"],
                "guide_id": guide["id"],
                "media_id": media["id"],
                "content": "\n".join(texts),
            })
    return all_text


# ============================
# 메인 UI
# ============================
search_kw = st.text_input("", placeholder="🔍 전체 가이드 검색", label_visibility="collapsed", key="mg_search")

media_pages = get_hub_children()

if not media_pages:
    st.warning("허브 페이지에 하위 매체 페이지가 없습니다. Notion 구조를 확인해주세요.")
    st.stop()

# 검색 모드
if search_kw:
    all_guides = search_all_guides(tuple((m["id"], m["title"]) for m in media_pages))
    results = []
    for g in all_guides:
        if search_kw.lower() in g["content"].lower() or search_kw.lower() in g["guide"].lower():
            # 매칭된 줄 추출
            matched_lines = [
                line.strip() for line in g["content"].split("\n")
                if search_kw.lower() in line.lower()
            ][:3]
            results.append({**g, "matched": matched_lines})

    if results:
        st.markdown(f"**검색 결과** — '{search_kw}' ({len(results)}건)")
        for r in results:
            with st.expander(f"📄 {r['media']} > {r['guide']}"):
                for line in r["matched"]:
                    st.markdown(f"- ...{line}...")
                if st.button("이 가이드 열기", key=f"mg_open_{r['guide_id']}"):
                    st.session_state["mg_media"] = r["media_id"]
                    st.session_state["mg_guide"] = r["guide_id"]
                    st.session_state["mg_search_clear"] = True
                    st.rerun()
    else:
        st.info(f"'{search_kw}'에 대한 검색 결과가 없습니다.")

else:
    # 매체 + 가이드 칩을 하나의 click_detector로 통합
    selected_media_id = st.session_state.get("mg_media")
    selected_guide_id = st.session_state.get("mg_guide")

    # 매체 칩 HTML
    media_chips = []
    for m in media_pages:
        is_active = (m["id"] == selected_media_id)
        if is_active:
            media_chips.append(
                f"<a href='#' id='media__{m['id']}' style='text-decoration:none;'>"
                f"<span style='padding:6px 14px;font-size:13px;border-radius:8px;"
                f"background:#111;color:#fff;cursor:pointer;display:inline-block;'>{m['title']}</span></a>"
            )
        else:
            media_chips.append(
                f"<a href='#' id='media__{m['id']}' style='text-decoration:none;color:#111;'>"
                f"<span style='padding:6px 14px;font-size:13px;border-radius:8px;"
                f"box-shadow:0 0 0 0.5px #999 inset;"
                f"color:#111;cursor:pointer;display:inline-block;'>{m['title']}</span></a>"
            )

    combined_html = "<div style='display:flex;flex-wrap:wrap;gap:8px;margin-bottom:8px;'>" + "".join(media_chips) + "</div>"

    # 가이드 칩 HTML (매체 선택 시만)
    sub_pages = []
    if selected_media_id:
        sub_pages = get_sub_pages(selected_media_id)
        if sub_pages:
            guide_chips = []
            for sp in sub_pages:
                is_active = (sp["id"] == selected_guide_id)
                if is_active:
                    guide_chips.append(
                        f"<a href='#' id='guide__{sp['id']}' style='text-decoration:none;'>"
                        f"<span style='padding:5px 12px;font-size:12px;border-radius:6px;"
                        f"background:#F2A93B;color:#fff;cursor:pointer;display:inline-block;'>{sp['title']}</span></a>"
                    )
                else:
                    guide_chips.append(
                        f"<a href='#' id='guide__{sp['id']}' style='text-decoration:none;color:#111;'>"
                        f"<span style='padding:5px 12px;font-size:12px;border-radius:6px;"
                        f"box-shadow:0 0 0 0.5px #999 inset;"
                        f"color:#111;cursor:pointer;display:inline-block;'>{sp['title']}</span></a>"
                    )
            combined_html += "<div style='display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px;'>" + "".join(guide_chips) + "</div>"
        else:
            st.session_state["mg_guide"] = selected_media_id

    # 통합 click_detector
    clicked = click_detector(combined_html, key="mg_chip_det")
    if clicked:
        if clicked.startswith("media__"):
            clicked_id = clicked.replace("media__", "")
            if clicked_id != st.session_state.get("mg_media"):
                st.session_state["mg_media"] = clicked_id
                st.session_state.pop("mg_guide", None)
                st.rerun()
        elif clicked.startswith("guide__"):
            clicked_id = clicked.replace("guide__", "")
            if clicked_id != st.session_state.get("mg_guide"):
                st.session_state["mg_guide"] = clicked_id
                st.rerun()

    # 가이드 본문 렌더링
    if "mg_guide" in st.session_state:
        guide_id = st.session_state["mg_guide"]

        # 제목 + 메타
        page_meta = get_page_meta(guide_id)
        guide_title = ""
        if "mg_media" in st.session_state:
            sub_pages = get_sub_pages(st.session_state["mg_media"])
            for sp in sub_pages:
                if sp["id"] == guide_id:
                    guide_title = sp["title"]
                    break
        if not guide_title:
            for m in media_pages:
                if m["id"] == guide_id:
                    guide_title = m["title"]
                    break

        # 블록 가져오기
        blocks = get_page_blocks(guide_id)

        # --- PDF용 HTML 생성 함수 ---
        def blocks_to_html(blocks, title, meta_date):
            """블록 리스트를 PDF용 HTML 문자열로 변환"""
            html_out = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
            <style>
            body {{ font-family: 'Noto Sans KR', sans-serif; font-size: 12px; line-height: 1.7; color: #222; padding: 40px; }}
            h1 {{ font-size: 20px; font-weight: 700; margin-bottom: 4px; }}
            .meta {{ font-size: 10px; color: #888; margin-bottom: 20px; padding-bottom: 8px; border-bottom: 1px solid #eee; }}
            h2 {{ font-size: 15px; font-weight: 600; margin: 18px 0 6px; }}
            h3 {{ font-size: 13px; font-weight: 600; margin: 14px 0 4px; }}
            h4 {{ font-size: 12px; font-weight: 600; margin: 12px 0 4px; }}
            p {{ margin-bottom: 6px; }}
            ul, ol {{ margin-left: 18px; margin-bottom: 6px; }}
            .callout {{ background: #FFF8E1; border-left: 3px solid #F2A93B; padding: 8px 12px; margin: 8px 0; border-radius: 4px; }}
            blockquote {{ border-left: 3px solid #ddd; padding-left: 12px; color: #555; margin: 8px 0; }}
            table {{ border-collapse: collapse; width: 100%; margin: 10px 0; }}
            th, td {{ border: 1px solid #ddd; padding: 6px 10px; text-align: left; font-size: 11px; }}
            th {{ background: #f5f5f5; font-weight: 600; }}
            code {{ background: #f4f4f4; padding: 1px 4px; border-radius: 2px; font-size: 11px; }}
            pre {{ background: #f4f4f4; padding: 10px; border-radius: 4px; overflow-x: auto; }}
            img {{ max-width: 100%; height: auto; margin: 8px 0; }}
            </style></head><body>
            <h1>{title}</h1>
            <div class="meta">D-PLAN360 ARCHIVE · 출력일 {date.today().isoformat()}</div>
            """
            for block in blocks:
                btype = block["type"]
                if btype == "heading_1":
                    text = extract_rich_text(block["heading_1"].get("rich_text", []))
                    html_out += f"<h2>{text}</h2>"
                elif btype == "heading_2":
                    text = extract_rich_text(block["heading_2"].get("rich_text", []))
                    html_out += f"<h3>{text}</h3>"
                elif btype == "heading_3":
                    text = extract_rich_text(block["heading_3"].get("rich_text", []))
                    html_out += f"<h4>{text}</h4>"
                elif btype == "paragraph":
                    text = extract_rich_text(block["paragraph"].get("rich_text", []))
                    if text:
                        html_out += f"<p>{text}</p>"
                elif btype == "bulleted_list_item":
                    text = extract_rich_text(block["bulleted_list_item"].get("rich_text", []))
                    html_out += f"<ul><li>{text}</li></ul>"
                elif btype == "numbered_list_item":
                    text = extract_rich_text(block["numbered_list_item"].get("rich_text", []))
                    html_out += f"<ol><li>{text}</li></ol>"
                elif btype == "callout":
                    text = extract_rich_text(block["callout"].get("rich_text", []))
                    icon = block["callout"].get("icon", {})
                    emoji = icon.get("emoji", "💡") if icon.get("type") == "emoji" else "💡"
                    html_out += f"<div class='callout'>{emoji} {text}</div>"
                elif btype == "quote":
                    text = extract_rich_text(block["quote"].get("rich_text", []))
                    html_out += f"<blockquote>{text}</blockquote>"
                elif btype == "code":
                    text = extract_rich_text(block["code"].get("rich_text", []))
                    html_out += f"<pre><code>{text}</code></pre>"
                elif btype == "divider":
                    html_out += "<hr>"
                elif btype == "image":
                    img = block["image"]
                    url = ""
                    if img["type"] == "file":
                        url = img["file"]["url"]
                    elif img["type"] == "external":
                        url = img["external"]["url"]
                    if url:
                        caption = extract_rich_text(img.get("caption", []))
                        html_out += f"<img src='{url}'>"
                        if caption:
                            html_out += f"<p style='font-size:10px;color:#888;'>{caption}</p>"
                elif btype == "table":
                    if block.get("has_children"):
                        table_rows = get_page_blocks(block["id"])
                        if table_rows:
                            html_out += "<table>"
                            for ri, row_block in enumerate(table_rows):
                                if row_block["type"] == "table_row":
                                    cells = row_block["table_row"]["cells"]
                                    tag = "th" if ri == 0 else "td"
                                    html_out += "<tr>" + "".join(
                                        f"<{tag}>{extract_rich_text(cell)}</{tag}>" for cell in cells
                                    ) + "</tr>"
                            html_out += "</table>"
            html_out += "</body></html>"
            return html_out

        # --- 제목 행 + PDF 버튼 ---
        st.markdown(f"<div style='font-size:20px;font-weight:700;margin-bottom:4px;'>{guide_title}</div>",
                    unsafe_allow_html=True)

        st.markdown(f"<div style='font-size:11px;color:var(--text-muted);margin-bottom:14px;"
                    f"padding-bottom:10px;border-bottom:0.5px solid var(--border);'>"
                    f"Notion 자동 연동 · 최종 수정 {page_meta}</div>",
                    unsafe_allow_html=True)

        # PDF 생성 + 다운로드
        @st.fragment
        def pdf_download_section():
            try:
                from fpdf import FPDF
                import os
                pdf = FPDF()
                pdf.add_page()
                font_path = os.path.join(os.path.dirname(__file__), "assets", "NotoSansKR-Regular.ttf")
                if os.path.exists(font_path):
                    pdf.add_font("NotoSansKR", "", font_path, uni=True)
                    pdf.set_font("NotoSansKR", size=10)
                else:
                    pdf.set_font("Helvetica", size=10)
                pdf.cell(0, 10, guide_title, ln=True)
                pdf.ln(4)
                for block in blocks:
                    btype = block["type"]
                    if btype in ("heading_1", "heading_2", "heading_3"):
                        text = extract_rich_text(block[btype].get("rich_text", []))
                        pdf.set_font(size=13 if btype == "heading_1" else 11)
                        pdf.cell(0, 8, text, ln=True)
                        pdf.set_font(size=10)
                    elif btype in ("paragraph", "bulleted_list_item", "numbered_list_item", "callout", "quote"):
                        text = extract_rich_text(block[btype].get("rich_text", []))
                        if text:
                            prefix = "• " if btype == "bulleted_list_item" else ""
                            pdf.multi_cell(0, 5, prefix + text)
                            pdf.ln(2)
                pdf_bytes = pdf.output()

                st.download_button(
                    "📄 PDF 다운로드",
                    data=pdf_bytes,
                    file_name=f"{guide_title}.pdf",
                    mime="application/pdf",
                    type="primary",
                )
            except Exception as e:
                st.error(f"PDF 생성 오류: {e}")

        pdf_download_section()

        # 목차
        toc = build_toc(blocks)
        if toc:
            toc_html = ("<div style='background:#FFF8E1;border:0.5px solid #F2A93B44;"
                        "border-radius:8px;padding:12px 16px;margin-bottom:18px;'>"
                        "<div style='font-size:11px;font-weight:700;color:#8A6D1F;margin-bottom:6px;'>📑 목차</div>")
            for item in toc:
                indent = (item["level"] - 1) * 14
                toc_html += f"<div style='font-size:12px;padding:2px 0 2px {indent}px;color:var(--text-primary);'>{item['text']}</div>"
            toc_html += "</div>"
            st.markdown(toc_html, unsafe_allow_html=True)

        # 본문 렌더링 (90% 스케일)
        st.markdown("<div style='font-size:90%;'>", unsafe_allow_html=True)
        render_blocks(blocks)
        st.markdown("</div>", unsafe_allow_html=True)

        # 하단 안내
        st.markdown(
            "<div style='font-size:10px;color:var(--text-muted);text-align:right;"
            "margin-top:18px;padding-top:10px;border-top:0.5px solid var(--border);'>"
            "🔄 Notion 수정 시 최대 10분 내 자동 반영</div>",
            unsafe_allow_html=True,
        )
