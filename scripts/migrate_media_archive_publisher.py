"""media_archive 탭 스키마 마이그레이션 — 배포주체 컬럼 추가 + 아젠다 구조 변경.

배경 (§17-17)
  utils/sheets.py:_get_media_archive_sheet() 는 헤더가 MEDIA_ARCHIVE_HEADERS 와 다르면
  ws.clear() 로 탭을 통째로 비운다. 운영 데이터가 쌓인 지금 상수를 먼저 고치면 전부 날아간다.
  → 반드시 이 스크립트로 시트를 먼저 옮긴 뒤 상수를 수정할 것.

하는 일
  1. publisher(배포주체) 컬럼을 맨 뒤에 추가하고 기존 전 행을 "디플랜360"으로 백필
     (기존 자료 동작에 영향이 없도록 하는 핵심. 파서 분기는 publisher != 디플랜360 일 때만 탄다)
  2. agenda_json 을 문자열 리스트 → [{"text":..., "newsroom":false}] 로 변환
     (아젠다별 [뉴스룸 연동] 체크를 담기 위함. 기존 항목은 전부 false)

안전장치
  - 기본은 드라이런. 실제 반영은 --apply
  - 반영 전 현재 탭 전체를 로컬 JSON 으로 백업
  - 이미 마이그레이션된 시트에 다시 돌려도 안전 (멱등)
  - 기존 컬럼(A~I)은 건드리지 않는다. agenda_json(F)과 신규 publisher(J)만 쓴다

사용법
  .venv/bin/python scripts/migrate_media_archive_publisher.py          # 드라이런
  .venv/bin/python scripts/migrate_media_archive_publisher.py --apply  # 실제 반영
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    import tomllib
except ModuleNotFoundError:  # py<3.11
    import tomli as tomllib  # type: ignore

import gspread
from google.oauth2 import service_account

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

TAB = "media_archive"
OLD_HEADERS = [
    "id", "year", "month", "title", "summary", "agenda_json",
    "drive_link", "published_date", "created_at",
]
NEW_HEADERS = OLD_HEADERS + ["publisher", "memo"]
DEFAULT_PUBLISHER = "디플랜360"

AGENDA_COL = OLD_HEADERS.index("agenda_json") + 1   # F = 6
PUB_COL = NEW_HEADERS.index("publisher") + 1        # J = 10


def _col_letter(n: int) -> str:
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _load_secrets() -> dict:
    with open(ROOT / ".streamlit" / "secrets.toml", "rb") as f:
        return tomllib.load(f)


def _normalize_agenda(raw) -> tuple[list[dict], bool]:
    """agenda_json 셀 값 → [{"text","newsroom"}] 로 정규화. (결과, 변경여부) 반환."""
    if not raw or not str(raw).strip():
        return [], False
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        # 파싱 불가 값은 손대지 않는다 (수기 입력 등)
        return [], False
    if not isinstance(data, list):
        return [], False

    out, changed = [], False
    for item in data:
        if isinstance(item, dict):
            out.append({
                "text": str(item.get("text", "")).strip(),
                "newsroom": bool(item.get("newsroom", False)),
            })
        else:
            out.append({"text": str(item).strip(), "newsroom": False})
            changed = True
    return [i for i in out if i["text"]], changed


def main() -> None:
    apply = "--apply" in sys.argv
    secrets = _load_secrets()

    sheet_id = str(secrets.get("PROMOTION_SHEET_ID", "")).strip()
    if not sheet_id:
        sys.exit("PROMOTION_SHEET_ID 가 secrets.toml 에 없습니다.")

    creds = service_account.Credentials.from_service_account_info(
        dict(secrets["gcp_service_account"]), scopes=SCOPES
    )
    gc = gspread.authorize(creds)
    ws = gc.open_by_key(sheet_id).worksheet(TAB)

    header = ws.row_values(1)
    print(f"현재 헤더: {header}")

    # 앱(_get_media_archive_sheet)과 동일한 안전 규칙: 신 스키마의 "접두사"면 확장 가능한 상태.
    # 앱이 이미 일부 컬럼을 덧붙여 둔 중간 상태(예: publisher 까지만 있는 경우)도 정상 처리한다.
    if header == NEW_HEADERS:
        print("→ 헤더는 최신입니다. 데이터만 점검합니다.")
    elif header and header == NEW_HEADERS[: len(header)]:
        print(f"→ 확장 가능한 상태입니다 (현재 {len(header)}개 / 최신 {len(NEW_HEADERS)}개).")
    else:
        sys.exit(
            "❌ 헤더가 예상과 다릅니다. 수동 확인이 필요합니다.\n"
            f"   기대(신): {NEW_HEADERS}"
        )

    records = ws.get_all_values()
    body = records[1:] if len(records) > 1 else []
    data_rows = [(i + 2, r) for i, r in enumerate(body) if r and r[0].strip()]
    print(f"데이터 행: {len(data_rows)}건")

    agenda_updates: list[tuple[int, str]] = []
    pub_updates: list[tuple[int, str]] = []

    for row_num, row in data_rows:
        raw_agenda = row[AGENDA_COL - 1] if len(row) >= AGENDA_COL else ""
        norm, changed = _normalize_agenda(raw_agenda)
        if changed:
            agenda_updates.append((row_num, json.dumps(norm, ensure_ascii=False)))

        cur_pub = row[PUB_COL - 1].strip() if len(row) >= PUB_COL else ""
        if not cur_pub:
            pub_updates.append((row_num, DEFAULT_PUBLISHER))

    print(f"  · agenda_json 변환 대상 : {len(agenda_updates)}건")
    print(f"  · publisher 백필 대상   : {len(pub_updates)}건")

    if data_rows:
        s_row, s_vals = data_rows[0]
        s_norm, _ = _normalize_agenda(s_vals[AGENDA_COL - 1] if len(s_vals) >= AGENDA_COL else "")
        print(f"\n[샘플 {s_row}행] {s_vals[3][:40] if len(s_vals) > 3 else ''}")
        print(f"  agenda: {json.dumps(s_norm[:2], ensure_ascii=False)}{' ...' if len(s_norm) > 2 else ''}")
        print(f"  publisher → {DEFAULT_PUBLISHER}")

    if not apply:
        print("\n=== 드라이런입니다. 실제 반영하려면 --apply ===")
        return

    backup = ROOT / f"media_archive_backup_{datetime.now():%Y%m%d-%H%M%S}.json"
    backup.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ 백업 저장: {backup}")

    # 1) 헤더 갱신 (publisher 추가) — 기존 A~I 값은 그대로 두고 J1 만 채운다
    if header != NEW_HEADERS:
        missing = NEW_HEADERS[len(header):]
        ws.update(values=[missing],
                  range_name=f"{_col_letter(len(header) + 1)}1")
        print(f"✅ 헤더에 {missing} 추가")

    # 2) agenda_json 변환
    if agenda_updates:
        ws.batch_update([
            {"range": f"{_col_letter(AGENDA_COL)}{r}", "values": [[v]]}
            for r, v in agenda_updates
        ], value_input_option="RAW")
        print(f"✅ agenda_json 변환 {len(agenda_updates)}건")

    # 3) publisher 백필
    if pub_updates:
        ws.batch_update([
            {"range": f"{_col_letter(PUB_COL)}{r}", "values": [[v]]}
            for r, v in pub_updates
        ], value_input_option="RAW")
        print(f"✅ publisher 백필 {len(pub_updates)}건")

    print("\n=== 마이그레이션 완료. 이제 utils/sheets.py 의 상수를 수정하세요. ===")


if __name__ == "__main__":
    main()
