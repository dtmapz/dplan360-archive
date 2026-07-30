import streamlit as st
import gspread
import requests
import re
from datetime import date
from google.oauth2 import service_account

SHEET_ID = st.secrets["BIGQUERY_MAPPING_SHEET_ID"]

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


@st.cache_resource
def _init():
    creds = service_account.Credentials.from_service_account_info(
        dict(st.secrets["gcp_service_account"]),
        scopes=SCOPES,
    )
    gc = gspread.authorize(creds)
    return gc, creds


def _get_sheet(tab_name: str):
    gc, _ = _init()
    return gc.open_by_key(SHEET_ID).worksheet(tab_name)


def _get_auth_token() -> str:
    _, creds = _init()
    if not creds.valid or creds.expired:
        from google.auth.transport.requests import Request
        creds.refresh(Request())
    return creds.token


# ======================================================================
# 카테고리
# ======================================================================

@st.cache_data(ttl=300)
def get_all_categories() -> list[dict]:
    ws = _get_sheet("category")
    return ws.get_all_records()


@st.cache_data(ttl=300)
def get_major_categories() -> list[str]:
    cats = get_all_categories()
    seen = []
    for c in cats:
        m = c["대분류"]
        if m not in seen:
            seen.append(m)
    return seen


@st.cache_data(ttl=300)
def get_sub_categories(major: str) -> list[str]:
    cats = get_all_categories()
    return sorted({
        c["중분류"] for c in cats
        if c["대분류"] == major and c["중분류"] and c["중분류"] != "-"
    })


def get_or_create_category(major: str, sub: str | None = None) -> str:
    sub = sub or "-"
    cats = get_all_categories()
    for c in cats:
        if c["대분류"] == major and c["중분류"] == sub:
            return c["카테고리ID"]

    prefix = major[:2] if len(major) >= 2 and major[:2].isdigit() else "99"
    max_seq = -1
    for c in cats:
        parts = c["카테고리ID"].split("-")
        if len(parts) == 3 and parts[1] == prefix:
            try:
                max_seq = max(max_seq, int(parts[2]))
            except ValueError:
                pass

    new_id = f"CAT-{prefix}-{max_seq + 1:03d}"
    ws = _get_sheet("category")
    ws.append_row([new_id, major, sub], value_input_option="USER_ENTERED")
    get_all_categories.clear()
    get_major_categories.clear()
    get_sub_categories.clear()
    return new_id


# ======================================================================
# 매체 — 읽기 (기존 + 신규)
# ======================================================================

@st.cache_data(ttl=300)
def _get_all_media_rows() -> list[dict]:
    ws = _get_sheet("media_info")
    rows = ws.get_all_records()
    result = []
    for i, r in enumerate(rows):
        if not r.get("매체명"):
            continue
        r["_row"] = i + 2
        result.append(r)
    return result


def _build_cat_lookup() -> dict:
    cats = get_all_categories()
    return {
        c["카테고리ID"]: {"major_category": c["대분류"], "sub_category": c["중분류"]}
        for c in cats
    }


def _row_to_media(row: dict, cat_lookup: dict | None = None) -> dict:
    cat_id = row.get("카테고리ID", "")
    categories = (cat_lookup or {}).get(cat_id, {})
    media_id = row.get("매체ID") or f"_row_{row.get('_row', 0)}"
    return {
        "id": media_id,
        "name": row["매체명"],
        "intro_doc_url": row.get("소개서링크") or None,
        "updated_at": row.get("업데이트일자") or None,
        "contacts": [{
            "id": media_id,
            "manager_name": row.get("담당자이름") or None,
            "position": row.get("직급") or None,
            "phone": str(row.get("전화번호") or "") or None,
            "email": row.get("이메일") or None,
            "team_email": row.get("팀메일") or None,
            "last_contact_date": row.get("최근연락일") or None,
        }],
        "categories": categories,
    }


@st.cache_data(ttl=300)
def get_all_media() -> list[dict]:
    rows = _get_all_media_rows()
    return [{"매체ID": r["매체ID"], "카테고리ID": r["카테고리ID"], "name": r["매체명"]} for r in rows]


@st.cache_data(ttl=300)
def build_media_cat_map() -> dict:
    all_media = get_all_media()
    cats = get_all_categories()
    cat_id_to_major = {c["카테고리ID"]: c["대분류"] for c in cats}
    return {m["name"]: cat_id_to_major.get(m["카테고리ID"], "") for m in all_media}


def search_media(keyword: str) -> list[dict]:
    rows = _get_all_media_rows()
    cat_lookup = _build_cat_lookup()
    kw = keyword.lower()
    results = []
    for r in rows:
        name = (r.get("매체명") or "").lower()
        cat = cat_lookup.get(r.get("카테고리ID", ""), {})
        major = cat.get("major_category", "").lower()
        sub = cat.get("sub_category", "").lower()
        if kw in name or kw in major or kw in sub:
            results.append(_row_to_media(r, cat_lookup))
    return results


