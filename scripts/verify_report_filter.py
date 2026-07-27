"""
Report Download 담당팀 필터 검증 스크립트 (로컬 실행 전용)

용도:
- 매핑 시트의 담당본부/담당팀 값과 organization 테이블 정합성 체크
- 각 팀/개인 로그인 시 어떤 광고주가 보일지 시뮬레이션
- 시트 담당 배정 대량 수정 후 오타/미매칭 자동 감지

실행:
    source .venv/bin/activate
    python scripts/verify_report_filter.py

주의:
- .streamlit/secrets.toml 필요 (Streamlit Cloud 접근 X)
- organization은 RLS 보호 → 실행 중 앱 계정으로 로그인 필요
"""
from pathlib import Path
import sys
import tomllib


ROOT = Path(__file__).resolve().parents[1]
SECRETS_PATH = ROOT / ".streamlit" / "secrets.toml"

if not SECRETS_PATH.exists():
    print(f"❌ secrets.toml 없음: {SECRETS_PATH}")
    sys.exit(1)

with open(SECRETS_PATH, "rb") as f:
    secrets = tomllib.load(f)

SHEET_ID = secrets.get("BIGQUERY_MAPPING_SHEET_ID")
SHEET_NAME = secrets.get("BIGQUERY_MAPPING_SHEET_NAME", "bigquery")
SUPABASE_URL = secrets["SUPABASE_URL"]
SUPABASE_KEY = secrets["SUPABASE_KEY"]
GCP_SA = dict(secrets["gcp_service_account"])

from google.oauth2 import service_account
import gspread
from supabase import create_client

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

DIVISION_LEVEL_POSITIONS = {"실장", "본부장"}


def load_mapping():
    creds = service_account.Credentials.from_service_account_info(GCP_SA, scopes=SCOPES)
    gc = gspread.authorize(creds)
    ws = gc.open_by_key(SHEET_ID).worksheet(SHEET_NAME)
    return ws.get_all_records()


def load_organization():
    """organization은 RLS 보호. 로그인해야 조회 가능."""
    import getpass
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("\n[organization 조회] RLS 보호 테이블 → 로그인 필요")
    email = input("  이메일 (@d-plan360.com): ").strip()
    password = getpass.getpass("  비밀번호: ")
    try:
        sb.auth.sign_in_with_password({"email": email, "password": password})
    except Exception as e:
        print(f"  ❌ 로그인 실패: {e}")
        return []
    print("  ✓ 로그인 성공")
    res = sb.table("organization").select("division, team, name, position, email").execute()
    try:
        sb.auth.sign_out()
    except Exception:
        pass
    return res.data


def unique_advertisers(rows):
    seen = set()
    for r in rows:
        adv = str(r.get("광고주명", "")).strip()
        if adv and adv != "종료":
            seen.add(adv)
    return sorted(seen)


def filter_for(mapping, division, team, position):
    """실제 앱 로직과 동일한 필터. admin은 별도 처리."""
    if position in DIVISION_LEVEL_POSITIONS:
        return [
            r for r in mapping
            if str(r.get("담당본부", "")).strip() == division
        ]
    return [
        r for r in mapping
        if str(r.get("담당본부", "")).strip() == division
        and str(r.get("담당팀", "")).strip() == team
    ]


