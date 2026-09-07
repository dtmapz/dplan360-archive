#!/usr/bin/env python3
"""
특정 캠페인 키워드로 API 응답을 필터링해서 원본 데이터를 그대로 출력.

사용법:
  export QNA_LOGIN_ID='...'
  export QNA_LOGIN_PW='...'
  python3 debug_lookup.py 2024 농심
"""
import os
import sys
import json
import requests

BASE_URL = os.environ.get("BUDGET_PLATFORM_URL", "").strip().rstrip("/")
if not BASE_URL:
    raise SystemExit("BUDGET_PLATFORM_URL 환경변수 없음")
LOGIN_URL = f"{BASE_URL}/_common/loginProc.php"
API_URL = f"{BASE_URL}/ajax/ajax.inquire.php"


def main():
    if len(sys.argv) < 3:
        print("사용법: python3 debug_lookup.py <연도> <캠페인키워드>")
        sys.exit(1)
    year = sys.argv[1]
    keyword = sys.argv[2]

    uid = os.getenv("QNA_LOGIN_ID")
    upw = os.getenv("QNA_LOGIN_PW")
    if not (uid and upw):
        print("QNA_LOGIN_ID / QNA_LOGIN_PW 환경변수 필요")
        sys.exit(1)

    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0"})
    r = s.post(LOGIN_URL, data={
        "action": "login", "userID": uid, "userPW": upw, "isRemember": "Y",
    }, timeout=30)
    if "top.location.href" not in r.text:
        print("로그인 실패")
        sys.exit(1)
    print(f"로그인 성공")

    payload = [
        ("action", "getSalesList"),
        ("teamIdx", ""), ("advertiserIdx", ""), ("agencyIdx", ""), ("mediaIdx", ""),
        ("campaignStatus", ""), ("campaignConfirm", ""),
        ("dateType", "salesMonth"), ("dateY", year), ("dateSelType", ""),
    ]
    for q in range(1, 5):
        payload.append(("quarterSelArr[]", str(q)))
    for m in range(1, 13):
        payload.append(("monthlySelArr[]", str(m)))
    payload += [("search", keyword), ("sort", ""), ("order", ""),
                ("offset", "0"), ("limit", "500")]

    r = s.post(API_URL, data=payload, headers={
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"{BASE_URL}/page/inquireList.php",
    }, timeout=60)
    r.raise_for_status()
    data = r.json()
    rows = data.get("rows", [])
    print(f"\n검색어='{keyword}' 연도={year} → {len(rows)}건\n" + "=" * 60)

    for i, row in enumerate(rows, 1):
        print(f"\n[{i}] no={row.get('no')} idx={row.get('idx')}")
        print(f"  campaignName  : {row.get('campaignName')!r}")
        print(f"  advertiserName: {row.get('advertiserName')!r}")
        print(f"  agencyName    : {row.get('agencyName')!r}")
        print(f"  mediaName     : {row.get('mediaName')!r}")
        print(f"  totalAdPrice  : {row.get('totalAdPrice')!r}")
        print(f"  agTaxIssueDateYm  : {row.get('agTaxIssueDateYm')!r}")
        print(f"  belongSalesDateYm : {row.get('belongSalesDateYm')!r}")
        print(f"  memo (raw)    : {row.get('memo')!r}")

    # 전체 JSON도 파일로 저장
    out = "/tmp/debug_lookup.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    print(f"\n전체 응답 저장: {out}")


if __name__ == "__main__":
    main()
