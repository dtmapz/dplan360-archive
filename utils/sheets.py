import streamlit as st
import gspread
import requests
import re
from datetime import date, timedelta, datetime as _dt
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


@st.cache_data(ttl=300)
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


@st.cache_data(ttl=300)
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


@st.cache_data(ttl=300)
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
    # 매체 행을 파생해 캐시하는 함수들 — 누락 시 최대 5분간 옛 데이터가 노출됨
    get_all_media_with_categories.clear()
    search_media.clear()
    get_media_by_category.clear()


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
    get_hub_media_ids.clear()


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
    return media_id in get_hub_media_ids()


@st.cache_data(ttl=300)
def get_hub_media_ids() -> set[str]:
    """허브 활성 매체ID 집합을 1회 계산해 캐시.

    표 렌더링에서 행마다 has_media_hub()를 호출하면 행당 _get_hub_rows() +
    _get_notice_rows() 전체 복사가 발생 → 목록 단위로 이 집합을 한 번만 조회한다.
    """
    ids = {str(r.get("매체ID", "")).strip() for r in _get_hub_rows()}
    ids.discard("")

    for r in _get_notice_rows():
        active_val = str(r.get("활성여부", "")).strip().upper()
        if active_val not in ("Y", "TRUE", "1", "예", "YES", "T"):
            continue
        if not str(r.get("공지내용", "")).strip():
            continue
        mid = str(r.get("매체ID", "")).strip()
        if mid:
            ids.add(mid)

    return ids


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


# ======================================================================
# 매체 프로모션 (home_promotion 탭) — 9_MediaPromo.py 용
# 시트 ID는 PROMOTION_SHEET_ID (PROMOTION LIVE 시트) 사용
# ======================================================================

DEFAULT_CATEGORY_PRESET = "line"
PROMOTION_SHEET_ID = st.secrets["PROMOTION_SHEET_ID"]


def _get_promo_sheet(tab_name: str):
    gc, _ = _init()
    return gc.open_by_key(PROMOTION_SHEET_ID).worksheet(tab_name)


@st.cache_data(ttl=300)
def _get_promotion_rows() -> list[dict]:
    ws = _get_promo_sheet("home_promotion")
    rows = ws.get_all_records()
    result = []
    for i, r in enumerate(rows):
        if not r.get("프로모션명"):
            continue
        r["_row"] = i + 2
        result.append(r)
    return result


def _parse_promo_date(val) -> date | None:
    s = str(val or "").strip()
    if not s:
        return None
    if isinstance(val, date):
        return val
    try:
        return _dt.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def _promo_status(end_date: date | None, today: date) -> str:
    this_month_start = today.replace(day=1)
    prev_month_start = (this_month_start - timedelta(days=1)).replace(day=1)
    if end_date is None or end_date >= this_month_start:
        return "active"
    if end_date >= prev_month_start:
        return "inactive"
    return "hidden"


def _parse_categories(raw: str) -> list[tuple[str, str]]:
    result = []
    for part in str(raw or "").split(","):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            name, key = part.split(":", 1)
        else:
            name, key = part, DEFAULT_CATEGORY_PRESET
        result.append((name.strip(), key.strip() or DEFAULT_CATEGORY_PRESET))
    return result


def _format_categories(pairs: list[tuple[str, str]]) -> str:
    return ",".join(f"{name}:{key}" for name, key in pairs if name and name.strip())


