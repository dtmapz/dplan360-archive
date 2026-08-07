"""SP봇 Notion 크롤러 — GitHub Actions에서 1일 1회 실행.

동작:
1. Notion 허브 하위 매체 페이지 순회 → 각 매체의 하위 가이드 페이지 수집
2. 각 가이드 페이지의 최종 수정일 확인 → 시트의 최종수정일과 비교
3. 신규 or 갱신된 문서만 LLM으로 정제 → 시트에 upsert
4. 새 카테고리 후보가 나오면 spbot_categories에 '대기' 상태로 추가

환경변수 (GitHub Actions Secrets):
- GEMINI_API_KEY
- NOTION_TOKEN
- GCP_SERVICE_ACCOUNT_JSON (전체 JSON 문자열)
- SHEET_ID (BIGQUERY_MAPPING_SHEET_ID 값)

로컬 테스트 시 .streamlit/secrets.toml 값을 환경변수로 export 후 실행.
"""
import json
import os
import sys
from datetime import datetime

# 프로젝트 루트를 path에 추가 (스크립트가 scripts/ 안에 있으므로)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _setup_streamlit_secrets_from_env():
    """GitHub Actions 환경에서 utils.sheets가 st.secrets를 요구하므로
    환경변수 → 임시 secrets.toml 생성."""
    import tempfile
    secrets_dir = os.path.expanduser("~/.streamlit")
    os.makedirs(secrets_dir, exist_ok=True)
    secrets_path = os.path.join(secrets_dir, "secrets.toml")

    sa_json = os.environ.get("GCP_SERVICE_ACCOUNT_JSON", "")
    sheet_id = os.environ.get("SHEET_ID", "")
    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    notion_token = os.environ.get("NOTION_TOKEN", "")

    if not (sa_json and sheet_id and gemini_key and notion_token):
        raise RuntimeError(
            "필수 환경변수 누락: GCP_SERVICE_ACCOUNT_JSON, SHEET_ID, "
            "GEMINI_API_KEY, NOTION_TOKEN"
        )

    sa = json.loads(sa_json)
    # secrets.toml 포맷 조립
    lines = [
        f'BIGQUERY_MAPPING_SHEET_ID = {json.dumps(sheet_id)}',
        f'GEMINI_API_KEY = {json.dumps(gemini_key)}',
        f'NOTION_TOKEN = {json.dumps(notion_token)}',
        # PROMOTION_SHEET_ID 는 크롤러엔 불필요하지만 utils/sheets.py 초기화에 필요
        f'PROMOTION_SHEET_ID = {json.dumps(os.environ.get("PROMOTION_SHEET_ID", sheet_id))}',
        '',
        '[gcp_service_account]',
    ]
    for k, v in sa.items():
        lines.append(f'{k} = {json.dumps(v)}')
    with open(secrets_path, "w") as f:
        f.write("\n".join(lines) + "\n")


# 로컬 실행 시 이 함수 스킵 가능 (이미 .streamlit/secrets.toml 있음)
if os.environ.get("GITHUB_ACTIONS") == "true":
    _setup_streamlit_secrets_from_env()


from notion_client import Client  # noqa: E402
from utils.spbot_sheets import (  # noqa: E402
    get_all_docs,
    upsert_doc,
    get_approved_category_names,
    get_pending_category_names,
    add_category_if_new,
)
from utils.spbot_llm import summarize_doc  # noqa: E402


# ---------------------------------------------------------------------
# Notion API 유틸
# ---------------------------------------------------------------------

def _extract_rich_text(rt_list) -> str:
    return "".join(rt.get("plain_text", "") for rt in (rt_list or []))


