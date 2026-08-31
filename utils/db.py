import streamlit as st
from supabase import create_client, Client


@st.cache_resource
def get_client() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)


@st.cache_resource
def get_service_client() -> Client:
    """service_role 키 클라이언트. RLS 우회 필요한 관리 작업 전용.
    (예: allowed_signup_emails 화이트리스트 upsert)
    """
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_SERVICE_KEY"]
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


# ---------- creative_guides ----------

def get_creative_guides() -> list[dict]:
    sb = get_client()
    res = (
        sb.table("creative_guides")
        .select("*")
        .order("media_name")
        .order("product_name")
        .execute()
    )
    return res.data


def create_creative_guide(media_name: str, category: str | None,
                          product_name: str, storage_path: str) -> None:
    sb = get_client()
    sb.table("creative_guides").insert({
        "media_name": media_name,
        "category": category,
        "product_name": product_name,
        "storage_path": storage_path,
    }).execute()


def update_creative_guide(guide_id: str, storage_path: str) -> None:
    sb = get_client()
    sb.table("creative_guides").update({
        "storage_path": storage_path,
        "uploaded_at": "now()",
    }).eq("id", guide_id).execute()


def delete_creative_guide(guide_id: str) -> None:
    sb = get_client()
    sb.table("creative_guides").delete().eq("id", guide_id).execute()


def upload_to_storage(bucket: str, path: str, data: bytes) -> str:
    """Storage에 파일 업로드 후 경로 반환"""
    sb = get_client()
    sb.storage.from_(bucket).upload(path, data, {"upsert": "true"})
    return path


def download_from_storage(bucket: str, path: str) -> bytes:
    """Storage에서 파일 다운로드"""
    sb = get_client()
    return sb.storage.from_(bucket).download(path)


def delete_from_storage(bucket: str, path: str) -> None:
    sb = get_client()
    sb.storage.from_(bucket).remove([path])

def get_all_media() -> list[dict]:
    sb = get_client()
    res = (
        sb.table("media")
        .select("*, categories(major_category, sub_category), contacts(*)")
        .order("name")
        .execute()
    )
    return res.data

def update_creative_guide_name(guide_id, new_product_name):
    return get_client().table("creative_guides").update(
        {"product_name": new_product_name}
    ).eq("id", guide_id).execute()


def delete_creative_guide(guide_id):
    return get_client().table("creative_guides").delete().eq("id", guide_id).execute()


# ---------- organization (report download 담당자 필터용) ----------
# 조직도 원본은 Google Sheets (ORG_SHEET_ID). 이 래퍼는 기존 호출부 호환용.
# 신규 코드는 utils.sheets.get_org_by_email_sheet 를 직접 사용해도 무방.


def get_org_by_email(email: str) -> dict | None:
    from utils.sheets import get_org_by_email_sheet
    return get_org_by_email_sheet(email)


# ---------- media hub 이미지 업로드 (Supabase Storage) ----------

MEDIA_HUB_IMAGE_BUCKET = "media-hub-images"
ALLOWED_IMAGE_EXTS = {"png", "jpg", "jpeg", "gif", "webp"}
MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5MB


def upload_notice_image(file_bytes: bytes, filename: str) -> str:
    """미디어허브 공지용 이미지 업로드 → 공개 URL 반환.
    파일명은 UUID 기반 (한글 경로/이름 방지, CLAUDE.md §2 규칙).
    """
    import uuid
    if not filename or "." not in filename:
        raise ValueError("파일명 확장자를 확인할 수 없습니다.")
    ext = filename.rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_IMAGE_EXTS:
        raise ValueError(f"지원하지 않는 형식: {ext} (허용: {', '.join(sorted(ALLOWED_IMAGE_EXTS))})")
    if len(file_bytes) > MAX_IMAGE_SIZE:
        raise ValueError(f"파일 크기 초과: {len(file_bytes)//1024}KB (제한 5MB)")

    key = f"{uuid.uuid4()}.{'jpg' if ext == 'jpeg' else ext}"
    sb = get_client()
    sb.storage.from_(MEDIA_HUB_IMAGE_BUCKET).upload(
        path=key,
        file=file_bytes,
        file_options={"content-type": f"image/{'jpeg' if ext == 'jpg' else ext}"},
    )
    return sb.storage.from_(MEDIA_HUB_IMAGE_BUCKET).get_public_url(key)


# ======================================================================
# MEDIA GUIDE PDF (media-guide-files 버킷)
# ======================================================================

MEDIA_GUIDE_BUCKET = "media-guide-files"
MAX_GUIDE_FILE_SIZE = 20 * 1024 * 1024  # 20MB


def upload_guide_file(file_bytes: bytes, filename: str) -> str:
    """가이드 PDF 업로드 → storage_path 반환 (UUID 파일명, PDF only)."""
    import uuid
    if not filename or not filename.lower().endswith(".pdf"):
        raise ValueError("PDF 파일만 업로드 가능합니다.")
    if len(file_bytes) > MAX_GUIDE_FILE_SIZE:
        raise ValueError(f"파일 크기 초과: {len(file_bytes)//1024//1024}MB (제한 20MB)")

    key = f"{uuid.uuid4()}.pdf"
    sb = get_client()
    sb.storage.from_(MEDIA_GUIDE_BUCKET).upload(
        path=key,
        file=file_bytes,
        file_options={"content-type": "application/pdf"},
    )
    return key


def download_guide_file(storage_path: str) -> bytes:
    sb = get_client()
    return sb.storage.from_(MEDIA_GUIDE_BUCKET).download(storage_path)


def delete_guide_file(storage_path: str) -> None:
    sb = get_client()
    sb.storage.from_(MEDIA_GUIDE_BUCKET).remove([storage_path])


def get_all_org_members() -> list[dict]:
    """organization 전체 조회 (admin impersonate용). 조직도는 Sheets가 원본."""
    from utils.sheets import get_all_org_members_sheet
    return get_all_org_members_sheet()


# ---------- Supabase auth 관리 (관리자 페이지 전용) ----------

def list_auth_last_sign_in() -> dict[str, str]:
    """Supabase auth.users 전체를 훑어 {email(소문자): last_sign_in_at(ISO)} 반환.
    service_role 키 필요. 페이지네이션 1페이지=1000명까지 지원.
    """
    sb = get_service_client()
    result: dict[str, str] = {}
    page = 1
    while True:
        try:
            resp = sb.auth.admin.list_users(page=page, per_page=1000)
        except TypeError:
            resp = sb.auth.admin.list_users()
        users = getattr(resp, "users", None) or resp
        if not users:
            break
        for u in users:
            email = (getattr(u, "email", None) or "").strip().lower()
            if not email:
                continue
            last = getattr(u, "last_sign_in_at", None) or ""
            result[email] = str(last) if last else ""
        if len(users) < 1000:
            break
        page += 1
        if page > 20:
            break
    return result


def delete_auth_user(email: str) -> bool:
    """이메일로 auth.users 계정 삭제. 없으면 False."""
    email_norm = (email or "").strip().lower()
    if not email_norm:
        return False
    sb = get_service_client()
    resp = sb.auth.admin.list_users(page=1, per_page=1000)
    users = getattr(resp, "users", None) or resp
    for u in users or []:
        if (getattr(u, "email", "") or "").strip().lower() == email_norm:
            sb.auth.admin.delete_user(u.id)
            return True
    return False
