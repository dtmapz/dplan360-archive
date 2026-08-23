#!/usr/bin/env python3
"""조직도 시트 → Supabase allowed_signup_emails 동기화 (스탠드얼론).

GitHub Actions에서 매일 실행. Streamlit 의존성 없음.

필요 환경변수:
- ORG_GCP_SERVICE_ACCOUNT_JSON: GCP 서비스계정 JSON (Base64 또는 raw JSON)
- ORG_SHEET_ID: 조직도 시트 ID
- ORG_TAB_NAME: 조직도 탭 이름 (기본 'organization')
- SUPABASE_URL: Supabase 프로젝트 URL
- SUPABASE_SERVICE_KEY: Supabase service_role 키 (RLS 우회 필요)
"""

import os
import sys
import json
import base64
import logging

import gspread
from google.oauth2 import service_account
from supabase import create_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


def _load_creds(raw: str):
    try:
        info = json.loads(raw)
    except json.JSONDecodeError:
        info = json.loads(base64.b64decode(raw).decode("utf-8"))
    return service_account.Credentials.from_service_account_info(info, scopes=SCOPES)


def _is_active(row: dict) -> bool:
    v = str(row.get("is_active", "")).strip().upper()
    return v == "Y" or v == ""


def _norm_email(v) -> str:
    return str(v or "").strip().lower()


def fetch_sheet_emails(sheet_id: str, tab: str, creds_json: str) -> set[str]:
    creds = _load_creds(creds_json)
    gc = gspread.authorize(creds)
    ws = gc.open_by_key(sheet_id).worksheet(tab)
    rows = ws.get_all_records()
    emails = set()
    for r in rows:
        email = _norm_email(r.get("email"))
        if email and _is_active(r):
            emails.add(email)
    return emails


def fetch_current_allowlist(sb) -> set[str]:
    res = sb.table("allowed_signup_emails").select("email").execute()
    return {row["email"] for row in (res.data or [])}


def main():
    sheet_id = os.environ["ORG_SHEET_ID"]
    tab = os.environ.get("ORG_TAB_NAME", "organization")
    creds_json = os.environ["ORG_GCP_SERVICE_ACCOUNT_JSON"]
    supabase_url = os.environ["SUPABASE_URL"]
    supabase_key = os.environ["SUPABASE_SERVICE_KEY"]

    log.info("조직도 시트 조회 (sheet=%s tab=%s)", sheet_id[:8] + "…", tab)
    sheet_emails = fetch_sheet_emails(sheet_id, tab, creds_json)
    log.info("활성 이메일 %d건 로드", len(sheet_emails))

    sb = create_client(supabase_url, supabase_key)
    current = fetch_current_allowlist(sb)
    log.info("현재 화이트리스트 %d건", len(current))

    to_add = sorted(sheet_emails - current)
    to_remove = sorted(current - sheet_emails)
    kept = len(sheet_emails & current)

    if to_add:
        sb.table("allowed_signup_emails").upsert(
            [{"email": e} for e in to_add]
        ).execute()
        log.info("추가 %d건: %s", len(to_add), ", ".join(to_add))

    if to_remove:
        sb.table("allowed_signup_emails").delete().in_("email", to_remove).execute()
        log.info("제거 %d건: %s", len(to_remove), ", ".join(to_remove))

    log.info("완료: 활성 %d · 추가 %d · 제거 %d · 유지 %d",
             len(sheet_emails), len(to_add), len(to_remove), kept)

    if not to_add and not to_remove:
        log.info("변경 없음")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        log.exception("동기화 실패: %s", e)
        sys.exit(1)