def _block_to_text(block: dict, notion: Client) -> str:
    t = block.get("type")
    if t == "heading_1":
        return "# " + _extract_rich_text(block[t].get("rich_text", []))
    if t == "heading_2":
        return "## " + _extract_rich_text(block[t].get("rich_text", []))
    if t == "heading_3":
        return "### " + _extract_rich_text(block[t].get("rich_text", []))
    if t == "paragraph":
        return _extract_rich_text(block[t].get("rich_text", []))
    if t in ("bulleted_list_item", "numbered_list_item", "to_do", "toggle", "quote", "callout"):
        return "- " + _extract_rich_text(block[t].get("rich_text", []))
    if t == "code":
        return _extract_rich_text(block[t].get("rich_text", []))
    if t == "child_page":
        return ""
    if t == "column_list":
        # column_list 하위는 별도로 다룸
        return ""
    return ""


def _fetch_all_children(block_id: str, notion: Client) -> list[dict]:
    results = []
    cursor = None
    while True:
        resp = notion.blocks.children.list(
            block_id=block_id, start_cursor=cursor, page_size=100,
        )
        results.extend(resp["results"])
        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")
    return results


def _get_page_body(page_id: str, notion: Client) -> str:
    """페이지 전체 블록 → 텍스트."""
    blocks = _fetch_all_children(page_id, notion)
    parts = []
    for b in blocks:
        text = _block_to_text(b, notion)
        if text:
            parts.append(text)
        # column_list 재귀
        if b.get("type") == "column_list":
            for col in _fetch_all_children(b["id"], notion):
                for inner in _fetch_all_children(col["id"], notion):
                    text = _block_to_text(inner, notion)
                    if text:
                        parts.append(text)
        # toggle 재귀
        if b.get("has_children") and b.get("type") in ("toggle", "callout"):
            for inner in _fetch_all_children(b["id"], notion):
                text = _block_to_text(inner, notion)
                if text:
                    parts.append(text)
    return "\n".join(parts)


def _get_workspace_hub(notion: Client) -> str | None:
    """워크스페이스 최상위 페이지 (허브) 찾기."""
    resp = notion.search(
        filter={"property": "object", "value": "page"}, page_size=100,
    )
    for page in resp["results"]:
        parent = page.get("parent", {})
        if parent.get("type") == "workspace":
            return page["id"]
    return None


# DPLAN360 hub 하위에 있지만 SP봇이 인덱싱하면 안 되는 페이지 목록.
# - 가이드 초안함: media-guide-draft 스킬이 생성하는 미완성 초안 저장소.
#   위치는 hub 직속(매체 페이지와 같은 계층)이라 skip 하지 않으면 초안이 검색에 노출됨.
SKIP_HUB_PAGE_IDS = {
    "3b5bc3813815805ab391cbcaf26cc0a7",  # 가이드 초안함
}


def _norm_page_id(page_id: str) -> str:
    """Notion API가 반환하는 하이픈 포함 ID를 하이픈 없는 형태로 정규화."""
    return (page_id or "").replace("-", "").lower()


def _get_hub_child_pages(hub_id: str, notion: Client) -> list[dict]:
    """허브 페이지의 매체 페이지 목록.
    matches MediaGuide.get_hub_children: column_list > column > child_page 까지 탐색.
    SKIP_HUB_PAGE_IDS에 있는 페이지는 제외 (초안·비인덱싱 대상)."""
    blocks = _fetch_all_children(hub_id, notion)
    pages = []

    def _maybe_add(child: dict):
        cid = child["id"]
        if _norm_page_id(cid) in SKIP_HUB_PAGE_IDS:
            print(f"  ⊘ skip: {child['child_page']['title']} (초안·비인덱싱)", flush=True)
            return
        pages.append({"id": cid, "title": child["child_page"]["title"]})

    for b in blocks:
        t = b.get("type")
        if t == "child_page":
            _maybe_add(b)
        elif t == "column_list" and b.get("has_children"):
            columns = notion.blocks.children.list(block_id=b["id"], page_size=100)["results"]
            for col in columns:
                if col.get("type") == "column" and col.get("has_children"):
                    col_children = notion.blocks.children.list(
                        block_id=col["id"], page_size=100
                    )["results"]
                    for child in col_children:
                        if child.get("type") == "child_page":
                            _maybe_add(child)
    return pages


