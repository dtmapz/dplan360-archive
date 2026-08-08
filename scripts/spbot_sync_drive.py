"""SP봇 Drive PDF 크롤러 — GitHub Actions에서 1일 1회 실행.

동작:
1. 지정 Drive 폴더의 PDF 파일 목록 조회
2. 각 파일의 modifiedTime 확인 → 시트의 최종수정일과 비교
3. 신규 or 갱신된 PDF만 다운로드 → 텍스트 추출 → LLM 정제 → 시트 upsert
4. 새 카테고리 후보 시트 등록

환경변수 (GitHub Actions Secrets · 로컬 secrets.toml):
- GEMINI_API_KEY
- GCP_SERVICE_ACCOUNT_JSON
- SHEET_ID
- DRIVE_PDF_FOLDER_ID (SP봇용 Drive 폴더 ID)
"""
import io
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _setup_streamlit_secrets_from_env():
    """GitHub Actions 환경 지원 (spbot_sync_notion.py와 동일 패턴)."""
    secrets_dir = os.path.expanduser("~/.streamlit")
    os.makedirs(secrets_dir, exist_ok=True)
    secrets_path = os.path.join(secrets_dir, "secrets.toml")

    sa_json = os.environ.get("GCP_SERVICE_ACCOUNT_JSON", "")
    sheet_id = os.environ.get("SHEET_ID", "")
    gemini_key = os.environ.get("GEMINI_API_KEY", "")

    if not (sa_json and sheet_id and gemini_key):
        raise RuntimeError(
            "필수 환경변수 누락: GCP_SERVICE_ACCOUNT_JSON, SHEET_ID, GEMINI_API_KEY"
        )

    sa = json.loads(sa_json)
    lines = [
        f'BIGQUERY_MAPPING_SHEET_ID = {json.dumps(sheet_id)}',
        f'GEMINI_API_KEY = {json.dumps(gemini_key)}',
        f'NOTION_TOKEN = {json.dumps(os.environ.get("NOTION_TOKEN", ""))}',
        f'PROMOTION_SHEET_ID = {json.dumps(os.environ.get("PROMOTION_SHEET_ID", sheet_id))}',
        '',
        '[gcp_service_account]',
    ]
    for k, v in sa.items():
        lines.append(f'{k} = {json.dumps(v)}')
    with open(secrets_path, "w") as f:
        f.write("\n".join(lines) + "\n")


if os.environ.get("GITHUB_ACTIONS") == "true":
    _setup_streamlit_secrets_from_env()


import toml  # noqa: E402
from google.oauth2 import service_account  # noqa: E402
from googleapiclient.discovery import build  # noqa: E402
from googleapiclient.http import MediaIoBaseDownload  # noqa: E402
from pypdf import PdfReader  # noqa: E402

from utils.spbot_sheets import (  # noqa: E402
    get_all_docs,
    upsert_doc,
    get_approved_category_names,
    get_pending_category_names,
    add_category_if_new,
)
from utils.spbot_llm import summarize_doc  # noqa: E402


MAX_PDF_MB = 50  # 50MB 초과 파일은 스킵 (안전장치)


def _get_drive_folder_id() -> str:
    """secrets.toml 또는 환경변수에서 폴더 ID 로드."""
    folder_id = os.environ.get("DRIVE_PDF_FOLDER_ID", "").strip()
    if folder_id:
        return folder_id
    # 로컬 secrets.toml fallback
    for p in (
        os.path.expanduser("~/.streamlit/secrets.toml"),
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     ".streamlit/secrets.toml"),
    ):
        if os.path.exists(p):
            data = toml.load(p)
            folder_id = str(data.get("DRIVE_PDF_FOLDER_ID", "")).strip()
            if folder_id:
                return folder_id
    raise RuntimeError("DRIVE_PDF_FOLDER_ID가 설정되지 않았습니다.")


def _get_drive_service():
    """서비스 계정으로 Drive API 클라이언트 생성."""
    sa_json = os.environ.get("GCP_SERVICE_ACCOUNT_JSON", "")
    if sa_json:
        sa_info = json.loads(sa_json)
    else:
        # 로컬 secrets.toml fallback
        for p in (
            os.path.expanduser("~/.streamlit/secrets.toml"),
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         ".streamlit/secrets.toml"),
        ):
            if os.path.exists(p):
                data = toml.load(p)
                sa_info = dict(data.get("gcp_service_account") or {})
                break
        else:
            raise RuntimeError("GCP 서비스 계정 정보를 찾을 수 없습니다.")
    creds = service_account.Credentials.from_service_account_info(
        sa_info,
        scopes=["https://www.googleapis.com/auth/drive.readonly"],
    )
    return build("drive", "v3", credentials=creds)


