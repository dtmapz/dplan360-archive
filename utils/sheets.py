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
        "memo": row.get("메모") or None,
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
def get_all_media_with_categories() -> list[dict]:
    """마일스톤/그리드용: 전체 매체를 categories 정보와 함께 반환."""
    rows = _get_all_media_rows()
    cat_lookup = _build_cat_lookup()
    return [_row_to_media(r, cat_lookup) for r in rows]


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
    memo: str | None = None,
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
        memo or "",
    ]
    ws.update(values=[row_data], range_name=f"A{row_num}:L{row_num}", value_input_option="USER_ENTERED")
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
    memo: str | None = None,
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
        memo or "",
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


def to_download_url(url: str) -> str:
    """Google Drive/Docs URL을 다운로드 URL로 변환. 외부 URL은 그대로 반환."""
    if not url:
        return url
    m = re.search(r"docs\.google\.com/document/d/([a-zA-Z0-9_-]+)", url)
    if m:
        return f"https://docs.google.com/document/d/{m.group(1)}/export?format=pdf"
    m = re.search(r"docs\.google\.com/spreadsheets/d/([a-zA-Z0-9_-]+)", url)
    if m:
        return f"https://docs.google.com/spreadsheets/d/{m.group(1)}/export?format=xlsx"
    m = re.search(r"docs\.google\.com/presentation/d/([a-zA-Z0-9_-]+)", url)
    if m:
        return f"https://docs.google.com/presentation/d/{m.group(1)}/export?format=pdf"
    m = re.search(r"drive\.google\.com/file/d/([a-zA-Z0-9_-]+)", url)
    if m:
        return f"https://drive.google.com/uc?export=download&id={m.group(1)}"
    m = re.search(r"drive\.google\.com/open\?id=([a-zA-Z0-9_-]+)", url)
    if m:
        return f"https://drive.google.com/uc?export=download&id={m.group(1)}"
    return url


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


# ======================================================================
# 미디어허브 (media_hub · media_notice 탭)
# ======================================================================

def _clear_hub_caches():
    _get_hub_rows.clear()
    _get_notice_rows.clear()


@st.cache_data(ttl=300)
def _get_hub_rows() -> list[dict]:
    """media_hub 탭 전체 조회. _row 첨부."""
    ws = _get_sheet("media_hub")
    rows = ws.get_all_records()
    result = []
    for i, r in enumerate(rows):
        if not r.get("매체ID"):
            continue
        r["_row"] = i + 2
        result.append(r)
    return result


@st.cache_data(ttl=300)
def _get_notice_rows() -> list[dict]:
    """media_notice 탭 전체 조회. _row 첨부."""
    ws = _get_sheet("media_notice")
    rows = ws.get_all_records()
    result = []
    for i, r in enumerate(rows):
        if not r.get("매체ID"):
            continue
        r["_row"] = i + 2
        result.append(r)
    return result


def _to_num(v, default=0) -> int:
    if v is None or v == "":
        return default
    try:
        return int(float(str(v).strip()))
    except (ValueError, TypeError):
        return default


def get_hub_by_media(media_id: str, include_intro_doc: bool = True) -> list[dict]:
    """매체 미디어허브 자료를 섹션별로 그룹화 반환.
    - Q8: media_info 소개서 URL을 '소개서' 섹션에 자동 편입
    - 섹션 정렬: 섹션순서 min → 이름 오름차순
    - 자료 정렬: 자료순서 asc → 등록 순
    """
    rows = [r for r in _get_hub_rows() if r.get("매체ID") == media_id]

    # 섹션별 그룹핑
    sections_map = {}
    for r in rows:
        name = str(r.get("섹션명", "")).strip()
        if not name:
            continue
        s = sections_map.setdefault(name, {"name": name, "order": None, "items": []})
        sec_order = _to_num(r.get("섹션순서"), default=None) if r.get("섹션순서") not in (None, "") else None
        if sec_order is not None and (s["order"] is None or sec_order < s["order"]):
            s["order"] = sec_order
        s["items"].append({
            "row": r["_row"],
            "title": str(r.get("제목", "")).strip(),
            "url": str(r.get("URL", "")).strip(),
            "desc": str(r.get("설명", "")).strip(),
            "order": _to_num(r.get("자료순서"), default=999),
        })

    # Q8: 소개서 자동 편입 (해당 매체의 intro_doc_url 존재 시 '소개서' 섹션 상단에 추가)
    if include_intro_doc:
        media = get_media_detail(media_id)
        intro_url = (media or {}).get("intro_doc_url")
        if intro_url:
            s = sections_map.setdefault("소개서", {"name": "소개서", "order": None, "items": []})
            # 자동 편입 아이템 (row=None → 편집/삭제 불가 표시)
            s["items"].insert(0, {
                "row": None,
                "title": f"{(media or {}).get('name', '')} 매체 소개서",
                "url": intro_url,
                "desc": "media_info에서 자동 편입",
                "order": -1,
                "auto": True,
            })

    # 각 섹션 items 정렬
    for s in sections_map.values():
        s["items"].sort(key=lambda x: (x["order"], x.get("title", "")))
        if s["order"] is None:
            s["order"] = 999

    # 섹션 정렬 (order → 이름)
    sections = sorted(sections_map.values(), key=lambda s: (s["order"], s["name"]))
    return sections


