#!/usr/bin/env python3
"""
budget_history 시트의 각 행에 대응하는 플랫폼 메모를 수집하여 H열에 채워넣음.

매칭 키(6개): 캠페인명 / 광고주 / 대행사 / 매체사 / 광고수주액 / 대행사 발행월(YYYY.MM)
API 필드:    campaignName / advertiserName / agencyName / mediaName / totalAdPrice / agTaxIssueDateYm

같은 6키에 여러 라인이 잡히고 memo가 서로 다르면 "\\n---\\n" 로 병합, conflicts.log 기록.

사용법:
  export QNA_LOGIN_ID='...'
  export QNA_LOGIN_PW='...'
  export QNA_GCP_SERVICE_ACCOUNT_JSON='...(json or base64)...'
  python3 budget_memo_crawler.py --dry-run     # 매칭만 확인, 시트 미변경
  python3 budget_memo_crawler.py               # 실제 H열 업데이트
"""
import os
import sys
import json
import base64
import argparse
import logging
import re
import time
from collections import defaultdict
from typing import Dict, List, Tuple, Optional

import requests
from bs4 import BeautifulSoup
import gspread
from google.oauth2 import service_account

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger("budget_memo")

BASE_URL = "https://dplan360.emato.net"
LOGIN_URL = f"{BASE_URL}/_common/loginProc.php"
API_URL = f"{BASE_URL}/ajax/ajax.inquire.php"
CAMPAIGN_API_URL = f"{BASE_URL}/ajax/ajax.campaign.php"

SHEET_ID = "1VSS1zHcoOiumySmzxyj-34zy3Qs7ln8Azp_TEZeKaDQ"
SHEET_GID = 1008030082
TAB_NAME = "budget_history"

# 시트 컬럼 (A~H)
COL_CAMPAIGN = 0   # A 캠페인명
COL_ADVERTISER = 1 # B 광고주
COL_BRAND = 2      # C 브랜드 (매칭 미사용)
COL_AGENCY = 3     # D 대행사
COL_MEDIA = 4      # E 매체사
COL_PRICE = 5      # F 광고수주액
COL_MONTH = 6      # G 대행사 발행월 (YYYY.MM)
COL_MEMO = 7       # H 메모 (업데이트 대상)


def load_credentials(raw: str) -> dict:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return json.loads(base64.b64decode(raw).decode("utf-8"))


def login(session: requests.Session, uid: str, upw: str) -> bool:
    r = session.post(LOGIN_URL, data={
        "action": "login", "userID": uid, "userPW": upw, "isRemember": "Y",
    }, timeout=30)
    ok = r.status_code == 200 and "top.location.href" in r.text
    log.info(f"로그인 {'성공' if ok else '실패'} (status={r.status_code})")
    return ok


def fetch_year(session: requests.Session, year: str, limit: int = 10000) -> List[dict]:
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
    payload += [("search", ""), ("sort", ""), ("order", ""),
                ("offset", "0"), ("limit", str(limit))]

    r = session.post(API_URL, data=payload, headers={
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"{BASE_URL}/page/inquireList.php",
    }, timeout=60)
    r.raise_for_status()
    data = r.json()
    rows = data.get("rows", [])
    log.info(f"  · {year}년 API 응답: {len(rows)}건 (total={data.get('total')})")
    return rows


_campaign_memo_cache: Dict[str, Dict[Tuple[str, str], str]] = {}


