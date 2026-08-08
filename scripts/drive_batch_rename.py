"""Drive 폴더 내 파일 일괄 리네임 유틸.

두 가지 모드:
  1) list   — 폴더 파일 목록을 지정 시트 탭에 저장
  2) rename — 시트 [변경파일명] 열에 값이 있는 행만 Drive에서 리네임 실행
              --dry-run 옵션: 실제 반영 없이 미리보기만

사용 예:
  python3 scripts/drive_batch_rename.py list --folder-id ABCXYZ --tab drive_rename
  python3 scripts/drive_batch_rename.py rename --tab drive_rename --dry-run
  python3 scripts/drive_batch_rename.py rename --tab drive_rename

폴더 ID를 매번 넘기기 귀찮으면 secrets.toml에 DRIVE_RENAME_FOLDER_ID로 등록.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import toml  # noqa: E402
import gspread  # noqa: E402
from google.oauth2 import service_account  # noqa: E402
from googleapiclient.discovery import build  # noqa: E402


HEADERS = ["파일ID", "현재파일명", "변경파일명", "상태"]


def _load_secrets() -> dict:
    for p in (
        os.path.expanduser("~/.streamlit/secrets.toml"),
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     ".streamlit/secrets.toml"),
    ):
        if os.path.exists(p):
            return toml.load(p)
    raise RuntimeError("secrets.toml을 찾을 수 없습니다.")


def _get_drive_and_sheet_clients(secrets: dict):
    sa_info = dict(secrets.get("gcp_service_account") or {})
    if not sa_info:
        raise RuntimeError("gcp_service_account 정보 없음.")
    scopes = [
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/spreadsheets",
    ]
    creds = service_account.Credentials.from_service_account_info(sa_info, scopes=scopes)
    drive = build("drive", "v3", credentials=creds)
    gc = gspread.authorize(creds)
    return drive, gc


def _get_sheet_by_id(gc, sheet_id: str, tab_name: str):
    """탭이 없으면 자동 생성."""
    sh = gc.open_by_key(sheet_id)
    try:
        ws = sh.worksheet(tab_name)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=tab_name, rows=1000, cols=len(HEADERS))
        ws.update(values=[HEADERS], range_name="A1:D1", value_input_option="USER_ENTERED")
        print(f"신규 탭 생성: {tab_name}")
    return ws


def _list_files(drive, folder_id: str) -> list[dict]:
    files = []
    page_token = None
    query = f"'{folder_id}' in parents and trashed=false"
    while True:
        resp = drive.files().list(
            q=query,
            fields="nextPageToken, files(id, name, mimeType)",
            pageSize=100,
            pageToken=page_token,
            orderBy="name",
        ).execute()
        files.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return files


def cmd_list(args, secrets):
    drive, gc = _get_drive_and_sheet_clients(secrets)
    folder_id = args.folder_id or secrets.get("DRIVE_RENAME_FOLDER_ID", "")
    if not folder_id:
        sys.exit("--folder-id 필수 (또는 secrets.toml의 DRIVE_RENAME_FOLDER_ID 설정)")

    files = _list_files(drive, folder_id)
    print(f"폴더에서 {len(files)}개 항목 발견")

    sheet_id = secrets["BIGQUERY_MAPPING_SHEET_ID"]
    ws = _get_sheet_by_id(gc, sheet_id, args.tab)

    # 기존 시트 파일ID 세트 (중복 방지)
    existing_records = ws.get_all_records()
    existing_ids = {str(r.get("파일ID", "")).strip() for r in existing_records if r.get("파일ID")}

    new_rows = []
    for f in files:
        if f["id"] in existing_ids:
            continue
        new_rows.append([f["id"], f["name"], "", ""])  # 변경파일명·상태 비워둠

    if not new_rows:
        print("신규 등록할 파일 없음 (모두 시트에 이미 있음)")
        return

    # 헤더 없으면 먼저 세팅
    header_row = ws.row_values(1)
    if not header_row:
        ws.update(values=[HEADERS], range_name="A1:D1", value_input_option="USER_ENTERED")

    ws.append_rows(new_rows, value_input_option="USER_ENTERED")
    print(f"시트에 {len(new_rows)}개 행 추가 · 탭: {args.tab}")
    print(f"→ 시트에서 [변경파일명] 열 채운 뒤 rename 명령 실행")


def cmd_rename(args, secrets):
    drive, gc = _get_drive_and_sheet_clients(secrets)
    sheet_id = secrets["BIGQUERY_MAPPING_SHEET_ID"]
    ws = _get_sheet_by_id(gc, sheet_id, args.tab)

    records = ws.get_all_records()
    if not records:
        sys.exit("시트가 비어있음")

    targets = []
    for i, r in enumerate(records):
        file_id = str(r.get("파일ID", "")).strip()
        current_name = str(r.get("현재파일명", "")).strip()
        new_name = str(r.get("변경파일명", "")).strip()
        status = str(r.get("상태", "")).strip()
        if not file_id or not new_name or new_name == current_name:
            continue
        if status == "완료":
            continue
        targets.append({
            "row": i + 2,
            "file_id": file_id,
            "current": current_name,
            "new": new_name,
        })

    if not targets:
        print("리네임 대상 없음 ([변경파일명] 비어있거나 이미 완료)")
        return

    print(f"리네임 대상: {len(targets)}개")
    for t in targets[:5]:
        print(f"  {t['current']}  →  {t['new']}")
    if len(targets) > 5:
        print(f"  ... 외 {len(targets)-5}개")

    if args.dry_run:
        print("\n[DRY RUN] 실제 반영 안 함. --dry-run 없이 다시 실행하면 반영됨")
        return

    print("\n실제 리네임 진행...")
    success = 0
    failed = []
    status_updates = []
    for t in targets:
        try:
            drive.files().update(
                fileId=t["file_id"],
                body={"name": t["new"]},
                fields="id, name",
            ).execute()
            success += 1
            status_updates.append((t["row"], "완료"))
            print(f"  ✓ {t['current']} → {t['new']}")
        except Exception as e:
            failed.append((t, str(e)))
            status_updates.append((t["row"], f"실패: {e}"))
            print(f"  ✗ {t['current']}: {e}")

    # 상태 열 일괄 업데이트
    for row_num, status in status_updates:
        ws.update_cell(row_num, 4, status)  # D열

    print(f"\n완료: {success} · 실패: {len(failed)}")


def main():
    parser = argparse.ArgumentParser(description="Drive 폴더 일괄 리네임 유틸")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="폴더 파일 목록을 시트에 저장")
    p_list.add_argument("--folder-id", help="Drive 폴더 ID (또는 secrets.toml의 DRIVE_RENAME_FOLDER_ID)")
    p_list.add_argument("--tab", default="drive_rename", help="시트 탭 이름 (기본: drive_rename)")

    p_rename = sub.add_parser("rename", help="시트 [변경파일명] 값으로 Drive 파일 리네임")
    p_rename.add_argument("--tab", default="drive_rename", help="시트 탭 이름")
    p_rename.add_argument("--dry-run", action="store_true", help="실제 반영 없이 미리보기")

    args = parser.parse_args()
    secrets = _load_secrets()

    if args.cmd == "list":
        cmd_list(args, secrets)
    elif args.cmd == "rename":
        cmd_rename(args, secrets)


if __name__ == "__main__":
    main()