def get_media_detail(media_id: str) -> dict:
    rows = _get_all_media_rows()
    cat_lookup = _build_cat_lookup()
    for r in rows:
        match_id = r.get("매체ID") or f"_row_{r.get('_row', 0)}"
        if match_id == media_id:
            return _row_to_media(r, cat_lookup)
    return {"id": media_id, "name": "", "contacts": [{}], "categories": {}}


def get_media_by_category(major: str) -> list[dict]:
    rows = _get_all_media_rows()
    cat_lookup = _build_cat_lookup()
    return [
        _row_to_media(r, cat_lookup)
        for r in rows
        if cat_lookup.get(r.get("카테고리ID", ""), {}).get("major_category") == major
    ]


# ======================================================================
# 매체 — 쓰기
# ======================================================================

def _clear_media_caches():
    _get_all_media_rows.clear()
    get_all_media.clear()
    build_media_cat_map.clear()


def update_media_info(
    media_id: str,
    name: str,
    major: str,
    sub: str | None,
    doc_url: str | None,
    manager_name: str | None,
    position: str | None,
    phone: str | None,
    email: str | None,
    team_email: str | None,
    last_contact: str | None,
) -> None:
    ws = _get_sheet("media_info")
    if media_id.startswith("_row_"):
        row_num = int(media_id.split("_row_")[1])
    else:
        cell = ws.find(media_id, in_column=1)
        if not cell:
            raise ValueError(f"매체 {media_id}를 찾을 수 없습니다.")
        row_num = cell.row

    cat_id = get_or_create_category(major, sub)
    today = date.today().isoformat()

    actual_id = media_id if not media_id.startswith("_row_") else ""
    row_data = [
        actual_id,
        cat_id,
        name or "",
        doc_url or "",
        today,
        manager_name or "",
        position or "",
        phone or "",
        email or "",
        team_email or "",
        last_contact or "",
    ]
    ws.update(values=[row_data], range_name=f"A{row_num}:K{row_num}", value_input_option="USER_ENTERED")
    _clear_media_caches()


def create_media_info(
    name: str,
    major: str,
    sub: str | None,
    doc_url: str | None,
    manager_name: str | None,
    position: str | None,
    phone: str | None,
    email: str | None,
    team_email: str | None,
    last_contact: str | None,
) -> str:
    rows = _get_all_media_rows()
    max_num = 0
    for r in rows:
        mid = r.get("매체ID", "")
        parts = mid.split("-")
        if len(parts) == 2:
            try:
                max_num = max(max_num, int(parts[1]))
            except ValueError:
                pass
    new_id = f"MED-{max_num + 1:03d}"

    cat_id = get_or_create_category(major, sub)
    today = date.today().isoformat()

    row_data = [
        new_id,
        cat_id,
        name or "",
        doc_url or "",
        today,
        manager_name or "",
        position or "",
        phone or "",
        email or "",
        team_email or "",
        last_contact or "",
    ]
    ws = _get_sheet("media_info")
    ws.append_row(row_data, value_input_option="USER_ENTERED")
    _clear_media_caches()
    return new_id


# ======================================================================
# 제작가이드
# ======================================================================

@st.cache_data(ttl=300)
def get_creative_guides() -> list[dict]:
    ws = _get_sheet("creative_guide")
    rows = ws.get_all_records()
    result = []
    for r in rows:
        if not r.get("상품명"):
            continue
        sheet_url = str(r.get("스프레드시트ID", "") or "").strip()
        result.append({
            "매체ID": r["매체ID"],
            "media_name": r["매체명"],
            "product_name": r["상품명"],
            "sheet_url": sheet_url,
            "has_file": bool(sheet_url),
        })
    return result


def parse_sheet_url(url: str) -> tuple[str, int | None]:
    sid_match = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", url)
    gid_match = re.search(r"[?&#]gid=(\d+)", url)
    spreadsheet_id = sid_match.group(1) if sid_match else ""
    gid = int(gid_match.group(1)) if gid_match else None
    return spreadsheet_id, gid


@st.cache_data(ttl=300, show_spinner=False)
def export_sheet_as_xlsx(sheet_url: str) -> bytes:
    """스프레드시트를 xlsx bytes로 다운로드. 동일 URL 5분간 캐싱."""
    spreadsheet_id, gid = parse_sheet_url(sheet_url)
    if not spreadsheet_id:
        raise ValueError(f"Invalid sheet URL: {sheet_url}")

    token = _get_auth_token()
    url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export"
    params = {"format": "xlsx"}
    if gid is not None:
        params["gid"] = str(gid)

    resp = requests.get(url, params=params, headers={"Authorization": f"Bearer {token}"})
    resp.raise_for_status()
    return resp.content