def fetch_campaign_memos(session: requests.Session, campaign_idx: str) -> Dict[Tuple[str, str], str]:
    """상세 API 호출 → (mediaName, adPrice) → memo dict. idx 단위 캐싱."""
    if campaign_idx in _campaign_memo_cache:
        return _campaign_memo_cache[campaign_idx]
    payload = [
        ("action", "getCampaignMediaList"),
        ("campaignIdx", campaign_idx),
        ("search", ""), ("sort", ""), ("order", ""),
    ]
    try:
        r = session.post(CAMPAIGN_API_URL, data=payload, headers={
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"{BASE_URL}/page/campaignRegister.php?id={campaign_idx}",
        }, timeout=60)
        r.raise_for_status()
        data = r.json()
        rows = data.get("rows", [])
    except Exception as e:
        log.warning(f"  ! campaignIdx={campaign_idx} 상세 조회 실패: {e}")
        _campaign_memo_cache[campaign_idx] = {}
        return {}
    result: Dict[Tuple[str, str], str] = {}
    for row in rows:
        key = (norm(row.get("mediaName", "")), norm_price(row.get("adPrice", "")))
        memo = row.get("memo", "") or ""
        # 같은 (media, price)가 여러 개면 non-empty 우선
        if key not in result or (memo and not result[key]):
            result[key] = memo
    _campaign_memo_cache[campaign_idx] = result
    return result


def clean_memo(html: str) -> str:
    if not html:
        return ""
    text = BeautifulSoup(html, "html.parser").get_text(separator="\n")
    # 연속 공백/개행 정리
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def norm(s: str) -> str:
    """매칭키 정규화: 양끝 공백 제거."""
    return (s or "").strip()


def norm_price(s: str) -> str:
    """광고수주액: 콤마/공백 제거해서 숫자만 비교."""
    return re.sub(r"[,\s]", "", s or "")


def norm_month(s: str) -> str:
    """대행사 발행월: 'YYYY.MM' 표준화, 'YYYY-MM'/'YYYY/MM'도 허용."""
    s = (s or "").strip()
    m = re.match(r"^(\d{4})[.\-/](\d{1,2})$", s)
    if not m:
        return s
    return f"{m.group(1)}.{int(m.group(2)):02d}"


def make_key(campaign, advertiser, agency, media, price, month) -> Tuple[str, ...]:
    return (
        norm(campaign),
        norm(advertiser),
        norm(agency),
        norm(media),
        norm_price(price),
        norm_month(month),
    )


def build_lookup(
    session: requests.Session,
    api_rows: List[dict],
    year: str,
) -> Dict[Tuple, List[str]]:
    """
    API 행을 6키 → memo 리스트로 그룹핑.
    memo는 상세 API(getCampaignMediaList)에서 (mediaName, adPrice)로 조인해서 가져옴.
    """
    lookup: Dict[Tuple, List[str]] = defaultdict(list)
    unique_idx = sorted({str(r.get("idx", "")) for r in api_rows if r.get("idx")})
    log.info(f"  · {year}년 상세 조회 대상 캠페인: {len(unique_idx)}개")

    for i, row in enumerate(api_rows, 1):
        idx = str(row.get("idx", ""))
        media = row.get("mediaName", "")
        price = row.get("totalAdPrice", "")
        detail_memos = fetch_campaign_memos(session, idx) if idx else {}
        # 라인(매체) 단위 memo만 사용. 상세에 없으면 공백 유지 (캠페인 단위 memo로 fallback 금지)
        memo = detail_memos.get((norm(media), norm_price(price)), "")
        key = make_key(
            row.get("campaignName", ""),
            row.get("advertiserName", ""),
            row.get("agencyName", ""),
            media, price,
            row.get("agTaxIssueDateYm", ""),
        )
        lookup[key].append(memo)
        if i % 100 == 0:
            log.info(f"    - 진행 {i}/{len(api_rows)}")
        time.sleep(0.1)  # 상세 API rate limit 회피
    return lookup


