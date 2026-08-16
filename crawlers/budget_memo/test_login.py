#!/usr/bin/env python3
"""
플랫폼 로그인 시험 스크립트
사용법:
  export QNA_LOGIN_ID='...'
  export QNA_LOGIN_PW='...'
  python3 test_login.py
"""
import os
import sys
import requests

BASE_URL = "https://dplan360.emato.net"
LOGIN_URL = f"{BASE_URL}/_common/loginProc.php"
LIST_URL = f"{BASE_URL}/page/inquireList.php"


def main():
    uid = os.getenv("QNA_LOGIN_ID")
    upw = os.getenv("QNA_LOGIN_PW")
    if not uid or not upw:
        print("QNA_LOGIN_ID / QNA_LOGIN_PW 환경변수 필요")
        sys.exit(1)

    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    })

    print(f"[1] POST {LOGIN_URL}")
    r = s.post(LOGIN_URL, data={
        "action": "login",
        "userID": uid,
        "userPW": upw,
        "isRemember": "Y",
    }, timeout=30, allow_redirects=False)
    print(f"    status={r.status_code}  set-cookie={dict(s.cookies)}")
    print(f"    body(앞 300): {r.text[:300]!r}")

    print(f"\n[2] GET {LIST_URL}")
    r2 = s.get(LIST_URL, timeout=30)
    print(f"    status={r2.status_code}  length={len(r2.text)}")
    # 로그인 성공 판정: 로그인폼 리다이렉트가 아닌 실제 리스트 페이지가 오는지
    signals = {
        "inquireList 키워드": "inquireList" in r2.text,
        "select2-dateY-container": "select2-dateY-container" in r2.text,
        "search-input": "search-input" in r2.text,
        "메모 컬럼(data-field=memo)": 'data-field="memo"' in r2.text,
        "loginProc 리다이렉트 감지": "loginProc" in r2.text or "login.php" in r2.text.lower(),
    }
    for k, v in signals.items():
        print(f"    - {k}: {v}")

    out = "/tmp/inquireList.html"
    with open(out, "w", encoding="utf-8") as f:
        f.write(r2.text)
    print(f"\n페이지 원문 저장: {out}")


if __name__ == "__main__":
    main()
