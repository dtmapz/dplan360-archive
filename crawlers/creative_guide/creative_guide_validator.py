"""
제작 가이드 검증기 — 시트 스펙 vs 웹 원본 비교
매일 05:00 KST 자동 실행 (GitHub Actions)
"""
import os
import json
import re
import sys
import logging
from datetime import datetime, timezone, timedelta
from base64 import b64decode

import gspread
import requests
from bs4 import BeautifulSoup
from google.oauth2 import service_account
from googleapiclient.discovery import build as build_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))
FOLDER_ID = "1DPwoSQd41b-GIe1P0wRMbql_iiCCCqCQ"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]
NOTIFY_EMAIL = "mj.park@d-plan360.com"

# ---------------------------------------------------------------------------
# 1. 인증
# ---------------------------------------------------------------------------

def _get_credentials():
    raw = os.environ.get("CG_GCP_SERVICE_ACCOUNT_JSON", "")
    if not raw:
        sys.exit("CG_GCP_SERVICE_ACCOUNT_JSON 환경변수 없음")
    info = json.loads(b64decode(raw))
    return service_account.Credentials.from_service_account_info(info, scopes=SCOPES)


def _init_clients(creds):
    gc = gspread.authorize(creds)
    drive = build_service("drive", "v3", credentials=creds)
    return gc, drive

# ---------------------------------------------------------------------------
# 2. Drive 폴더 → 시트/탭 목록
# ---------------------------------------------------------------------------

def list_sheets(drive):
    resp = drive.files().list(
        q=f"'{FOLDER_ID}' in parents and mimeType='application/vnd.google-apps.spreadsheet' and trashed=false",
        fields="files(id, name)",
        pageSize=100,
    ).execute()
    return resp.get("files", [])


def get_tab_data(gc, sheet_id):
    """시트의 모든 탭에서 (탭명, 참조URL, 스펙텍스트) 반환."""
    sh = gc.open_by_key(sheet_id)
    results = []
    for ws in sh.worksheets():
        rows = ws.get_all_values()
        ref_url = _extract_url(rows[3] if len(rows) > 3 else [])
        spec_text = _rows_to_text(rows[4:])  # 행5부터 스펙 데이터
        results.append({
            "tab": ws.title,
            "tab_gid": ws.id,
            "ref_url": ref_url,
            "spec_text": spec_text,
        })
    return results


def _extract_url(row_cells):
    """행4 셀들에서 URL 추출."""
    text = " ".join(row_cells)
    match = re.search(r"https?://[^\s,)]+", text)
    return match.group(0) if match else None


def _rows_to_text(rows):
    """행 리스트 → 비어있지 않은 셀만 연결."""
    lines = []
    for row in rows:
        cells = [c.strip() for c in row if c.strip()]
        if cells:
            lines.append(" | ".join(cells))
    return "\n".join(lines)

# ---------------------------------------------------------------------------
# 3. 웹 페이지 fetch
# ---------------------------------------------------------------------------

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
}


def fetch_web_content(url):
    """URL에서 텍스트 콘텐츠 추출. 실패 시 None."""
    if not url:
        return None
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        return text[:15000]  # 토큰 절약
    except Exception as e:
        log.warning(f"웹 fetch 실패 ({url}): {e}")
        return None

# ---------------------------------------------------------------------------
# 4. Gemini 비교
# ---------------------------------------------------------------------------

def compare_with_gemini(spec_text, web_text, tab_name, ref_url):
    """Gemini Flash로 스펙 변경사항 감지. 변경 없으면 None."""
    from google import genai
    from google.genai import types

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        sys.exit("GEMINI_API_KEY 환경변수 없음")

    client = genai.Client(api_key=api_key)
    model_id = "gemini-flash-latest"
    tools = [types.Tool(google_search=types.GoogleSearch())] if not web_text else None

    prompt = f"""당신은 광고 매체 제작 가이드 검증 담당자입니다.

## 역할
시트에 기록된 제작 가이드 스펙과 웹 원본(또는 웹 검색 결과)을 비교하여
**실질적인 변경사항만** 감지합니다.

## 감지 대상 (이것만 보고)
1. **숫자 변경**: 해상도, 용량, 비트레이트, 길이, 비율 등 수치가 달라진 경우
2. **필수 정보 추가**: 웹 원본에는 있지만 시트에 없는 새로운 필수 스펙/제한사항
3. **필수 정보 삭제**: 시트에는 있지만 웹 원본에서 폐지/제거된 스펙

## 감지 제외 (무시할 것)
- 문체/어투 차이 (같은 내용의 다른 표현)
- 항목 순서 변경
- 줄바꿈/공백/포맷 차이
- 부가 설명/팁/권장사항 (필수가 아닌 것)

## 시트 스펙 (탭: {tab_name})
{spec_text}

## 웹 원본 {'(URL: ' + ref_url + ')' if ref_url else '(웹 검색 기반)'}
{web_text if web_text else '(직접 접근 불가 — google_search로 최신 정보를 검색하세요)'}

## 출력 형식
변경사항이 있으면 아래 JSON 배열로 응답하세요. 없으면 빈 배열 [] 을 응답하세요.
반드시 JSON만 출력하세요. 마크다운 코드블록이나 설명 텍스트 없이 순수 JSON만.

[
  {{
    "type": "number_change" | "info_added" | "info_removed",
    "item": "변경 항목명",
    "old_value": "시트 기존값 (없으면 null)",
    "new_value": "웹 원본 값 (없으면 null)",
    "evidence": "근거 (웹 원본 문구 인용)"
  }}
]
"""

    try:
        response = client.models.generate_content(
            model=model_id,
            contents=prompt,
            config=types.GenerateContentConfig(tools=tools) if tools else None,
        )
        text = response.text.strip()
        # 코드블록 감싸져 있으면 제거
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        changes = json.loads(text)
        if isinstance(changes, list) and len(changes) > 0:
            return changes
        return None
    except json.JSONDecodeError:
        log.warning(f"Gemini 응답 파싱 실패 ({tab_name}): {response.text[:200]}")
        return None
    except Exception as e:
        log.error(f"Gemini 호출 실패 ({tab_name}): {e}")
        return None

