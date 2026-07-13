import streamlit as st
from notion_client import Client
from utils.auth import get_current_user
from utils.ui import set_current_page

set_current_page("media_guide")

user = get_current_user()

# ============================
# Notion API 연결
# ============================
NOTION_TOKEN = st.secrets.get("NOTION_TOKEN", "")
HUB_PAGE_ID = st.secrets.get("NOTION_HUB_PAGE_ID", "")

if not NOTION_TOKEN or not HUB_PAGE_ID:
    st.error("Notion API 토큰 또는 허브 페이지 ID가 설정되지 않았습니다. Streamlit Secrets를 확인해주세요.")
    st.stop()

notion = Client(auth=NOTION_TOKEN)


# ============================
# Notion 유틸 함수
# ============================
@st.cache_data(ttl=600)
def get_hub_children():
    """허브 페이지의 하위 페이지 목록 (매체별 그룹)"""
    results = []
    cursor = None
    while True:
        resp = notion.blocks.children.list(block_id=HUB_PAGE_ID, start_cursor=cursor, page_size=100)
        results.extend(resp["results"])
        if not resp["has_more"]:
            break
        cursor = resp["next_cursor"]
    # child_page 블록만 필터
    pages = []
    for block in results:
        if block["type"] == "child_page":
            pages.append({
                "id": block["id"],
                "title": block["child_page"]["title"],
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
    # 매체 선택 (칩)
    media_names = [m["title"] for m in media_pages]
    selected_media_idx = None

    if "mg_media" in st.session_state:
        for i, m in enumerate(media_pages):
            if m["id"] == st.session_state["mg_media"]:
                selected_media_idx = i
                break

    cols = st.columns(min(len(media_names), 8))
    for i, name in enumerate(media_names):
        with cols[i % 8]:
            is_active = (selected_media_idx == i)
            btn_type = "primary" if is_active else "secondary"
            if st.button(name, key=f"mg_media_{i}", type=btn_type):
                st.session_state["mg_media"] = media_pages[i]["id"]
                st.session_state.pop("mg_guide", None)
                st.rerun()

    # 하위 가이드 선택 (칩)
    if "mg_media" in st.session_state:
        selected_media_id = st.session_state["mg_media"]
        sub_pages = get_sub_pages(selected_media_id)

        if sub_pages:
            media_title = next((m["title"] for m in media_pages if m["id"] == selected_media_id), "")
            st.markdown(f"<div style='font-size:12px;color:var(--text-muted);margin:8px 0 4px;'>{media_title} 가이드 ↓</div>",
                        unsafe_allow_html=True)

            sub_cols = st.columns(min(len(sub_pages), 8))
            selected_guide_idx = None
            if "mg_guide" in st.session_state:
                for i, s in enumerate(sub_pages):
                    if s["id"] == st.session_state["mg_guide"]:
                        selected_guide_idx = i
                        break

            for i, sp in enumerate(sub_pages):
                with sub_cols[i % 8]:
                    is_active = (selected_guide_idx == i)
                    btn_type = "primary" if is_active else "secondary"
                    if st.button(sp["title"], key=f"mg_guide_{i}", type=btn_type):
                        st.session_state["mg_guide"] = sp["id"]
                        st.rerun()
        else:
            # 하위 가이드가 없으면 매체 페이지 자체를 바로 표시
            st.session_state["mg_guide"] = selected_media_id

    # 가이드 본문 렌더링
    if "mg_guide" in st.session_state:
        guide_id = st.session_state["mg_guide"]

        # 제목 + 메타
        page_meta = get_page_meta(guide_id)
        # 제목은 sub_pages 또는 media_pages에서 가져오기
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

        st.markdown(f"<div style='font-size:22px;font-weight:700;margin-bottom:4px;'>{guide_title}</div>",
                    unsafe_allow_html=True)
        st.markdown(f"<div style='font-size:12px;color:var(--text-muted);margin-bottom:16px;"
                    f"padding-bottom:12px;border-bottom:0.5px solid var(--border);'>"
                    f"Notion 자동 연동 · 최종 수정 {page_meta}</div>",
                    unsafe_allow_html=True)

        # 블록 가져오기
        blocks = get_page_blocks(guide_id)

        # 목차
        toc = build_toc(blocks)
        if toc:
            toc_html = ("<div style='background:#FFF8E1;border:0.5px solid #F2A93B44;"
                        "border-radius:8px;padding:14px 18px;margin-bottom:20px;'>"
                        "<div style='font-size:12px;font-weight:700;color:#8A6D1F;margin-bottom:8px;'>📑 목차</div>")
            for item in toc:
                indent = (item["level"] - 1) * 16
                toc_html += f"<div style='font-size:13px;padding:2px 0 2px {indent}px;color:var(--text-primary);'>{item['text']}</div>"
            toc_html += "</div>"
            st.markdown(toc_html, unsafe_allow_html=True)

        # 본문 렌더링
        render_blocks(blocks)

        # 하단 안내
        st.markdown(
            "<div style='font-size:11px;color:var(--text-muted);text-align:right;"
            "margin-top:20px;padding-top:12px;border-top:0.5px solid var(--border);'>"
            "🔄 Notion 수정 시 최대 10분 내 자동 반영</div>",
            unsafe_allow_html=True,
        )
