"""조직도 시트 → Supabase allowed_signup_emails 동기화.

- Streamlit 관리자 페이지의 '동기화' 버튼과 GitHub Actions 워크플로우가
  같은 함수를 호출한다.
- 활성 사용자(is_active=Y/공란)의 이메일을 upsert하고,
  시트에서 사라진(또는 비활성 처리된) 이메일은 삭제한다.
- 삭제는 화이트리스트만 대상. 이미 존재하는 auth.users 계정은 건드리지 않음.
"""

from utils.db import get_service_client
from utils.sheets import get_all_org_members_sheet, clear_org_cache


def sync_allowlist() -> dict:
    """조직도 → Supabase 화이트리스트 반영.

    Returns:
        {"total": N, "added": [emails], "removed": [emails], "kept": N}
    """
    # 시트 캐시 무효화 후 최신값으로 조회
    clear_org_cache()
    members = get_all_org_members_sheet()
    sheet_emails = {m["email"] for m in members if m.get("email")}

    sb = get_service_client()

    # 현재 화이트리스트
    res = sb.table("allowed_signup_emails").select("email").execute()
    current = {row["email"] for row in (res.data or [])}

    to_add = sorted(sheet_emails - current)
    to_remove = sorted(current - sheet_emails)

    if to_add:
        sb.table("allowed_signup_emails").upsert(
            [{"email": e} for e in to_add]
        ).execute()

    if to_remove:
        (
            sb.table("allowed_signup_emails")
            .delete()
            .in_("email", to_remove)
            .execute()
        )

    return {
        "total": len(sheet_emails),
        "added": to_add,
        "removed": to_remove,
        "kept": len(sheet_emails & current),
    }