def main():
    print("=" * 70)
    print("📊 Report Download 담당팀 필터 검증")
    print("=" * 70)

    mapping = load_mapping()
    print(f"\n✓ 매핑 시트 로드: {len(mapping)}행")

    org = load_organization()
    print(f"✓ organization 로드: {len(org)}명")

    # --- 1. 매핑 시트 담당본부/담당팀 컬럼 존재 확인 ---
    if mapping:
        cols = list(mapping[0].keys())
        print(f"\n[시트 컬럼] {cols}")
        for required in ["담당본부", "담당팀", "광고주명"]:
            if required not in cols:
                print(f"  ❌ 필수 컬럼 누락: {required}")
                sys.exit(1)
        print("  ✓ 필수 컬럼 존재")

    # --- 2. 시트 담당본부/담당팀 유니크 값 ---
    sheet_divisions = sorted({str(r.get("담당본부", "")).strip() for r in mapping} - {""})
    sheet_teams = sorted({
        (str(r.get("담당본부", "")).strip(), str(r.get("담당팀", "")).strip())
        for r in mapping
        if str(r.get("담당본부", "")).strip() and str(r.get("담당팀", "")).strip()
    })
    print(f"\n[시트 담당본부 유니크] {sheet_divisions}")
    print(f"[시트 담당본부+담당팀 조합] {len(sheet_teams)}개")
    for d, t in sheet_teams:
        cnt = sum(
            1 for r in mapping
            if str(r.get("담당본부", "")).strip() == d
            and str(r.get("담당팀", "")).strip() == t
        )
        print(f"  - {d} {t}: {cnt}행")

    # 담당본부/팀 미지정 행
    blank_rows = [
        r for r in mapping
        if not str(r.get("담당본부", "")).strip() or not str(r.get("담당팀", "")).strip()
    ]
    if blank_rows:
        print(f"\n⚠️  담당본부/담당팀 미지정 행 {len(blank_rows)}개 (필터 시 아무한테도 안 보임)")
        for r in blank_rows[:5]:
            print(f"  - {r.get('매체명')} / {r.get('광고계정명')} / 광고주={r.get('광고주명')}")
        if len(blank_rows) > 5:
            print(f"  ... 외 {len(blank_rows)-5}개")

    # --- 3. organization 유니크 조합 ---
    org_divisions = sorted({r["division"] for r in org if r.get("division")})
    org_teams = sorted({
        (r["division"], r["team"])
        for r in org
        if r.get("division") and r.get("team")
    })
    print(f"\n[organization 담당본부 유니크] {org_divisions}")
    print(f"[organization 담당본부+팀 조합] {len(org_teams)}개")

    # --- 4. 정합성 체크: 시트 값이 organization에 존재하나? ---
    print("\n" + "=" * 70)
    print("🔎 정합성 체크 (시트 담당본부/팀 값 → organization 존재 여부)")
    print("=" * 70)
    org_team_set = set(org_teams)
    missing = [pair for pair in sheet_teams if pair not in org_team_set]
    if missing:
        print(f"❌ organization에 매칭되는 팀이 없는 시트 값 {len(missing)}개:")
        for d, t in missing:
            print(f"  - {d} / {t}")
    else:
        print("✓ 시트의 모든 담당본부/팀 조합이 organization에 존재")

    unused = [pair for pair in org_teams if pair not in {(d, t) for d, t in sheet_teams}]
    if unused:
        print(f"\nℹ️  organization에는 있지만 시트 담당 광고주 없는 팀 {len(unused)}개:")
        for d, t in unused:
            print(f"  - {d} / {t}")

    # --- 5. 팀별 시뮬레이션: 각 팀 구성원이 로그인하면 몇 개 광고주 보임? ---
    print("\n" + "=" * 70)
    print("👥 팀별 시뮬레이션 (일반 팀원 관점)")
    print("=" * 70)
    for d, t in org_teams:
        # 팀원들 이름 조회
        members = [r["name"] for r in org if r.get("division") == d and r.get("team") == t]
        filtered = filter_for(mapping, d, t, position="사원")  # 일반직급
        advs = unique_advertisers(filtered)
        print(f"\n[{d} {t}] 팀원 {len(members)}명 → 광고주 {len(advs)}개")
        if advs:
            for a in advs:
                print(f"    · {a}")

    # --- 6. 실장/본부장 시뮬레이션 ---
    print("\n" + "=" * 70)
    print("👔 실장/본부장 시뮬레이션 (본부 단위 조회)")
    print("=" * 70)
    for r in org:
        if r.get("position") in DIVISION_LEVEL_POSITIONS:
            d = r.get("division")
            filtered = filter_for(mapping, d, r.get("team"), position=r["position"])
            advs = unique_advertisers(filtered)
            print(f"\n[{r.get('name')} ({r.get('position')}) - {d}] 광고주 {len(advs)}개")

    # --- 7. 존재하지 않는 이메일 시뮬레이션 ---
    print("\n" + "=" * 70)
    print("❓ 미등록 이메일 시뮬레이션")
    print("=" * 70)
    print("→ get_org_by_email이 None 반환 → 앱에서 'unknown' 안내 표시 (실제 앱에서 확인)")

    print("\n" + "=" * 70)
    print("✅ 검증 완료")
    print("=" * 70)


if __name__ == "__main__":
    main()
