import streamlit as st
from datetime import date, timedelta
import io
from utils.auth import get_current_user
from utils.ui import set_current_page

set_current_page("report_download")

user = get_current_user()

# ============================
# GCP / BigQuery / Sheets 연결
# ============================
try:
    from google.oauth2 import service_account
    from google.cloud import bigquery
    import gspread
except ImportError as e:
    st.error(f"필수 패키지가 설치되지 않았습니다: {e}")
    st.stop()

BIGQUERY_PROJECT = "ad-report-automation-500214"
BIGQUERY_LOCATION = "asia-northeast3"
SHEET_ID = st.secrets.get("BIGQUERY_MAPPING_SHEET_ID", "")
SHEET_NAME = st.secrets.get("BIGQUERY_MAPPING_SHEET_NAME", "bigquery")

if "gcp_service_account" not in st.secrets or not SHEET_ID:
    st.error("GCP 서비스 계정 또는 시트 정보가 설정되지 않았습니다.")
    st.stop()

SCOPES = [
    "https://www.googleapis.com/auth/bigquery",
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

@st.cache_resource
def get_credentials():
    return service_account.Credentials.from_service_account_info(
        dict(st.secrets["gcp_service_account"]),
        scopes=SCOPES,
    )

@st.cache_resource
def get_bq_client():
    return bigquery.Client(
        credentials=get_credentials(),
        project=BIGQUERY_PROJECT,
        location=BIGQUERY_LOCATION,
    )

@st.cache_resource
def get_gspread_client():
    return gspread.authorize(get_credentials())


# ============================
# 매핑 시트 조회
# ============================
@st.cache_data(ttl=300)
def load_mapping():
    """bigquery 시트 → [{매체명, 광고계정id, 광고계정명, 광고주명, 최초감지일}]"""
    gc = get_gspread_client()
    sh = gc.open_by_key(SHEET_ID)
    ws = sh.worksheet(SHEET_NAME)
    rows = ws.get_all_records()
    return rows


def get_unique_advertisers(mapping):
    """광고주명 유니크 목록 (종료 제외, 공란 제외)"""
    names = set()
    for row in mapping:
        adv = str(row.get("광고주명", "")).strip()
        if adv and adv != "종료":
            names.add(adv)
    return sorted(names)


def get_accounts_for_advertiser(mapping, advertiser, selected_media):
    """광고주 + 매체 필터 → [(매체명, 광고계정id)] 목록"""
    media_map = {"구글": "google", "카카오": "kakao_moment", "네이버": "naver_gfa"}
    allowed_media = {media_map[m] for m in selected_media}
    accounts = []
    for row in mapping:
        if str(row.get("광고주명", "")).strip() != advertiser:
            continue
        media = str(row.get("매체명", "")).strip()
        if media not in allowed_media:
            continue
        acc_id = str(row.get("광고계정id", "")).strip()
        if acc_id:
            accounts.append((media, acc_id))
    return accounts


def count_by_media(accounts):
    counts = {"google": 0, "kakao_moment": 0, "naver_gfa": 0}
    for media, _ in accounts:
        if media in counts:
            counts[media] += 1
    return counts


# ============================
# BigQuery 조회
# ============================
TABLE_MAP = {
    "google": f"`{BIGQUERY_PROJECT}.raw.google`",
    "kakao_moment": f"`{BIGQUERY_PROJECT}.raw.kakao_moment`",
    "naver_gfa": f"`{BIGQUERY_PROJECT}.raw.naver_gfa`",
}

COLUMNS = [
    "date", "media", "ad_account_id", "ad_account_name",
    "campaign_id", "campaign_name", "adgroup_id", "adgroup_name",
    "creative_id", "creative_name", "ad_format",
    "impressions", "clicks", "cost", "views",
]


def build_query(accounts, start_date, end_date):
    """선택 매체·계정 UNION ALL 쿼리 생성"""
    from collections import defaultdict
    grouped = defaultdict(list)
    for media, acc_id in accounts:
        grouped[media].append(acc_id)

    unions = []
    for media, ids in grouped.items():
        ids_str = ", ".join(f"'{aid}'" for aid in ids)
        cols_str = ", ".join(COLUMNS)
        unions.append(f"""
        SELECT {cols_str}
        FROM {TABLE_MAP[media]}
        WHERE date BETWEEN @start_date AND @end_date
          AND ad_account_id IN ({ids_str})
        """)

    query = "\nUNION ALL\n".join(unions)
    query += "\nORDER BY date ASC"
    return query


def run_query(query, start_date, end_date):
    client = get_bq_client()
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("start_date", "DATE", start_date),
            bigquery.ScalarQueryParameter("end_date", "DATE", end_date),
        ]
    )
    return client.query(query, job_config=job_config).result().to_dataframe(create_bqstorage_client=False)