@st.cache_data(ttl=300)
def get_home_promotions() -> list[dict]:
    """매체 프로모션 목록. status='hidden'인 항목은 결과에서 제외."""
    today = date.today()
    result = []
    for r in _get_promotion_rows():
        end_date = _parse_promo_date(r.get("종료일"))
        start_date = _parse_promo_date(r.get("시작일"))
        status = _promo_status(end_date, today)
        if status == "hidden":
            continue
        result.append({
            "id": r.get("프로모션ID") or f"_row_{r['_row']}",
            "row": r["_row"],
            "media_name": str(r.get("매체명", "")).strip(),
            "name": str(r.get("프로모션명", "")).strip(),
            "subtitle": str(r.get("부제목", "")).strip(),
            "image_url": str(r.get("이미지URL", "")).strip(),
            "preview_image_url": str(r.get("미리보기이미지URL", "")).strip(),
            "categories": _parse_categories(r.get("카테고리", "")),
            "start_date": start_date,
            "end_date": end_date,
            "memo": str(r.get("메모", "")).strip(),
            "status": status,
        })

    def _sort_key(p):
        is_ongoing = p["status"] == "active" and (p["start_date"] is None or p["start_date"] <= today)
        group = 0 if is_ongoing else (1 if p["status"] == "active" else 2)
        return (group, p["start_date"] or date.max)

    return sorted(result, key=_sort_key)


def _clear_promotion_caches():
    _get_promotion_rows.clear()
    get_home_promotions.clear()


def normalize_image_url(url: str) -> str:
    m = re.search(r"drive\.google\.com/file/d/([a-zA-Z0-9_-]+)", url or "")
    if m:
        return f"https://drive.google.com/uc?export=view&id={m.group(1)}"
    return url


def validate_image_url(url: str) -> tuple[bool, str]:
    if not url:
        return False, "이미지 URL이 비어 있습니다."
    check_url = normalize_image_url(url)
    try:
        resp = requests.head(check_url, timeout=4, allow_redirects=True)
        if resp.status_code != 200:
            resp = requests.get(check_url, timeout=4, stream=True)
        content_type = resp.headers.get("Content-Type", "")
        if resp.status_code == 200 and content_type.startswith("image/"):
            return True, "정상 확인됨"
        return False, f"이미지 응답이 아닙니다 (status={resp.status_code}, type={content_type or '-'})"
    except requests.RequestException as e:
        return False, f"URL 접근 실패: {e}"


def create_home_promotion(
    media_name: str,
    name: str,
    subtitle: str,
    image_url: str,
    categories: list[tuple[str, str]],
    start_date: str,
    end_date: str,
    memo: str = "",
    preview_image_url: str = "",
) -> str:
    rows = _get_promotion_rows()
    max_num = 0
    for r in rows:
        pid = r.get("프로모션ID", "")
        parts = pid.split("-")
        if len(parts) == 2:
            try:
                max_num = max(max_num, int(parts[1]))
            except ValueError:
                pass
    new_id = f"PROMO-{max_num + 1:03d}"

    row_data = [
        new_id,
        media_name or "",
        name or "",
        subtitle or "",
        normalize_image_url(image_url or ""),
        _format_categories(categories),
        start_date or "",
        end_date or "",
        memo or "",
        date.today().isoformat(),
        normalize_image_url(preview_image_url or ""),
    ]
    ws = _get_promo_sheet("home_promotion")
    ws.append_row(row_data, value_input_option="USER_ENTERED")
    _clear_promotion_caches()
    return new_id


def update_home_promotion(
    row_num: int,
    media_name: str,
    name: str,
    subtitle: str,
    image_url: str,
    categories: list[tuple[str, str]],
    start_date: str,
    end_date: str,
    memo: str = "",
    preview_image_url: str = "",
) -> None:
    ws = _get_promo_sheet("home_promotion")
    existing_id = ws.cell(row_num, 1).value or ""
    existing_created = ws.cell(row_num, 10).value or date.today().isoformat()
    row_data = [
        existing_id,
        media_name or "",
        name or "",
        subtitle or "",
        normalize_image_url(image_url or ""),
        _format_categories(categories),
        start_date or "",
        end_date or "",
        memo or "",
        existing_created,
        normalize_image_url(preview_image_url or ""),
    ]
    ws.update(values=[row_data], range_name=f"A{row_num}:K{row_num}", value_input_option="USER_ENTERED")
    _clear_promotion_caches()


def delete_home_promotion(row_num: int) -> None:
    ws = _get_promo_sheet("home_promotion")
    ws.delete_rows(row_num)
    _clear_promotion_caches()


# ======================================================================
# MEDIA GUIDE 다운로드 매핑 (media_guide_download 탭) — 6_MediaGuide.py 용
# ======================================================================