def resolve_memo(memos: List[str]) -> Tuple[str, bool]:
    """3-tier 처리. (합쳐진텍스트, 충돌여부) 반환."""
    cleaned = [clean_memo(m) for m in memos]
    non_empty = [m for m in cleaned if m]
    if not non_empty:
        return "", False
    unique = []
    for m in non_empty:
        if m not in unique:
            unique.append(m)
    if len(unique) == 1:
        return unique[0], False
    return "\n---\n".join(unique), True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="시트 미변경, 매칭 결과만 출력")
    ap.add_argument("--from-csv", metavar="PATH",
                    help="matches.csv를 읽어 시트에 그대로 씀 (API 재호출 없음)")
    args = ap.parse_args()

    # --- fast path: matches.csv로부터 시트 업데이트만 수행 ---
    if args.from_csv:
        import csv
        creds_raw = os.getenv("QNA_GCP_SERVICE_ACCOUNT_JSON")
        if not creds_raw:
            log.error("환경변수 필요: QNA_GCP_SERVICE_ACCOUNT_JSON")
            sys.exit(1)
        creds = service_account.Credentials.from_service_account_info(
            load_credentials(creds_raw),
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
        gc = gspread.authorize(creds)
        ss = gc.open_by_key(SHEET_ID)
        ws = next((w for w in ss.worksheets() if w.id == SHEET_GID), None)
        if ws is None:
            log.error(f"gid={SHEET_GID} 워크시트를 찾을 수 없음")
            sys.exit(1)

        with open(args.from_csv, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            batch = []
            for r in reader:
                if r.get("status") == "NO_MATCH":
                    continue
                row_num = int(r["sheet_row"])
                memo = r.get("resolved_memo", "") or ""
                batch.append({"range": f"H{row_num}", "values": [[memo]]})
        log.info(f"CSV에서 로드한 업데이트 대상: {len(batch)}건")
        CHUNK = 500
        for i in range(0, len(batch), CHUNK):
            ws.batch_update(batch[i:i + CHUNK], value_input_option="USER_ENTERED")
            log.info(f"업데이트 {min(i + CHUNK, len(batch))}/{len(batch)}")
            time.sleep(1.0)
        log.info("완료")
        return

    uid = os.getenv("QNA_LOGIN_ID")
    upw = os.getenv("QNA_LOGIN_PW")
    creds_raw = os.getenv("QNA_GCP_SERVICE_ACCOUNT_JSON")
    if not (uid and upw and creds_raw):
        log.error("환경변수 필요: QNA_LOGIN_ID, QNA_LOGIN_PW, QNA_GCP_SERVICE_ACCOUNT_JSON")
        sys.exit(1)

    # 1) 시트 열기
    creds = service_account.Credentials.from_service_account_info(
        load_credentials(creds_raw),
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    gc = gspread.authorize(creds)
    ss = gc.open_by_key(SHEET_ID)
    ws = None
    for w in ss.worksheets():
        if w.id == SHEET_GID:
            ws = w
            break
    if ws is None:
        log.error(f"gid={SHEET_GID} 워크시트를 찾을 수 없음")
        sys.exit(1)
    log.info(f"시트 열기 완료: {ws.title}")

    all_values = ws.get_all_values()
    if len(all_values) <= 1:
        log.info("데이터 없음")
        return
    header, data_rows = all_values[0], all_values[1:]
    log.info(f"시트 행: {len(data_rows)}건 (헤더: {header})")

    # 2) 시트에서 대상 연도 수집
    years = set()
    for row in data_rows:
        if len(row) <= COL_MONTH:
            continue
        m = norm_month(row[COL_MONTH])
        if re.match(r"^\d{4}\.\d{2}$", m):
            years.add(m.split(".")[0])
    log.info(f"대상 연도: {sorted(years)}")

    # 3) 로그인 + 연도별 API 호출 → 통합 lookup
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})
    if not login(session, uid, upw):
        sys.exit(1)

    lookup: Dict[Tuple, List[str]] = defaultdict(list)
    for y in sorted(years):
        rows = fetch_year(session, y)
        for k, memos in build_lookup(session, rows, y).items():
            lookup[k].extend(memos)
        time.sleep(0.5)
    log.info(f"lookup 키 수: {len(lookup)}")

    # 4) 시트 행별 매칭
    updates: List[Tuple[int, str]] = []  # (row_num_1based_in_sheet, memo)
    detail_rows: List[dict] = []         # dry-run 검증용 상세
    stats = {"matched": 0, "empty_memo": 0, "conflict": 0, "no_match": 0}
    conflict_lines: List[str] = []
    no_match_lines: List[str] = []

    for idx, row in enumerate(data_rows, start=2):  # sheet row = idx (header가 1행)
        if len(row) < 7:
            continue
        key = make_key(
            row[COL_CAMPAIGN], row[COL_ADVERTISER], row[COL_AGENCY],
            row[COL_MEDIA], row[COL_PRICE], row[COL_MONTH],
        )
        memos = lookup.get(key)
        detail = {
            "sheet_row": idx,
            "campaign": row[COL_CAMPAIGN],
            "advertiser": row[COL_ADVERTISER],
            "agency": row[COL_AGENCY],
            "media": row[COL_MEDIA],
            "price": row[COL_PRICE],
            "month": row[COL_MONTH],
            "match_count": 0,
            "conflict": "",
            "resolved_memo": "",
            "status": "",
        }
        if memos is None:
            stats["no_match"] += 1
            no_match_lines.append(f"row {idx} | {key}")
            detail["status"] = "NO_MATCH"
            detail_rows.append(detail)
            continue
        text, conflicted = resolve_memo(memos)
        stats["matched"] += 1
        if not text:
            stats["empty_memo"] += 1
        if conflicted:
            stats["conflict"] += 1
            conflict_lines.append(
                f"row {idx} | {row[COL_CAMPAIGN]} | {len(memos)}건 상이 → 병합"
            )
        detail["match_count"] = len(memos)
        detail["conflict"] = "Y" if conflicted else ""
        detail["resolved_memo"] = text
        detail["status"] = "EMPTY" if not text else ("CONFLICT_MERGED" if conflicted else "OK")
        detail_rows.append(detail)
        updates.append((idx, text))

    log.info(f"매칭 결과: {stats}")

    # 5) 로그 파일 저장
    out_dir = os.path.dirname(os.path.abspath(__file__))
    if conflict_lines:
        with open(os.path.join(out_dir, "conflicts.log"), "w", encoding="utf-8") as f:
            f.write("\n".join(conflict_lines))
        log.info(f"conflicts.log: {len(conflict_lines)}건")
    if no_match_lines:
        with open(os.path.join(out_dir, "no_match.log"), "w", encoding="utf-8") as f:
            f.write("\n".join(no_match_lines))
        log.info(f"no_match.log: {len(no_match_lines)}건")

    # 6) 상세 CSV 저장 (dry-run/실행 모두)
    import csv
    csv_path = os.path.join(out_dir, "matches.csv")
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "sheet_row", "status", "match_count", "conflict",
            "campaign", "advertiser", "agency", "media", "price", "month",
            "resolved_memo",
        ])
        writer.writeheader()
        writer.writerows(detail_rows)
    log.info(f"상세 매칭 결과 저장: {csv_path} ({len(detail_rows)}행)")

    if args.dry_run:
        log.info("[DRY-RUN] 시트 미변경. 샘플 상위 10건 (memo 있는 것 우선):")
        with_memo = [d for d in detail_rows if d["resolved_memo"]]
        for d in with_memo[:10]:
            preview = d["resolved_memo"][:80].replace("\n", " ↵ ")
            log.info(
                f"  H{d['sheet_row']} [{d['status']}] "
                f"{d['campaign'][:20]} | {d['media']} | {d['price']} | {d['month']} "
                f"→ {preview!r}"
            )
        log.info(f"전체 매칭 상세는 matches.csv 를 확인하세요.")
        return

    if not updates:
        log.info("업데이트할 행 없음")
        return

    # gspread batch_update: H열만
    batch = [{
        "range": f"H{row_num}",
        "values": [[text]],
    } for row_num, text in updates]

    # gspread는 batch_update 크기 제한이 있으므로 500건씩 끊어 전송
    CHUNK = 500
    for i in range(0, len(batch), CHUNK):
        ws.batch_update(batch[i:i + CHUNK], value_input_option="USER_ENTERED")
        log.info(f"업데이트 {min(i + CHUNK, len(batch))}/{len(batch)}")
        time.sleep(1.0)

    log.info("완료")


if __name__ == "__main__":
    main()