def _list_pdfs_in_folder(drive, folder_id: str) -> list[dict]:
    """폴더 내 PDF 파일 목록. 하위 폴더는 재귀 안 함 (flat scan).
    반환: [{id, name, modifiedTime, webViewLink, size}]"""
    files = []
    page_token = None
    query = (
        f"'{folder_id}' in parents "
        "and mimeType='application/pdf' "
        "and trashed=false"
    )
    while True:
        resp = drive.files().list(
            q=query,
            fields="nextPageToken, files(id, name, modifiedTime, webViewLink, size)",
            pageSize=100,
            pageToken=page_token,
        ).execute()
        files.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return files


def _download_pdf_bytes(drive, file_id: str) -> bytes:
    request = drive.files().get_media(fileId=file_id)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buf.getvalue()


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    """pypdf로 텍스트 추출. 스캔 PDF는 빈 텍스트 반환됨 (OCR 미지원)."""
    reader = PdfReader(io.BytesIO(pdf_bytes))
    parts = []
    for page in reader.pages:
        text = page.extract_text() or ""
        if text.strip():
            parts.append(text)
    return "\n\n".join(parts).strip()


def run():
    folder_id = _get_drive_folder_id()
    drive = _get_drive_service()

    pdfs = _list_pdfs_in_folder(drive, folder_id)
    print(f"Drive 폴더에서 PDF {len(pdfs)}개 발견", flush=True)

    # 기존 시트 상태 로드 (원본링크 기준 modifiedTime 비교)
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
    total_failed = 0
    new_category_proposals = set()

    for f in pdfs:
        file_id = f["id"]
        name = f["name"]
        size = int(f.get("size", 0))
        modified_short = (f.get("modifiedTime") or "")[:10]  # YYYY-MM-DD
        source_link = f.get("webViewLink") or f"https://drive.google.com/file/d/{file_id}/view"

        # 크기 초과 스킵
        if size > MAX_PDF_MB * 1024 * 1024:
            print(f"  ⚠ 크기 초과 스킵 [{name}]: {size // 1024 // 1024}MB (제한 {MAX_PDF_MB}MB)",
                  flush=True)
            total_skipped += 1
            continue

        # 변경 없음 스킵
        if source_link in existing and existing[source_link] == modified_short:
            total_skipped += 1
            continue

        # 다운로드 + 텍스트 추출
        try:
            pdf_bytes = _download_pdf_bytes(drive, file_id)
            body = _extract_pdf_text(pdf_bytes)
        except Exception as e:
            print(f"  ! 다운로드/추출 실패 [{name}]: {e}", flush=True)
            total_failed += 1
            continue

        if not body.strip():
            print(f"  ⚠ 텍스트 없음 (스캔 PDF? OCR 미지원) 스킵 [{name}]", flush=True)
            total_skipped += 1
            continue

        # LLM 정제
        try:
            meta = summarize_doc(
                title_hint=name.rsplit(".", 1)[0],
                body_text=body,
                approved_categories=approved_cats,
                pending_categories=pending_cats,
            )
        except Exception as e:
            print(f"  ! LLM 실패 [{name}]: {e}", flush=True)
            total_failed += 1
            continue

        if meta.get("new_category_proposal"):
            new_category_proposals.add(meta["new_category_proposal"])

        _, action = upsert_doc(
            source_channel="Drive PDF",
            source_link=source_link,
            title=meta["title"] or name,
            summary=meta["summary"],
            category=meta["category"],
            keywords=meta["keywords"],
            body=body,
            status=meta["status"],
        )
        if action == "created":
            total_created += 1
            print(f"  ✓ 신규 [{name}]", flush=True)
        else:
            total_updated += 1
            print(f"  ↻ 갱신 [{name}]", flush=True)

    for cname in new_category_proposals:
        add_category_if_new(cname, initial_status="대기")

    print("=" * 40, flush=True)
    print(
        f"신규: {total_created} · 갱신: {total_updated} · "
        f"스킵: {total_skipped} · 실패: {total_failed}",
        flush=True,
    )
    if new_category_proposals:
        print(f"신규 카테고리 후보 (승인 대기): {sorted(new_category_proposals)}", flush=True)


if __name__ == "__main__":
    started = datetime.now().isoformat(timespec="seconds")
    print(f"SP봇 Drive PDF 동기화 시작 · {started}", flush=True)
    run()
    ended = datetime.now().isoformat(timespec="seconds")
    print(f"완료 · {ended}", flush=True)
