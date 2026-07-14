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
# Gemini API 연결
# ============================
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", "")
SHEET_ID = st.secrets.get("BIGQUERY_MAPPING_SHEET_ID", "")
AI_LINKS_SHEET_NAME = "ai_reference_links"


@st.cache_data(ttl=300)
def load_reference_links():
    """시트에서 관리자 등록 링크 목록 조회"""
    try:
        from google.oauth2 import service_account
        import gspread

        creds = service_account.Credentials.from_service_account_info(
            dict(st.secrets["gcp_service_account"]),
            scopes=[
                "https://www.googleapis.com/auth/spreadsheets.readonly",
                "https://www.googleapis.com/auth/drive.readonly",
            ],
        )
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(SHEET_ID)
        ws = sh.worksheet(AI_LINKS_SHEET_NAME)
        rows = ws.get_all_records()
        # 빈 링크 제외
        return [
            {"media": str(r.get("매체", "")).strip(),
             "url": str(r.get("링크", "")).strip(),
             "title": str(r.get("제목", "")).strip()}
            for r in rows
            if str(r.get("링크", "")).strip()
        ]
    except Exception as e:
        return []


@st.cache_data(ttl=86400)
def fetch_gitbook_llms_txt(base_url):
    """GitBook의 llms.txt에서 하위 페이지 링크 목록 조회"""
    try:
        import requests
        # base_url에서 도메인 부분 추출
        from urllib.parse import urlparse
        parsed = urlparse(base_url)
        llms_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}/llms.txt"
        resp = requests.get(llms_url, timeout=10)
        if resp.status_code != 200:
            return []
        # llms.txt에서 URL 추출
        import re
        urls = re.findall(r'https?://[^\s\)]+\.md', resp.text)
        return list(set(urls))[:50]  # 최대 50개
    except Exception:
        return []


@st.cache_data(ttl=86400)
def fetch_link_content(url):
    """링크 fetch → 텍스트 반환 (24시간 캐시)"""
    try:
        import requests
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
        }
        resp = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        resp.raise_for_status()

        # GitBook은 .md 붙이면 마크다운 반환
        if "gitbook.io" in url and not url.endswith(".md"):
            try:
                md_url = url.rstrip("/") + ".md"
                md_resp = requests.get(md_url, headers=headers, timeout=15)
                if md_resp.status_code == 200 and len(md_resp.text) > 100:
                    return md_resp.text[:8000]
            except Exception:
                pass

        # BeautifulSoup 사용
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)
            return text[:8000] if text else f"⚠️ 빈 텍스트 (HTML {len(resp.text)}자)"
        except ImportError:
            import re
            text = re.sub(r"<script[^>]*>.*?</script>", "", resp.text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text).strip()
            return text[:8000] if text else f"⚠️ 빈 텍스트"
    except Exception as e:
        return f"⚠️ fetch 실패: {type(e).__name__}: {str(e)[:200]}"


def fetch_gitbook_with_search(base_url, question):
    """GitBook의 ?ask= 파라미터로 AI 질의 (하위 문서 전체 검색)"""
    try:
        import requests
        from urllib.parse import quote
        # GitBook의 master.md에 ?ask= 붙여서 AI 질의
        parsed_url = base_url.rstrip("/")
        # 이미 .md면 그대로, 아니면 /master.md 또는 llms.txt에서 가져온 형태로
        if not parsed_url.endswith(".md"):
            # GitBook 루트 문서 규칙
            if "/main" in parsed_url or "/guide" in parsed_url or "/business.daangn" in parsed_url:
                ask_url = f"{parsed_url}.md" if parsed_url.count("/") > 3 else f"{parsed_url}/master.md"
            else:
                ask_url = f"{parsed_url}/master.md"
        else:
            ask_url = parsed_url

        ask_url = f"{ask_url}?ask={quote(question)}"
        resp = requests.get(ask_url, timeout=20)
        if resp.status_code == 200 and len(resp.text) > 100:
            return resp.text[:8000]
        return ""
    except Exception:
        return ""