@st.cache_data(ttl=300)
def _get_guide_download_rows() -> list[dict]:
    ws = _get_sheet("media_guide_download")
    rows = ws.get_all_records()
    result = []
    for i, r in enumerate(rows):
        if not r.get("Notion페이지ID"):
            continue
        r["_row"] = i + 2
        result.append(r)
    return result


def get_guide_download(notion_page_id: str) -> dict | None:
    """페이지 ID로 매핑 조회. 없으면 None."""
    pid = (notion_page_id or "").strip()
    if not pid:
        return None
    for r in _get_guide_download_rows():
        if str(r.get("Notion페이지ID", "")).strip() == pid:
            return {
                "row": r["_row"],
                "notion_page_id": pid,
                "media_name": str(r.get("매체명", "")).strip(),
                "guide_title": str(r.get("가이드제목", "")).strip(),
                "storage_path": str(r.get("storage_path", "")).strip(),
                "original_filename": str(r.get("원본파일명", "")).strip(),
                "uploaded_at": str(r.get("업로드일", "")).strip(),
            }
    return None


def upsert_guide_download(
    notion_page_id: str,
    media_name: str,
    guide_title: str,
    storage_path: str,
    original_filename: str,
) -> None:
    """페이지 ID 기준 upsert. 기존 매핑 있으면 storage_path 갱신."""
    ws = _get_sheet("media_guide_download")
    existing = get_guide_download(notion_page_id)
    today = date.today().isoformat()
    row_data = [
        notion_page_id,
        media_name or "",
        guide_title or "",
        storage_path or "",
        original_filename or "",
        today,
    ]
    if existing:
        ws.update(
            values=[row_data],
            range_name=f"A{existing['row']}:F{existing['row']}",
            value_input_option="USER_ENTERED",
        )
    else:
        ws.append_row(row_data, value_input_option="USER_ENTERED")
    _get_guide_download_rows.clear()


def delete_guide_download(notion_page_id: str) -> None:
    existing = get_guide_download(notion_page_id)
    if not existing:
        return
    ws = _get_sheet("media_guide_download")
    ws.delete_rows(existing["row"])
    _get_guide_download_rows.clear()


# ======================================================================
# 캠페인 이력 (budget_history) + 광고주 마스터 (budget_adv)
# ======================================================================

@st.cache_data(ttl=600)
def get_budget_history() -> list[dict]:
    """budget_history 탭. 컬럼: 캠페인명 | 광고주 | 브랜드 | 대행사 | 매체사 | 광고수주액 | 대행사 발행월 | 메모 | 상품(정리)

    numericise_ignore=['all']: 2025.10 같은 값이 float로 캐스팅되며 뒤 0이 소실되는 문제 방지.
    호출부에서 필요한 컬럼만 수동 변환한다.
    """
    ws = _get_sheet("budget_history")
    return ws.get_all_records(numericise_ignore=["all"])


@st.cache_data(ttl=600)
def get_budget_adv() -> list[dict]:
    """budget_adv 탭. 컬럼: 광고주명 | 브랜드명 | 대업종 | 소업종"""
    ws = _get_sheet("budget_adv")
    return ws.get_all_records()


# ======================================================================
# 조직도 (organization 탭) — 별도 시트 ORG_SHEET_ID
# 컬럼: email | name | division | team | position | role | is_active
# role: "admin" 이면 관리자. 그 외("user"/공란)는 일반.
# is_active: "Y"만 활성. "N"/공란은 비활성(로그인 차단, 담당자 목록 제외).
# 회원가입/로그인 게이트 원본이므로 절대 하드코딩 금지 — st.secrets 참조.
# ======================================================================

# 현재 조직도 시트는 PROMOTION_SHEET_ID 와 동일한 스프레드시트를 공유(organization 탭).
# 향후 분리하려면 ORG_SHEET_ID secret 추가하면 자동으로 그쪽을 우선 사용.
ORG_SHEET_ID = st.secrets.get("ORG_SHEET_ID", "") or PROMOTION_SHEET_ID
ORG_TAB_NAME = st.secrets.get("ORG_TAB_NAME", "organization")