def _get_child_pages(page_id: str, notion: Client) -> list[dict]:
    """매체 페이지의 하위 가이드 (direct child_page만)."""
    blocks = _fetch_all_children(page_id, notion)
    pages = []
    for b in blocks:
        if b.get("type") == "child_page":
            pages.append({
                "id": b["id"],
                "title": b["child_page"]["title"],
            })
    return pages


def _get_page_last_edited(page_id: str, notion: Client) -> str:
    page = notion.pages.retrieve(page_id=page_id)
    return (page.get("last_edited_time") or "")[:10]  # YYYY-MM-DD


def _notion_page_url(page_id: str) -> str:
    return f"https://www.notion.so/{page_id.replace('-', '')}"


# ---------------------------------------------------------------------
# 메인 sync
# ---------------------------------------------------------------------

def run():
    notion = Client(auth=os.environ.get("NOTION_TOKEN") or _get_notion_token_from_secrets())

    hub_id = _get_workspace_hub(notion)
    if not hub_id:
        print("허브 페이지 찾지 못함 — 종료", flush=True)
        return

    media_pages = _get_hub_child_pages(hub_id, notion)
    print(f"매체 페이지 {len(media_pages)}개 발견", flush=True)

    # 기존 시트 문서 로드 (원본링크 → 최종수정일)
    existing = {}
    for d in get_all_docs():
        link = str(d.get("원본링크", "")).strip()
        if link:
            existing[link] = str(d.get("최종수정일", "")).strip()

    approved_cats = get_approved_category_names()
    pending_cats = get_pending_category_names()

    total_created = 0
    total_updated = 0
    total_skipped = 0
    new_category_proposals = set()

    for media in media_pages:
        media_title = media["title"]
        guide_pages = _get_child_pages(media["id"], notion)
        print(f"[{media_title}] 하위 가이드 {len(guide_pages)}개", flush=True)

        for guide in guide_pages:
            guide_id = guide["id"]
            guide_title = guide["title"]
            source_link = _notion_page_url(guide_id)
            last_edited = _get_page_last_edited(guide_id, notion)

            # 이미 있는 문서 + 수정일 동일 → 스킵
            if source_link in existing and existing[source_link] == last_edited:
                total_skipped += 1
                continue

            body = _get_page_body(guide_id, notion)
            if not body.strip():
                total_skipped += 1
                continue

            try:
                meta = summarize_doc(
                    title_hint=f"{media_title} · {guide_title}",
                    body_text=body,
                    approved_categories=approved_cats,
                    pending_categories=pending_cats,
                )
            except Exception as e:
                print(f"  ! LLM 실패 [{guide_title}]: {e}", flush=True)
                continue

            if meta.get("new_category_proposal"):
                new_category_proposals.add(meta["new_category_proposal"])

            _, action = upsert_doc(
                source_channel="Notion",
                source_link=source_link,
                title=meta["title"] or guide_title,
                summary=meta["summary"],
                category=meta["category"],
                keywords=meta["keywords"],
                body=body,
                status=meta["status"],
            )
            if action == "created":
                total_created += 1
            else:
                total_updated += 1

    # 신규 카테고리 제안 → spbot_categories에 대기 상태로 추가
    for name in new_category_proposals:
        add_category_if_new(name, initial_status="대기")

    print("=" * 40, flush=True)
    print(f"신규: {total_created} · 갱신: {total_updated} · 스킵: {total_skipped}", flush=True)
    if new_category_proposals:
        print(f"신규 카테고리 후보 (승인 대기): {sorted(new_category_proposals)}", flush=True)


def _get_notion_token_from_secrets() -> str:
    """로컬 실행 fallback."""
    import toml
    p = os.path.expanduser("~/.streamlit/secrets.toml")
    if not os.path.exists(p):
        p = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            ".streamlit/secrets.toml",
        )
    return toml.load(p).get("NOTION_TOKEN", "")


if __name__ == "__main__":
    started = datetime.now().isoformat(timespec="seconds")
    print(f"SP봇 Notion 동기화 시작 · {started}", flush=True)
    run()
    ended = datetime.now().isoformat(timespec="seconds")
    print(f"완료 · {ended}", flush=True)