def find_relevant_guides(question, all_guides):
    """질문 키워드와 매칭되는 노션 가이드 찾기"""
    q_lower = question.lower()
    q_words = set(w for w in q_lower.split() if len(w) >= 2)

    scored = []
    for g in all_guides:
        content_lower = g["content"].lower()
        guide_lower = g["guide"].lower()
        media_lower = g["media"].lower()

        score = 0
        for word in q_words:
            if word in guide_lower:
                score += 3
            if word in media_lower:
                score += 2
            if word in content_lower:
                score += 1

        if score > 0:
            scored.append((score, g))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [g for _, g in scored]


def find_relevant_links(question, links):
    """질문 매체 매칭 → 해당 매체 링크만 반환"""
    q_lower = question.lower()

    # 시트에 등록된 매체 목록
    all_media = set(l.get("media", "").strip() for l in links if l.get("media"))
    matched_media = [m for m in all_media if m and m.lower() in q_lower]

    # 매체 감지되면 해당 매체 링크만
    if matched_media:
        return [l for l in links if l.get("media", "").strip() in matched_media]

    # 매체 미감지 → 빈 리스트 (2단계 스킵 → 3단계 웹검색)
    return []


def get_gemini_response(question, notion_context, link_context, use_web_search=False):
    """Gemini API 호출 → 답변 반환 (3단계 fallback)"""
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return "❌ google-genai 패키지가 설치되지 않았습니다."

    if not GEMINI_API_KEY:
        return "❌ Gemini API 키가 설정되지 않았습니다."

    client = genai.Client(api_key=GEMINI_API_KEY)

    context_parts = []
    if notion_context:
        context_parts.append(f"[Notion 가이드]\n{notion_context}")
    if link_context:
        context_parts.append(f"[관리자 등록 링크 콘텐츠]\n{link_context}")

    context_str = "\n\n---\n\n".join(context_parts) if context_parts else "(참고 자료 없음)"

    prompt = f"""당신은 D-PLAN360의 매체 가이드 도우미입니다. 아래 참고 자료를 바탕으로 사용자 질문에 답변하세요.

규칙:
- 참고 자료에 있는 내용만 답변하세요
- 참고 자료에 답이 없으면 "해당 자료에는 없습니다."라고 답하세요
- 답변은 한국어로 명확하고 간결하게 작성하세요
- 필요 시 단계별로 정리하세요

[참고 자료]
{context_str}

[질문]
{question}
"""

    try:
        config = None
        if use_web_search:
            config = types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())]
            )
        response = client.models.generate_content(
            model="gemini-flash-latest",
            contents=prompt,
            config=config,
        )
        return response.text if response.text else "답변을 생성할 수 없습니다."
    except Exception as e:
        return f"❌ AI 응답 오류: {e}"


def is_answer_insufficient(answer):
    """답변이 부족한지 판단"""
    insufficient_phrases = [
        "해당 자료에는 없습니다",
        "해당 가이드에는 없습니다",
        "정보가 없습니다",
        "확인할 수 없습니다",
        "찾을 수 없습니다",
    ]
    return any(p in answer for p in insufficient_phrases)


def answer_with_fallback(question, all_guides):
    """3단계 fallback으로 답변 생성

    반환: (answer, notion_refs, link_refs)
    """
    # 1단계: Notion 가이드
    relevant_guides = find_relevant_guides(question, all_guides)
    notion_context = ""
    notion_refs = []
    if relevant_guides:
        parts = []
        for i, g in enumerate(relevant_guides[:5]):
            parts.append(f"[가이드 {i+1}: {g['media']} > {g['guide']}]\n{g['content'][:2000]}")
            notion_refs.append({
                "media": g['media'], "guide": g['guide'],
                "guide_id": g['guide_id'], "media_id": g['media_id']
            })
        notion_context = "\n\n---\n\n".join(parts)

    answer = get_gemini_response(question, notion_context, "", use_web_search=False)

    if not is_answer_insufficient(answer):
        return answer, notion_refs[:3], []

    # 2단계: 관리자 등록 링크 (질문 매체 매칭 시에만)
    links = load_reference_links()
    relevant_links = find_relevant_links(question, links)

    link_context = ""
    link_refs = []
    if relevant_links:
        parts = []
        for link in relevant_links[:3]:
            url = link["url"]
            if "gitbook.io" in url:
                content = fetch_gitbook_with_search(url, question)
                if not content or content.startswith("⚠️"):
                    content = fetch_link_content(url)
            else:
                content = fetch_link_content(url)
            if content and not content.startswith("⚠️"):
                parts.append(f"[링크: {link.get('title') or url}]\n{content}")
                link_refs.append(link)
        link_context = "\n\n---\n\n".join(parts)

    if link_context:
        answer = get_gemini_response(question, notion_context, link_context, use_web_search=False)
        if not is_answer_insufficient(answer):
            return answer, notion_refs[:3], link_refs

    # 3단계: 웹 검색
    answer = get_gemini_response(question, notion_context, link_context, use_web_search=True)
    return answer, notion_refs[:3], link_refs
    """질문 키워드와 매칭되는 가이드 찾기 (간단한 텍스트 매칭)"""
    q_lower = question.lower()
    q_words = set(w for w in q_lower.split() if len(w) >= 2)

    scored = []
    for g in all_guides:
        content_lower = g["content"].lower()
        guide_lower = g["guide"].lower()
        media_lower = g["media"].lower()

        # 스코어링: 제목 매칭 3점, 매체명 매칭 2점, 본문 단어 매칭 1점씩
        score = 0
        for word in q_words:
            if word in guide_lower:
                score += 3
            if word in media_lower:
                score += 2
            if word in content_lower:
                score += 1

        if score > 0:
            scored.append((score, g))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [g for _, g in scored]