def _get_org_sheet():
    if not ORG_SHEET_ID:
        raise RuntimeError("ORG_SHEET_ID / PROMOTION_SHEET_ID secret이 설정되지 않았습니다.")
    gc, _ = _init()
    return gc.open_by_key(ORG_SHEET_ID).worksheet(ORG_TAB_NAME)


def _norm_email(v) -> str:
    return str(v or "").strip().lower()


def _is_active_row(row: dict) -> bool:
    v = str(row.get("is_active", "")).strip().upper()
    return v == "Y" or v == ""  # 공란은 활성 취급(초기 마이그레이션 편의)


@st.cache_data(ttl=300)
def _get_all_org_rows() -> list[dict]:
    """조직도 원본 행. 활성/비활성 모두 포함."""
    ws = _get_org_sheet()
    return ws.get_all_records()


@st.cache_data(ttl=300)
def get_org_by_email_sheet(email: str) -> dict | None:
    """이메일로 조직 정보 조회. 활성 사용자만. 없으면 None."""
    target = _norm_email(email)
    if not target:
        return None
    for r in _get_all_org_rows():
        if _norm_email(r.get("email")) != target:
            continue
        if not _is_active_row(r):
            return None
        return {
            "email": _norm_email(r.get("email")),
            "name": str(r.get("name", "")).strip(),
            "division": str(r.get("division", "")).strip(),
            "team": str(r.get("team", "")).strip(),
            "position": str(r.get("position", "")).strip(),
            "role": str(r.get("role", "")).strip().lower(),
            "is_active": True,
        }
    return None


@st.cache_data(ttl=300)
def get_all_org_members_sheet() -> list[dict]:
    """조직도 전체 (활성만) — division/team/name 정렬."""
    rows = []
    for r in _get_all_org_rows():
        if not _is_active_row(r):
            continue
        if not _norm_email(r.get("email")):
            continue
        rows.append({
            "email": _norm_email(r.get("email")),
            "name": str(r.get("name", "")).strip(),
            "division": str(r.get("division", "")).strip(),
            "team": str(r.get("team", "")).strip(),
            "position": str(r.get("position", "")).strip(),
            "role": str(r.get("role", "")).strip().lower(),
        })
    rows.sort(key=lambda x: (x["division"], x["team"], x["name"]))
    return rows


def is_email_registered(email: str) -> bool:
    """조직도 활성 사용자 등록 여부. 회원가입 사전 게이트용."""
    return get_org_by_email_sheet(email) is not None


def clear_org_cache() -> None:
    """조직도 시트 수정 후 캐시 무효화."""
    _get_all_org_rows.clear()
    get_org_by_email_sheet.clear()
    get_all_org_members_sheet.clear()


# ======================================================================
# CASE STUDIES (case_studies 탭) — 11_CaseStudy.py 용
# BIGQUERY_MAPPING_SHEET_ID 시트에 case_studies 탭을 사용.
# 탭이 없으면 자동 생성.
# 스키마: A~Q
#   A id / B share_scope / C advertiser / D brand / E industry / F media
#   G target_gender / H target_age / I period_start / J period_end
#   K campaign_types(comma) / L objective / M strategy / N insight / O extra_note
#   P results_json / Q ai_json / R creative_image_url / S created_at
# ======================================================================
import json as _json

CASESTUDY_TAB = "case_studies"
CASESTUDY_HEADERS = [
    "id", "share_scope", "advertiser", "brand", "industry", "media",
    "target_gender", "target_age", "period_start", "period_end",
    "campaign_types", "objective", "strategy", "insight", "extra_note",
    "results_json", "ai_json", "creative_image_url", "created_at",
]


def _get_casestudy_sheet():
    gc, _ = _init()
    sh = gc.open_by_key(SHEET_ID)
    try:
        ws = sh.worksheet(CASESTUDY_TAB)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=CASESTUDY_TAB, rows=200, cols=len(CASESTUDY_HEADERS))
        ws.update(values=[CASESTUDY_HEADERS], range_name="A1")
    return ws


