import io
import re
import html
import streamlit as st
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

from utils.auth import get_current_user
from utils.ui import set_current_page
from utils.sheets import get_budget_history, get_budget_adv

set_current_page("budget_reference")
user = get_current_user()

GROUP_COLS = ["대업종", "소업종", "광고주", "브랜드", "대행사", "캠페인명", "대행사 발행월"]
DISPLAY_COLS = [
    "대업종", "소업종", "광고주", "브랜드", "대행사", "캠페인명",
    "매체사", "상품", "광고수주액", "비중", "대행사 발행월",
]
EMPTY_PRODUCT = "—"


def _norm_month(s: str) -> str:
    """대행사 발행월 표기 정규화 → 'YYYY.MM'. 파싱 불가면 원문 유지."""
    s = (s or "").strip()
    if not s:
        return s
    m = re.match(r"^(\d{4})[.\-/](\d{1,2})(?:\.0+)?$", s)
    if m:
        return f"{m.group(1)}.{int(m.group(2)):02d}"
    # gspread가 이미 float로 캐스팅한 흔적 (예: '2025.1' → 원본 '2025.10'일 가능성)
    # 소수부 1자리이고 두 자릿수로 복원할 수 없으므로 그대로 유지
    return s


# ============================================================
# 데이터 로드 + 조인
# ============================================================
@st.cache_data(ttl=600, show_spinner=False)
def _load_joined() -> pd.DataFrame:
    hist = pd.DataFrame(get_budget_history())
    adv = pd.DataFrame(get_budget_adv())

    if hist.empty:
        return hist

    for col in ("광고주", "브랜드"):
        if col in hist.columns:
            hist[col] = hist[col].astype(str).str.strip()
    for col in ("광고주명", "브랜드명"):
        if col in adv.columns:
            adv[col] = adv[col].astype(str).str.strip()

    if not adv.empty:
        adv_slim = adv[["광고주명", "브랜드명", "대업종", "소업종"]].drop_duplicates(
            subset=["광고주명", "브랜드명"], keep="first"
        )
        hist = hist.merge(
            adv_slim,
            how="left",
            left_on=["광고주", "브랜드"],
            right_on=["광고주명", "브랜드명"],
        ).drop(columns=["광고주명", "브랜드명"], errors="ignore")

    if "대행사 발행월" in hist.columns:
        hist["대행사 발행월"] = hist["대행사 발행월"].astype(str).str.strip().map(_norm_month)

    # 상품 컬럼 정규화 (헤더가 "상품" / "상품명" / "상품(정리)" 어느 쪽이든 대응)
    for alt in ("상품(정리)", "상품명"):
        if "상품" not in hist.columns and alt in hist.columns:
            hist["상품"] = hist[alt]
            break
    if "상품" in hist.columns:
        hist["상품"] = hist["상품"].astype(str).str.strip()
        hist["상품"] = hist["상품"].where(hist["상품"] != "", EMPTY_PRODUCT)
    else:
        hist["상품"] = EMPTY_PRODUCT

    if "광고수주액" in hist.columns:
        hist["광고수주액"] = pd.to_numeric(
            hist["광고수주액"].astype(str).str.replace(",", "").str.strip(),
            errors="coerce",
        ).fillna(0).astype(int)

    return hist


try:
    df_all = _load_joined()
except Exception as e:
    st.error(f"데이터 로드 실패: {e}")
    st.stop()

if df_all.empty:
    st.info("budget_history 시트에 데이터가 없습니다.")
    st.stop()


# ============================================================
# 필터 UI
# ============================================================
majors = sorted(
    [x for x in df_all.get("대업종", pd.Series(dtype=str)).dropna().unique() if str(x).strip()]
)

col_f1, col_f2, col_f3, col_f4 = st.columns([2, 3, 3, 1])

with col_f1:
    sel_major = st.selectbox("대업종 (필수)", ["-- 선택 --"] + majors, index=0)

sub_options: list[str] = []
if sel_major and sel_major != "-- 선택 --":
    sub_options = sorted(
        [
            x for x in df_all[df_all["대업종"] == sel_major]
            .get("소업종", pd.Series(dtype=str))
            .dropna()
            .unique()
            if str(x).strip()
        ]
    )

with col_f2:
    sel_subs = st.multiselect("소업종 (선택)", sub_options, default=[])

# 선택한 업종 하위 광고주만 노출
_adv_scope = df_all.copy()
if sel_major and sel_major != "-- 선택 --":
    _adv_scope = _adv_scope[_adv_scope["대업종"] == sel_major]
if sel_subs:
    _adv_scope = _adv_scope[_adv_scope["소업종"].isin(sel_subs)]

adv_options = sorted(
    [
        x for x in _adv_scope.get("광고주", pd.Series(dtype=str)).dropna().unique()
        if str(x).strip()
    ]
)

with col_f3:
    sel_advs = st.multiselect("광고주 (선택)", adv_options, default=[])

with col_f4:
    # 라벨 높이만큼 spacer 추가해 버튼을 드롭다운 하단선에 정렬
    st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)
    search = st.button("조회", type="primary", use_container_width=True)

