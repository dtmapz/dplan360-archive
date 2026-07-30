"""
Phase 1 마이그레이션 사전 검증 — 시트 3개 탭 구조 크로스체크
실행: python scripts/check_sheet_structure.py
"""
from pathlib import Path
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
with open(ROOT / ".streamlit" / "secrets.toml", "rb") as f:
    secrets = tomllib.load(f)

SHEET_ID = secrets["BIGQUERY_MAPPING_SHEET_ID"]
GCP_SA = dict(secrets["gcp_service_account"])

from google.oauth2 import service_account
import gspread

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

EXPECTED = {
    "category": ["카테고리ID", "대분류", "중분류"],
    "media_info": [
        "매체ID", "카테고리ID", "매체명", "소개서링크", "업데이트일자",
        "담당자이름", "직급", "전화번호", "이메일", "팀메일", "최근연락일",
    ],
    "creative_guide": ["매체ID", "매체명", "상품명", "스프레드시트ID"],
}


def main():
    creds = service_account.Credentials.from_service_account_info(GCP_SA, scopes=SCOPES)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SHEET_ID)

    all_titles = [ws.title for ws in sh.worksheets()]
    print(f"[Sheet 전체 탭] {all_titles}\n")

    print("=" * 70)
    print("탭별 헤더 검증 (기대 컬럼 vs 실제 헤더)")
    print("=" * 70)

    all_ok = True
    for tab, expected_cols in EXPECTED.items():
        print(f"\n[{tab}]")
        if tab not in all_titles:
            print(f"  ❌ 탭 없음")
            all_ok = False
            continue
        ws = sh.worksheet(tab)
        actual = ws.row_values(1)
        # 정확한 순서 비교
        if actual[:len(expected_cols)] == expected_cols:
            print(f"  ✓ 헤더 순서 완전 일치: {actual[:len(expected_cols)]}")
            if len(actual) > len(expected_cols):
                print(f"  ℹ️  추가 컬럼(사용 안 함): {actual[len(expected_cols):]}")
        else:
            print(f"  ❌ 불일치")
            print(f"    기대: {expected_cols}")
            print(f"    실제: {actual}")
            all_ok = False

        # 행 수
        row_count = len(ws.get_all_values()) - 1  # 헤더 제외
        print(f"  📊 데이터 행수: {row_count}")

    print("\n" + "=" * 70)
    if all_ok:
        print("✅ 모든 탭 헤더 검증 통과 — Phase 1 마이그레이션 준비 완료")
    else:
        print("❌ 시트 구조 수정 필요 — 위 오류 확인 후 시트 조정")
    print("=" * 70)

    # 추가 샘플 확인
    print("\n[creative_guide 스프레드시트ID 컬럼 샘플 3개]")
    ws_cg = sh.worksheet("creative_guide")
    cg_rows = ws_cg.get_all_records()[:3]
    for r in cg_rows:
        url = r.get("스프레드시트ID", "")
        is_full_url = "docs.google.com/spreadsheets/d/" in url
        print(f"  {r.get('매체명', '?')} · {r.get('상품명', '?')}: "
              f"{'✓ 전체 URL' if is_full_url else '⚠️ URL 아님'} — {url[:60]}...")


if __name__ == "__main__":
    main()
