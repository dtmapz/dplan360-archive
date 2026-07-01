import streamlit as st
from supabase import create_client, Client


@st.cache_resource
def get_client() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)


# ---------- categories ----------

def get_all_categories() -> list[dict]:
    sb = get_client()
    res = sb.table("categories").select("*").order("major_category").order("sub_category").execute()
    return res.data


def get_major_categories() -> list[str]:
    cats = get_all_categories()
    seen = []
    for c in cats:
        if c["major_category"] not in seen:
            seen.append(c["major_category"])
    return seen


def get_sub_categories(major: str) -> list[str]:
    cats = get_all_categories()
    return sorted({c["sub_category"] for c in cats if c["major_category"] == major and c["sub_category"]})


def get_or_create_category(major: str, sub: str | None) -> str:
    """(major, sub) 조합이 있으면 id 반환, 없으면 새로 생성 후 id 반환"""
    sb = get_client()
    q = sb.table("categories").select("id").eq("major_category", major)
    q = q.is_("sub_category", "null") if not sub else q.eq("sub_category", sub)
    existing = q.execute()
    if existing.data:
        return existing.data[0]["id"]
    inserted = sb.table("categories").insert({"major_category": major, "sub_category": sub}).execute()
    return inserted.data[0]["id"]


def add_major_category(major: str) -> None:
    """새 대분류만 생성(중분류 없음). 이미 있으면 무시."""
    get_or_create_category(major, None)


def add_sub_category(major: str, sub: str) -> None:
    get_or_create_category(major, sub)


# ---------- media + contacts ----------

def search_media(keyword: str) -> list[dict]:
    """매체명뿐 아니라 대분류/중분류 카테고리명으로도 검색 가능.
    결과는 마지막컨택이력 최신순으로 정렬(값 없는 행은 맨 뒤)."""
    sb = get_client()

    # 1) 매체명 직접 매칭
    name_match = (
        sb.table("media")
        .select("*, categories(major_category, sub_category), contacts(*)")
        .ilike("name", f"%{keyword}%")
        .execute()
    ).data

    # 2) 카테고리명(대분류/중분류) 매칭 -> 해당 카테고리에 속한 매체 전체
    cat_match = (
        sb.table("categories")
        .select("id")
        .or_(f"major_category.ilike.%{keyword}%,sub_category.ilike.%{keyword}%")
        .execute()
    ).data
    cat_ids = [c["id"] for c in cat_match]
    cat_media = []
    if cat_ids:
        cat_media = (
            sb.table("media")
            .select("*, categories(major_category, sub_category), contacts(*)")
            .in_("category_id", cat_ids)
            .execute()
        ).data

    merged = {m["id"]: m for m in name_match + cat_media}
    results = list(merged.values())

    def sort_key(m):
        contact = (m.get("contacts") or [{}])[0] if m.get("contacts") else {}
        d = contact.get("last_contact_date")
        return (d is None, d or "")  # None은 뒤로, 나머지는 최신순(내림차순)

    results.sort(key=sort_key, reverse=True)
    return results


def get_media_by_category(major: str) -> list[dict]:
    """대분류 기준 전체 매체 (category 조인 포함), 매체명 가나다순"""
    sb = get_client()
    res = (
        sb.table("media")
        .select("*, categories!inner(major_category, sub_category), contacts(*)")
        .eq("categories.major_category", major)
        .order("name")
        .execute()
    )
    return res.data


def get_media_detail(media_id: str) -> dict:
    sb = get_client()
    res = (
        sb.table("media")
        .select("*, categories(major_category, sub_category), contacts(*)")
        .eq("id", media_id)
        .single()
        .execute()
    )
    return res.data


def create_media(name: str, major: str, sub: str | None, intro_doc_url: str | None,
                  manager_name: str, position: str | None, phone: str | None,
                  email: str | None, team_email: str | None, last_contact_date: str | None) -> str:
    sb = get_client()
    category_id = get_or_create_category(major, sub)
    media_row = sb.table("media").insert({
        "name": name, "category_id": category_id, "intro_doc_url": intro_doc_url,
    }).execute()
    media_id = media_row.data[0]["id"]
    sb.table("contacts").insert({
        "media_id": media_id, "manager_name": manager_name, "position": position,
        "phone": phone, "email": email, "team_email": team_email,
        "last_contact_date": last_contact_date or None,
    }).execute()
    return media_id


def update_media(media_id: str, name: str, major: str, sub: str | None, intro_doc_url: str | None) -> None:
    sb = get_client()
    category_id = get_or_create_category(major, sub)
    sb.table("media").update({
        "name": name, "category_id": category_id, "intro_doc_url": intro_doc_url,
        "updated_at": "now()",
    }).eq("id", media_id).execute()


def upsert_contact(contact_id: str | None, media_id: str, manager_name: str, position: str | None,
                    phone: str | None, email: str | None, team_email: str | None,
                    last_contact_date: str | None) -> None:
    sb = get_client()
    payload = {
        "media_id": media_id, "manager_name": manager_name, "position": position,
        "phone": phone, "email": email, "team_email": team_email,
        "last_contact_date": last_contact_date or None,
    }
    if contact_id:
        sb.table("contacts").update(payload).eq("id", contact_id).execute()
    else:
        sb.table("contacts").insert(payload).execute()


def get_all_media() -> list[dict]:
    """전체 매체를 한 번에 조회 (마일스톤 페이지 전용)"""
    sb = get_client()
    res = (
        sb.table("media")
        .select("*, categories(major_category, sub_category), contacts(*)")
        .order("name")
        .execute()
    )
    return res.data