# 연/월 필터 (2행)
if sel_advs:
    _adv_scope = _adv_scope[_adv_scope["광고주"].isin(sel_advs)]

_month_series = _adv_scope.get("대행사 발행월", pd.Series(dtype=str)).dropna().astype(str)
year_options = sorted({m.split(".")[0] for m in _month_series if re.match(r"^\d{4}\.\d{2}$", m)})

col_y1, col_y2, _ = st.columns([2, 3, 5])
with col_y1:
    sel_years = st.multiselect("연도 (선택)", year_options, default=[])

if sel_years:
    _month_series = _month_series[_month_series.str[:4].isin(sel_years)]
month_options = sorted({m.split(".")[1] for m in _month_series if re.match(r"^\d{4}\.\d{2}$", m)})

with col_y2:
    sel_months = st.multiselect("월 (선택)", month_options, default=[])

if search:
    if not sel_major or sel_major == "-- 선택 --":
        st.warning("대업종을 선택해주세요.")
        st.stop()

    df = df_all.copy()
    df = df[df["대업종"] == sel_major]
    if sel_subs:
        df = df[df["소업종"].isin(sel_subs)]
    if sel_advs:
        df = df[df["광고주"].isin(sel_advs)]
    if sel_years:
        df = df[df["대행사 발행월"].astype(str).str[:4].isin(sel_years)]
    if sel_months:
        df = df[df["대행사 발행월"].astype(str).str[-2:].isin(sel_months)]

    st.session_state["_budget_result"] = df.reset_index(drop=True)


# ============================================================
# 결과 렌더링
# ============================================================
def _fmt_won(v: int) -> str:
    return f"{int(v):,}"


def _fmt_pct(v: float) -> str:
    return f"{v * 100:.2f}%"


def _group_iter(df: pd.DataFrame):
    """(group_key, group_df, total_amount) 캠페인 총액 desc."""
    grouped = df.groupby(GROUP_COLS, dropna=False, sort=False)
    items = []
    for key, gdf in grouped:
        total = int(gdf["광고수주액"].sum())
        items.append((key, gdf.reset_index(drop=True), total))
    items.sort(key=lambda x: x[2], reverse=True)
    return items


def _render_preview_html(groups) -> str:
    css = """
    <style>
    .bref-tbl { border-collapse: collapse; width: 100%; font-size: 12px; background: #fff; }
    .bref-tbl th, .bref-tbl td {
        border: 1px solid #E5E5E5; padding: 8px 10px; text-align: center; vertical-align: middle;
    }
    .bref-tbl thead th {
        background: #0B0B0B; color: #fff; font-weight: 600; padding: 10px;
    }
    .bref-tbl td.num { text-align: right; font-variant-numeric: tabular-nums; }
    .bref-tbl td.merged { background: #fafafa; }
    .bref-tbl td.camp { background: #fafafa; font-weight: 600; }
    .bref-tbl tr.total td {
        background: #FFF8E1; font-weight: 700; border-top: 1.5px solid #F2A93B;
    }
    </style>
    """
    head = "<tr>" + "".join(f"<th>{c}</th>" for c in DISPLAY_COLS) + "</tr>"
    body_rows = []

    for key, gdf, total in groups:
        key_map = dict(zip(GROUP_COLS, key))
        n = len(gdf)

        for i, row in gdf.iterrows():
            tds = []
            if i == 0:
                for c in ["대업종", "소업종", "광고주", "브랜드", "대행사"]:
                    tds.append(f'<td class="merged" rowspan="{n}">{html.escape(str(key_map.get(c) or ""))}</td>')
                tds.append(f'<td class="camp" rowspan="{n}">{html.escape(str(key_map.get("캠페인명") or ""))}</td>')
            tds.append(f'<td>{html.escape(str(row.get("매체사") or ""))}</td>')
            product = str(row.get("상품") or "").strip() or EMPTY_PRODUCT
            tds.append(f'<td>{html.escape(product)}</td>')
            amt = int(row.get("광고수주액") or 0)
            tds.append(f'<td class="num">{_fmt_won(amt)}</td>')
            pct = (amt / total) if total else 0
            tds.append(f'<td class="num">{_fmt_pct(pct)}</td>')
            if i == 0:
                tds.append(f'<td class="merged" rowspan="{n}">{html.escape(str(key_map.get("대행사 발행월") or ""))}</td>')
            body_rows.append("<tr>" + "".join(tds) + "</tr>")

        camp_name = html.escape(str(key_map.get("캠페인명") or ""))
        body_rows.append(
            f'<tr class="total">'
            f'<td colspan="8">Total : {camp_name}</td>'
            f'<td class="num">{_fmt_won(total)}</td>'
            f'<td colspan="2"></td>'
            f'</tr>'
        )

    return css + f'<table class="bref-tbl"><thead>{head}</thead><tbody>{"".join(body_rows)}</tbody></table>'