# ============================
# 메인 UI
# ============================
if "mg_mode" not in st.session_state:
    st.session_state["mg_mode"] = "search"

col_input, col_toggle = st.columns([5, 1.2])
with col_input:
    if st.session_state["mg_mode"] == "search":
        search_kw = st.text_input("", placeholder="🔍 전체 가이드 검색", label_visibility="collapsed", key="mg_search")
        ai_question = None
    else:
        search_kw = None
        ai_question = st.text_input("", placeholder="💬 질문을 입력해주세요", label_visibility="collapsed", key="mg_ai_input")

with col_toggle:
    if st.session_state["mg_mode"] == "search":
        if st.button("🤖 AI 모드 전환", key="mg_mode_toggle", use_container_width=True):
            st.session_state["mg_mode"] = "ai"
            st.rerun()
    else:
        if st.button("🔍 검색 모드 전환", key="mg_mode_toggle", use_container_width=True):
            st.session_state["mg_mode"] = "search"
            st.rerun()

media_pages = get_hub_children()

if not media_pages:
    st.warning("허브 페이지에 하위 매체 페이지가 없습니다. Notion 구조를 확인해주세요.")
    st.stop()

# ============================
# AI 모드
# ============================
if st.session_state["mg_mode"] == "ai":
    st.markdown(
        "<div style='font-size:12px;color:var(--text-muted);margin-bottom:12px;'>"
        "Notion에 등록된 매체 가이드 기반으로 답변합니다. 정확한 절차는 원본 가이드도 확인해주세요."
        "</div>",
        unsafe_allow_html=True,
    )

    # 대화 히스토리
    if "mg_chat" not in st.session_state:
        st.session_state["mg_chat"] = [
            {"role": "ai", "text": "안녕하세요! 매체 가이드 관련 궁금한 점을 편하게 물어보세요.<br>예) \"네이버 GFA 계정 이관은 어떻게 하나요?\"", "sources": []}
        ]

    # 새 질문 처리
    if ai_question and ai_question != st.session_state.get("_mg_last_q"):
        st.session_state["_mg_last_q"] = ai_question
        st.session_state["mg_chat"].append({"role": "user", "text": ai_question})

        with st.spinner("답변 생성 중..."):
            all_guides = search_all_guides(tuple(frozenset(m.items()) for m in media_pages))
            answer, notion_refs, link_refs = answer_with_fallback(ai_question, all_guides)
            st.session_state["mg_chat"].append({
                "role": "ai",
                "text": answer.replace("\n", "<br>"),
                "sources": notion_refs,
                "link_sources": link_refs,
            })
        st.rerun()

    # 대화창 렌더링
    chat_html = "<div style='border:0.5px solid #ddd;border-radius:8px;background:#fafafa;padding:12px 4px;max-height:600px;overflow-y:auto;'>"
    for msg in st.session_state["mg_chat"]:
        if msg["role"] == "user":
            chat_html += (
                f"<div style='display:flex;justify-content:flex-end;margin-bottom:12px;padding:0 12px;'>"
                f"<div style='background:#111;color:#fff;padding:10px 14px;border-radius:14px 14px 4px 14px;max-width:70%;font-size:13px;line-height:1.5;'>{msg['text']}</div>"
                f"</div>"
            )
        else:
            sources_html = ""
            if msg.get("sources"):
                src_links = "".join(
                    f"<a href='#' id='ref__{s['media_id']}__{s['guide_id']}' "
                    f"style='text-decoration:none;color:#1A73E8;padding:2px 0;display:block;cursor:pointer;'>"
                    f"→ {s['media']} &gt; {s['guide']}</a>"
                    for s in msg["sources"]
                )
                sources_html = (
                    f"<div style='margin-top:6px;padding:8px 12px;background:#FFF8E1;"
                    f"border-left:3px solid #F2A93B;border-radius:4px;font-size:11px;'>"
                    f"<div style='color:#8A6D1F;font-weight:600;margin-bottom:4px;'>📚 참고 가이드</div>"
                    f"{src_links}</div>"
                )
            link_sources_html = ""
            if msg.get("link_sources"):
                link_html = "".join(
                    f"<a href='{l['url']}' target='_blank' rel='noopener' "
                    f"style='text-decoration:none;color:#1A73E8;padding:2px 0;display:block;'>"
                    f"→ {l.get('title') or l['url']}</a>"
                    for l in msg["link_sources"]
                )
                link_sources_html = (
                    f"<div style='margin-top:6px;padding:8px 12px;background:#FFF8E1;"
                    f"border-left:3px solid #F2A93B;border-radius:4px;font-size:11px;'>"
                    f"<div style='color:#8A6D1F;font-weight:600;margin-bottom:4px;'>🌐 참고 링크</div>"
                    f"{link_html}</div>"
                )
            chat_html += (
                f"<div style='display:flex;align-items:flex-start;gap:8px;margin-bottom:16px;padding:0 12px;'>"
                f"<div style='width:28px;height:28px;border-radius:50%;background:#F2A93B;color:#fff;"
                f"font-size:12px;display:flex;align-items:center;justify-content:center;font-weight:700;flex-shrink:0;'>AI</div>"
                f"<div style='flex:1;'>"
                f"<div style='background:#fff;border:0.5px solid #ddd;padding:10px 14px;"
                f"border-radius:4px 14px 14px 14px;font-size:13px;line-height:1.6;color:#111;'>{msg['text']}</div>"
                f"{sources_html}"
                f"{link_sources_html}"
                f"</div></div>"
            )
    chat_html += "</div>"

    ref_clicked = click_detector(chat_html, key="mg_chat_det")
    if ref_clicked and ref_clicked.startswith("ref__"):
        parts = ref_clicked.replace("ref__", "").split("__")
        if len(parts) == 2:
            media_id, guide_id = parts
            if st.session_state.get("_mg_dialog_guide") != guide_id:
                st.session_state["_mg_dialog_guide"] = guide_id
                st.session_state["_mg_dialog_media"] = media_id
                st.rerun()

    # 팝업 표시
    if "_mg_dialog_guide" in st.session_state:
        dialog_guide_id = st.session_state["_mg_dialog_guide"]
        dialog_media_id = st.session_state.get("_mg_dialog_media")

        # 제목 조회
        dialog_title = ""
        dialog_media_title = ""
        for m in media_pages:
            if m["id"] == dialog_media_id:
                dialog_media_title = m["title"]
                break
        sub_pages_dialog = get_sub_pages(dialog_media_id) if dialog_media_id else []
        for sp in sub_pages_dialog:
            if sp["id"] == dialog_guide_id:
                dialog_title = sp["title"]
                break

        @st.dialog(f"{dialog_media_title} · {dialog_title}", width="large")
        def show_guide_dialog():
            page_meta = get_page_meta(dialog_guide_id)
            st.markdown(
                f"<div style='font-size:11px;color:var(--text-muted);margin-bottom:12px;'>"
                f"Notion 자동 연동 · 최종 수정 {page_meta}</div>",
                unsafe_allow_html=True,
            )
            blocks = get_page_blocks(dialog_guide_id)

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

            if st.button("닫기", key="mg_dialog_close", use_container_width=True):
                del st.session_state["_mg_dialog_guide"]
                st.session_state.pop("_mg_dialog_media", None)
                st.rerun()

        show_guide_dialog()

    st.stop()

# ============================
# 검색 모드
# ============================
# 검색 실행
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
