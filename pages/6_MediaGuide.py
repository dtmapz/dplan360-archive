import streamlit as st
from notion_client import Client
from st_click_detector import click_detector
from utils.auth import get_current_user
from utils.ui import set_current_page

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
    resp = notion.search(filter={"property": "object", "value": "page"}, page_size=100)
    hub_id = None
    for page in resp["results"]:
        parent = page.get("parent", {})
        if parent.get("type") == "workspace":
            hub_id = page["id"]
            break
    if not hub_id:
        return []

    results = []
    cursor = None
    while True:
        resp = notion.blocks.children.list(block_id=hub_id, start_cursor=cursor, page_size=100)
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
        elif block["type"] == "column_list" and block.get("has_children"):
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
    """페이지 메타 정보"""
    page = notion.pages.retrieve(page_id=page_id)
    last_edited = page.get("last_edited_time", "")[:10]
    return last_edited


# ============================
# 블록 렌더링
# ============================
def extract_rich_text(rich_text_list):
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


# ============================
# 목차 생성
# ============================
def build_toc(blocks):
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
    all_text = []
    for media_frozen in _media_pages:
        media = dict(media_frozen)
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
    all_guides = search_all_guides(tuple(frozenset(m.items()) for m in media_pages))
    results = []
    for g in all_guides:
        if search_kw.lower() in g["content"].lower() or search_kw.lower() in g["guide"].lower():
            results.append(g)

    if results:
        st.markdown(f"**검색 결과** — '{search_kw}' ({len(results)}건)")

        selected_search_id = st.session_state.get("mg_search_selected")

        result_chips = []
        for r in results:
            label = f"{r['media']} · {r['guide']}"
            is_active = (r["guide_id"] == selected_search_id)
            if is_active:
                result_chips.append(
                    f"<a href='#' id='search__{r['guide_id']}' style='text-decoration:none;'>"
                    f"<span style='padding:6px 14px;font-size:13px;border-radius:8px;"
                    f"background:#F2A93B;color:#fff;cursor:pointer;display:inline-block;'>✓ {label}</span></a>"
                )
            else:
                result_chips.append(
                    f"<a href='#' id='search__{r['guide_id']}' style='text-decoration:none;color:#111;'>"
                    f"<span style='padding:6px 14px;font-size:13px;border-radius:8px;"
                    f"box-shadow:0 0 0 0.5px #999 inset;"
                    f"color:#111;cursor:pointer;display:inline-block;'>{label}</span></a>"
                )
        search_html = "<div style='display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px;'>" + "".join(result_chips) + "</div>"
        clicked = click_detector(search_html, key="mg_search_det")
        if clicked and clicked.startswith("search__"):
            clicked_id = clicked.replace("search__", "")
            if clicked_id != st.session_state.get("mg_search_selected"):
                st.session_state["mg_search_selected"] = clicked_id
                st.rerun()

        # 선택된 가이드 본문 렌더링
        if selected_search_id:
            selected_guide = next((r for r in results if r["guide_id"] == selected_search_id), None)
            if selected_guide:
                page_meta = get_page_meta(selected_search_id)
                st.markdown(f"<div style='font-size:20px;font-weight:700;margin-bottom:4px;'>{selected_guide['guide']}</div>",
                            unsafe_allow_html=True)
                st.markdown(f"<div style='font-size:11px;color:var(--text-muted);margin-bottom:14px;"
                            f"padding-bottom:10px;border-bottom:0.5px solid var(--border);'>"
                            f"{selected_guide['media']} · Notion 자동 연동 · 최종 수정 {page_meta}</div>",
                            unsafe_allow_html=True)

                blocks = get_page_blocks(selected_search_id)

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

                st.markdown("<div style='font-size:90%;'>", unsafe_allow_html=True)
                render_blocks(blocks)
                st.markdown("</div>", unsafe_allow_html=True)
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

    combined_html = "<div style='display:flex;flex-wrap:wrap;gap:8px;margin-bottom:4px;'>" + "".join(media_chips) + "</div>"

    # 가이드 칩 HTML
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
            combined_html += "<div style='border-top:0.5px solid #ddd;margin:8px 0;'></div>"
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

        st.markdown(f"<div style='font-size:20px;font-weight:700;margin-bottom:8px;'>{guide_title}</div>",
                    unsafe_allow_html=True)
        st.markdown(f"<div style='font-size:11px;color:var(--text-muted);margin-bottom:14px;"
                    f"padding-bottom:10px;border-bottom:0.5px solid var(--border);'>"
                    f"Notion 자동 연동 · 최종 수정 {page_meta}</div>",
                    unsafe_allow_html=True)

        blocks = get_page_blocks(guide_id)

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

        st.markdown("<div style='font-size:90%;'>", unsafe_allow_html=True)
        render_blocks(blocks)
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown(
            "<div style='font-size:10px;color:var(--text-muted);text-align:right;"
            "margin-top:18px;padding-top:10px;border-top:0.5px solid var(--border);'>"
            "🔄 Notion 수정 시 최대 10분 내 자동 반영</div>",
            unsafe_allow_html=True,
        )