def _build_excel(groups) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "campaigns"

    header_fill = PatternFill("solid", fgColor="0B0B0B")
    header_font = Font(bold=True, color="FFFFFF", size=11)
    total_fill = PatternFill("solid", fgColor="FFF8E1")
    total_font = Font(bold=True)
    merged_fill = PatternFill("solid", fgColor="FAFAFA")
    thin = Side(border_style="thin", color="E5E5E5")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    right = Alignment(horizontal="right", vertical="center")

    for col_idx, name in enumerate(DISPLAY_COLS, start=1):
        c = ws.cell(row=1, column=col_idx, value=name)
        c.fill = header_fill
        c.font = header_font
        c.alignment = center
        c.border = border

    r = 2
    for key, gdf, total in groups:
        key_map = dict(zip(GROUP_COLS, key))
        n = len(gdf)
        start_row = r

        for i, row in gdf.iterrows():
            if i == 0:
                for col_name, col_idx in [
                    ("대업종", 1), ("소업종", 2), ("광고주", 3),
                    ("브랜드", 4), ("대행사", 5), ("캠페인명", 6),
                ]:
                    cell = ws.cell(row=r, column=col_idx, value=key_map.get(col_name) or "")
                    cell.fill = merged_fill
                cell = ws.cell(row=r, column=11, value=key_map.get("대행사 발행월") or "")
                cell.fill = merged_fill

            ws.cell(row=r, column=7, value=str(row.get("매체사") or ""))
            product = str(row.get("상품") or "").strip() or EMPTY_PRODUCT
            ws.cell(row=r, column=8, value=product)
            amt = int(row.get("광고수주액") or 0)
            ac = ws.cell(row=r, column=9, value=amt)
            ac.number_format = "#,##0"
            ac.alignment = right
            pct = (amt / total) if total else 0
            pc = ws.cell(row=r, column=10, value=pct)
            pc.number_format = "0.00%"
            pc.alignment = right
            r += 1

        # Total 행
        total_row_idx = r
        tc = ws.cell(row=total_row_idx, column=1, value=f"Total : {key_map.get('캠페인명') or ''}")
        for col_idx in range(1, 12):
            cell = ws.cell(row=total_row_idx, column=col_idx)
            cell.fill = total_fill
            cell.font = total_font
        ws.merge_cells(start_row=total_row_idx, start_column=1, end_row=total_row_idx, end_column=8)
        tc.alignment = center
        ac = ws.cell(row=total_row_idx, column=9, value=total)
        ac.number_format = "#,##0"
        ac.alignment = right
        ac.fill = total_fill
        ac.font = total_font
        ws.merge_cells(start_row=total_row_idx, start_column=10, end_row=total_row_idx, end_column=11)
        r += 1

        # 매체 라인 rowspan 병합 (2건 이상일 때) — 매체사(7)·상품(8)은 라인마다 다르므로 병합 제외
        end_row = start_row + n - 1
        if end_row > start_row:
            for col_idx in [1, 2, 3, 4, 5, 6, 11]:
                ws.merge_cells(
                    start_row=start_row, start_column=col_idx,
                    end_row=end_row, end_column=col_idx,
                )
                ws.cell(row=start_row, column=col_idx).alignment = center

    for row_cells in ws.iter_rows(min_row=1, max_row=r - 1, min_col=1, max_col=11):
        for c in row_cells:
            c.border = border
            if c.alignment is None or c.alignment.horizontal is None:
                c.alignment = center

    widths = [10, 14, 16, 16, 14, 26, 18, 18, 16, 10, 14]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


df_result = st.session_state.get("_budget_result")
if df_result is not None:
    groups = _group_iter(df_result)
    n_campaigns = len(groups)
    n_lines = len(df_result)

    st.markdown(
        f"<div style='margin-top:14px; padding:12px 16px; background:#f0f0f0; "
        f"border:0.5px solid #E5E5E5; border-radius:8px; font-size:13px;'>"
        f"조회 조건으로 <b>{n_campaigns:,}개 캠페인</b> (매체 라인 {n_lines:,}건)이 확인되었습니다."
        f"</div>",
        unsafe_allow_html=True,
    )

    if n_campaigns == 0:
        st.stop()

    st.markdown(
        "<div style='margin-top:18px; font-size:13px; font-weight:600; margin-bottom:6px;'>"
        "미리보기 <span style='font-size:11px; font-weight:400; color:#666; margin-left:6px;'>"
        "상위 3개 캠페인 · 총액 순</span></div>",
        unsafe_allow_html=True,
    )
    st.markdown(_render_preview_html(groups[:3]), unsafe_allow_html=True)

    excel_bytes = _build_excel(groups)
    fname_parts = [sel_major]
    if sel_subs:
        fname_parts.append("-".join(sel_subs)[:30])
    fname = f"budget_history_{'_'.join(fname_parts)}.xlsx"

    st.markdown("<div style='margin-top:16px;'></div>", unsafe_allow_html=True)
    st.download_button(
        label=f"엑셀 다운로드 (전체 {n_campaigns:,}개 캠페인)",
        data=excel_bytes,
        file_name=fname,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
    )