# ============================
# 엑셀 생성
# ============================
def build_excel(df):
    import openpyxl
    from openpyxl.utils.dataframe import dataframe_to_rows
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "report"
    for row in dataframe_to_rows(df, index=False, header=True):
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


# ============================
# UI
# ============================
st.markdown("<div style='font-size:20px;font-weight:700;margin-bottom:4px;'>📊 REPORT DOWNLOAD</div>",
            unsafe_allow_html=True)
st.markdown("<div style='font-size:12px;color:var(--text-muted);margin-bottom:16px;'>"
            "광고주별 리포트를 BigQuery에서 조회해 엑셀로 다운로드합니다.</div>",
            unsafe_allow_html=True)

# 매핑 시트 로드
try:
    mapping = load_mapping()
except Exception as e:
    st.error(f"매핑 시트 조회 실패: {e}")
    st.stop()

advertisers = get_unique_advertisers(mapping)
if not advertisers:
    st.warning("등록된 광고주가 없습니다.")
    st.stop()

# 기간 + 광고주 (한 행)
today = date.today()
default_start = today - timedelta(days=13)
default_end = today - timedelta(days=1)

col_start, col_end, col_adv = st.columns([1, 1, 2])
with col_start:
    start_date = st.date_input("시작일", value=default_start, key="rd_start")
with col_end:
    end_date = st.date_input("종료일", value=default_end, key="rd_end")
with col_adv:
    selected_adv = st.selectbox("광고주", advertisers, key="rd_adv")

# 매체 선택
st.markdown("<div style='font-size:12px;color:var(--text-muted);margin:12px 0 6px;'>매체 선택</div>",
            unsafe_allow_html=True)
if "rd_media" not in st.session_state:
    st.session_state["rd_media"] = ["구글", "카카오", "네이버"]

all_media = ["구글", "카카오", "네이버"]
media_chips = []
for m in all_media:
    is_active = m in st.session_state["rd_media"]
    if is_active:
        media_chips.append(
            f"<a href='#' id='media__{m}' style='text-decoration:none;'>"
            f"<span style='padding:8px 16px;font-size:13px;border-radius:8px;"
            f"background:#111;color:#fff;cursor:pointer;display:inline-block;'>✓ {m}</span></a>"
        )
    else:
        media_chips.append(
            f"<a href='#' id='media__{m}' style='text-decoration:none;color:#111;'>"
            f"<span style='padding:8px 16px;font-size:13px;border-radius:8px;"
            f"box-shadow:0 0 0 0.5px #999 inset;"
            f"color:#111;cursor:pointer;display:inline-block;'>{m}</span></a>"
        )

from st_click_detector import click_detector
media_html = "<div style='display:flex;gap:12px;margin-bottom:16px;'>" + "".join(media_chips) + "</div>"
clicked = click_detector(media_html, key="rd_media_det")
if clicked and clicked.startswith("media__"):
    m = clicked.replace("media__", "")
    last = st.session_state.get("_rd_media_last")
    if clicked != last:
        st.session_state["_rd_media_last"] = clicked
        if m in st.session_state["rd_media"]:
            st.session_state["rd_media"].remove(m)
        else:
            st.session_state["rd_media"].append(m)
        st.rerun()

selected_media = st.session_state["rd_media"]

# 검증
if start_date > end_date:
    st.error("시작일이 종료일보다 늦습니다.")
    st.stop()
if not selected_media:
    st.warning("매체를 최소 1개 선택해주세요.")
    st.stop()

# 광고계정 미리보기
accounts = get_accounts_for_advertiser(mapping, selected_adv, selected_media)
counts = count_by_media(accounts)
days = (end_date - start_date).days + 1