@st.cache_data(ttl=120)
def _get_casestudy_rows() -> list[dict]:
    ws = _get_casestudy_sheet()
    rows = ws.get_all_records()
    out = []
    for i, r in enumerate(rows):
        if not r.get("id"):
            continue
        r["_row"] = i + 2
        out.append(r)
    return out


def _parse_json_field(raw, default):
    if not raw:
        return default
    if isinstance(raw, (list, dict)):
        return raw
    try:
        return _json.loads(str(raw))
    except Exception:
        return default


def get_case_studies() -> list[dict]:
    out = []
    for r in _get_casestudy_rows():
        out.append({
            "id": str(r.get("id", "")).strip(),
            "row": r["_row"],
            "share_scope": str(r.get("share_scope", "Internal")).strip() or "Internal",
            "advertiser": str(r.get("advertiser", "")).strip(),
            "brand": str(r.get("brand", "")).strip(),
            "industry": str(r.get("industry", "")).strip(),
            "media": str(r.get("media", "")).strip(),
            "target_gender": str(r.get("target_gender", "")).strip(),
            "target_age": str(r.get("target_age", "")).strip(),
            "period_start": str(r.get("period_start", "")).strip(),
            "period_end": str(r.get("period_end", "")).strip(),
            "campaign_types": [t for t in str(r.get("campaign_types", "")).split(",") if t.strip()],
            "objective": str(r.get("objective", "")).strip(),
            "strategy": str(r.get("strategy", "")).strip(),
            "insight": str(r.get("insight", "")).strip(),
            "extra_note": str(r.get("extra_note", "")).strip(),
            "results": _parse_json_field(r.get("results_json"), []),
            "ai": _parse_json_field(r.get("ai_json"), {}),
            "creative_image_url": str(r.get("creative_image_url", "")).strip(),
            "created_at": str(r.get("created_at", "")).strip(),
        })
    out.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return out


def _clear_casestudy_cache():
    _get_casestudy_rows.clear()


def _cs_row(cs: dict) -> list:
    return [
        cs.get("id", ""),
        cs.get("share_scope", "Internal"),
        cs.get("advertiser", ""),
        cs.get("brand", ""),
        cs.get("industry", ""),
        cs.get("media", ""),
        cs.get("target_gender", ""),
        cs.get("target_age", ""),
        str(cs.get("period_start", "")),
        str(cs.get("period_end", "")),
        ",".join(cs.get("campaign_types", []) or []),
        cs.get("objective", ""),
        cs.get("strategy", ""),
        cs.get("insight", ""),
        cs.get("extra_note", ""),
        _json.dumps(cs.get("results", []), ensure_ascii=False),
        _json.dumps(cs.get("ai", {}), ensure_ascii=False),
        cs.get("creative_image_url", ""),
        cs.get("created_at", date.today().isoformat()),
    ]


def create_case_study(cs: dict) -> str:
    rows = _get_casestudy_rows()
    max_num = 0
    for r in rows:
        pid = str(r.get("id", ""))
        if pid.startswith("CS-"):
            try:
                max_num = max(max_num, int(pid.split("-")[1]))
            except (ValueError, IndexError):
                pass
    new_id = f"CS-{max_num + 1:04d}"
    cs = dict(cs)
    cs["id"] = new_id
    cs.setdefault("created_at", date.today().isoformat())
    ws = _get_casestudy_sheet()
    ws.append_row(_cs_row(cs), value_input_option="USER_ENTERED")
    _clear_casestudy_cache()
    return new_id


def update_case_study(row_num: int, cs: dict) -> None:
    ws = _get_casestudy_sheet()
    row = _cs_row(cs)
    end_col = chr(ord("A") + len(CASESTUDY_HEADERS) - 1)
    ws.update(values=[row], range_name=f"A{row_num}:{end_col}{row_num}", value_input_option="USER_ENTERED")
    _clear_casestudy_cache()


def delete_case_study(row_num: int) -> None:
    ws = _get_casestudy_sheet()
    ws.delete_rows(row_num)
    _clear_casestudy_cache()