# ---------------------------------------------------------------------------
# 5. 시트 기록
# ---------------------------------------------------------------------------

LOG_SHEET_ID = (
    os.environ.get("CG_LOG_SHEET_ID", "").strip()
    or os.environ.get("BIGQUERY_MAPPING_SHEET_ID", "").strip()
    or os.environ.get("SHEET_ID", "").strip()
)
if not LOG_SHEET_ID:
    raise RuntimeError("BIGQUERY_MAPPING_SHEET_ID (또는 CG_LOG_SHEET_ID) 환경변수 미설정")
LOG_TAB = "creative_guide_log"
TYPE_LABELS = {"number_change": "수치 변경", "info_added": "정보 추가", "info_removed": "정보 삭제"}


def _ensure_log_tab(gc):
    """로그 탭이 없으면 헤더와 함께 생성."""
    sh = gc.open_by_key(LOG_SHEET_ID)
    try:
        ws = sh.worksheet(LOG_TAB)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=LOG_TAB, rows=1000, cols=10)
        ws.append_row(
            ["검증일시", "시트명", "탭명", "유형", "항목", "기존값", "변경값", "근거", "탭링크", "알림발송"],
            value_input_option="RAW",
        )
        log.info(f"'{LOG_TAB}' 탭 생성 완료")
    return ws


def write_changes_to_sheet(gc, all_changes):
    """변경사항을 로그 탭에 기록. 알림발송 컬럼은 'N'으로 초기화."""
    ws = _ensure_log_tab(gc)
    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M")

    rows = []
    for c in all_changes:
        rows.append([
            now,
            c["sheet"],
            c["tab"],
            TYPE_LABELS.get(c["type"], c["type"]),
            c["item"],
            c.get("old_value") or "-",
            c.get("new_value") or "-",
            c.get("evidence", ""),
            c.get("tab_url", ""),
            "N",
        ])

    if rows:
        ws.append_rows(rows, value_input_option="RAW")
        log.info(f"시트 기록 완료: {len(rows)}건 → {LOG_TAB}")
    return len(rows)

# ---------------------------------------------------------------------------
# 6. 메인
# ---------------------------------------------------------------------------

def main():
    start = datetime.now(KST)
    log.info("=== 제작 가이드 검증 시작 ===")

    creds = _get_credentials()
    gc, drive = _init_clients(creds)

    sheets = list_sheets(drive)
    log.info(f"대상 시트: {len(sheets)}개")

    all_changes = []
    checked = 0

    for sheet_file in sheets:
        sheet_name = sheet_file["name"]
        log.info(f"📊 {sheet_name} 검증 중...")

        tabs = get_tab_data(gc, sheet_file["id"])
        for tab in tabs:
            log.info(f"  탭: {tab['tab']} (URL: {tab['ref_url'] or '없음'})")

            web_text = fetch_web_content(tab["ref_url"])

            changes = compare_with_gemini(
                spec_text=tab["spec_text"],
                web_text=web_text,
                tab_name=f"{sheet_name} > {tab['tab']}",
                ref_url=tab["ref_url"],
            )

            if changes:
                tab_url = f"https://docs.google.com/spreadsheets/d/{sheet_file['id']}/edit#gid={tab['tab_gid']}"
                for c in changes:
                    c["sheet"] = sheet_name
                    c["tab"] = tab["tab"]
                    c["tab_url"] = tab_url
                all_changes.extend(changes)
                log.info(f"    ⚠️ {len(changes)}건 변경 감지")
            else:
                log.info(f"    ✅ 변경 없음")

            checked += 1

    elapsed = (datetime.now(KST) - start).total_seconds()
    log.info(f"검증 완료: {checked}탭 / 변경 {len(all_changes)}건 / {elapsed:.1f}초")

    if all_changes:
        write_changes_to_sheet(gc, all_changes)
    else:
        log.info("변경 없음 — 기록 생략")


if __name__ == "__main__":
    main()