badge_google = f"<span style='display:inline-block;font-size:11px;padding:2px 8px;border-radius:4px;background:#E1F5EE;color:#0F6E56;margin-right:4px;'>구글</span>" if "구글" in selected_media else ""
badge_kakao = f"<span style='display:inline-block;font-size:11px;padding:2px 8px;border-radius:4px;background:#FBEAF0;color:#993556;margin-right:4px;'>카카오</span>" if "카카오" in selected_media else ""
badge_naver = f"<span style='display:inline-block;font-size:11px;padding:2px 8px;border-radius:4px;background:#EAF3DE;color:#3B6D11;margin-right:4px;'>네이버</span>" if "네이버" in selected_media else ""

acc_detail_parts = []
if "구글" in selected_media:
    acc_detail_parts.append(f"구글 {counts['google']}")
if "카카오" in selected_media:
    acc_detail_parts.append(f"카카오 {counts['kakao_moment']}")
if "네이버" in selected_media:
    acc_detail_parts.append(f"네이버 {counts['naver_gfa']}")

preview_html = f"""
<div style='background:var(--surface-2);border-radius:8px;padding:14px 18px;margin-bottom:16px;border:0.5px solid var(--border);'>
    <div style='font-size:11px;color:var(--text-muted);margin-bottom:8px;'>📋 다운로드 요약</div>
    <div style='display:flex;gap:8px;margin-bottom:2px;font-size:13px;'>
        <span style='color:var(--text-muted);min-width:90px;font-size:12px;'>광고주</span>
        <span style='color:var(--text-primary);font-weight:500;'>{selected_adv}</span>
    </div>
    <div style='display:flex;gap:8px;margin-bottom:2px;font-size:13px;'>
        <span style='color:var(--text-muted);min-width:90px;font-size:12px;'>기간</span>
        <span style='color:var(--text-primary);font-weight:500;'>{start_date.isoformat()} ~ {end_date.isoformat()} ({days}일)</span>
    </div>
    <div style='display:flex;gap:8px;margin-bottom:2px;font-size:13px;'>
        <span style='color:var(--text-muted);min-width:90px;font-size:12px;'>매체</span>
        <span>{badge_google}{badge_kakao}{badge_naver}</span>
    </div>
    <div style='display:flex;gap:8px;margin-bottom:2px;font-size:13px;'>
        <span style='color:var(--text-muted);min-width:90px;font-size:12px;'>광고계정</span>
        <span style='color:var(--text-primary);font-weight:500;'>{len(accounts)}개 ({', '.join(acc_detail_parts)})</span>
    </div>
</div>
"""
st.markdown(preview_html, unsafe_allow_html=True)

if not accounts:
    st.warning("선택한 조건에 해당하는 광고계정이 없습니다.")
    st.stop()

# 다운로드 (fragment로 격리)
@st.fragment
def download_section():
    if st.button("📥 통합 데이터 다운로드", type="primary", use_container_width=True, key="rd_download_btn"):
        with st.spinner("BigQuery 조회 중..."):
            try:
                query = build_query(accounts, start_date, end_date)
                df = run_query(query, start_date, end_date)
                if df.empty:
                    st.warning("해당 조건에 데이터가 없습니다.")
                    return
                buf = build_excel(df)
                file_name = f"report_daily_{start_date.isoformat()}_{end_date.isoformat()}_{selected_adv}_{today.isoformat()}.xlsx"
                st.download_button(
                    "📥 파일 저장",
                    data=buf,
                    file_name=file_name,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    type="primary",
                    use_container_width=True,
                )
                st.success(f"조회 완료: 총 {len(df):,}행")
            except Exception as e:
                st.error(f"다운로드 중 오류: {e}")

download_section()

st.markdown(
    "<div style='display:flex;gap:12px;margin-top:12px;padding:10px 14px;"
    "background:#FFF8E1;border-left:3px solid #F2A93B;border-radius:4px;"
    "font-size:12px;color:#111;'>"
    "ℹ️ BigQuery 조회 특성상 데이터 양에 따라 5초~1분 소요될 수 있습니다."
    "</div>",
    unsafe_allow_html=True,
)