def get_media_notice(media_id: str) -> dict | None:
    """활성 공지 반환. 없으면 None."""
    for r in _get_notice_rows():
        if str(r.get("매체ID", "")).strip() != media_id:
            continue
        active_val = str(r.get("활성여부", "")).strip().upper()
        if active_val not in ("Y", "TRUE", "1", "예", "YES", "T"):
            continue
        content = str(r.get("공지내용", "")).strip()
        if not content:
            continue
        return {
            "row": r["_row"],
            "content": content,
            "updated": str(r.get("업데이트일자", "")).strip(),
            "active": True,
        }
    return None


def get_media_notice_any(media_id: str) -> dict | None:
    """비활성 포함 매체의 공지 조회 (편집용)."""
    for r in _get_notice_rows():
        if str(r.get("매체ID", "")).strip() != media_id:
            continue
        active_val = str(r.get("활성여부", "")).strip().upper()
        return {
            "row": r["_row"],
            "content": str(r.get("공지내용", "")).strip(),
            "updated": str(r.get("업데이트일자", "")).strip(),
            "active": active_val in ("Y", "TRUE", "1", "예", "YES", "T"),
        }
    return None


def has_media_hub(media_id: str) -> bool:
    """매체가 미디어허브를 가지고 있나?

    관리자 지정 매체만 hub 뷰로 진입 → 조건:
    - media_hub 탭에 자료 1개 이상 등록, 또는
    - media_notice 탭에 활성 공지 있음

    소개서 URL만으로는 활성화되지 않음. (활성 후 Q8 자동 편입은 hub 렌더링 시 동작)
    """
    if any(r.get("매체ID") == media_id for r in _get_hub_rows()):
        return True
    if get_media_notice(media_id):
        return True
    return False


# ---------- Hub 자료 CRUD ----------

def add_hub_item(media_id: str, section_name: str, section_order: int,
                 title: str, url: str, desc: str, item_order: int) -> None:
    ws = _get_sheet("media_hub")
    row_data = [
        media_id, section_name, section_order or "",
        title or "", url or "", desc or "", item_order or "",
    ]
    ws.append_row(row_data, value_input_option="USER_ENTERED")
    _clear_hub_caches()


def update_hub_item(row_num: int, media_id: str, section_name: str, section_order,
                    title: str, url: str, desc: str, item_order) -> None:
    ws = _get_sheet("media_hub")
    row_data = [
        media_id, section_name,
        section_order if section_order not in (None, "") else "",
        title or "", url or "", desc or "",
        item_order if item_order not in (None, "") else "",
    ]
    ws.update(values=[row_data], range_name=f"A{row_num}:G{row_num}", value_input_option="USER_ENTERED")
    _clear_hub_caches()


def delete_hub_item(row_num: int) -> None:
    ws = _get_sheet("media_hub")
    ws.delete_rows(row_num)
    _clear_hub_caches()


def delete_section(media_id: str, section_name: str) -> None:
    """매체 내 특정 섹션의 모든 자료 삭제. 아래에서 위로 삭제해서 행 시프트 방지."""
    ws = _get_sheet("media_hub")
    targets = [r["_row"] for r in _get_hub_rows()
               if r.get("매체ID") == media_id and str(r.get("섹션명", "")).strip() == section_name]
    for row_num in sorted(targets, reverse=True):
        ws.delete_rows(row_num)
    _clear_hub_caches()


# ---------- Notice CRUD ----------

def upsert_notice(media_id: str, content: str, active: bool = True) -> None:
    """공지 upsert. 매체당 한 행 원칙."""
    ws = _get_sheet("media_notice")
    today = date.today().isoformat()
    active_str = "Y" if active else "N"
    existing = None
    for r in _get_notice_rows():
        if str(r.get("매체ID", "")).strip() == media_id:
            existing = r
            break
    row_data = [media_id, active_str, content or "", today]
    if existing:
        row_num = existing["_row"]
        ws.update(values=[row_data], range_name=f"A{row_num}:D{row_num}", value_input_option="USER_ENTERED")
    else:
        ws.append_row(row_data, value_input_option="USER_ENTERED")
    _clear_hub_caches()


def delete_notice(media_id: str) -> None:
    """공지 행 완전 삭제."""
    ws = _get_sheet("media_notice")
    for r in _get_notice_rows():
        if str(r.get("매체ID", "")).strip() == media_id:
            ws.delete_rows(r["_row"])
            break
    _clear_hub_caches()
