import streamlit as st
from datetime import date, datetime
from utils.auth import get_current_user
from utils.ui import set_current_page

set_current_page("promotion")
user = get_current_user()

# ============================
# GCP / Sheets 연결
# ============================
try:
    from google.oauth2 import service_account
    import gspread
except ImportError as e:
    st.error(f"필수 패키지가 설치되지 않았습니다: {e}")
    st.stop()

PROMOTION_SHEET_ID = st.secrets.get("PROMOTION_SHEET_ID", "")
if "gcp_service_account" not in st.secrets or not PROMOTION_SHEET_ID:
    st.error("PROMOTION_SHEET_ID 또는 서비스 계정 정보가 설정되지 않았습니다.")
    st.stop()

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

PROMOTION_START = date(2026, 8, 1)
PROMOTION_END = date(2026, 12, 31)

# 매체 컬러
NETFLIX_COLOR = "#E50914"
SMR_COLOR = "#0066CC"
AMBER = "#F2A93B"


@st.cache_resource
def _get_gspread_client():
    creds = service_account.Credentials.from_service_account_info(
        dict(st.secrets["gcp_service_account"]),
        scopes=SCOPES,
    )
    return gspread.authorize(creds)


@st.cache_data(ttl=300, show_spinner=False)
def load_tab(tab_name: str) -> list[dict]:
    """netflix / smr 탭 데이터 조회. 5분 캐싱."""
    gc = _get_gspread_client()
    ws = gc.open_by_key(PROMOTION_SHEET_ID).worksheet(tab_name)
    return ws.get_all_records()


# ============================
# 데이터 처리 헬퍼
# ============================
def _to_int(val) -> int:
    """집행금액 문자열/숫자 → int. 공란은 0."""
    if val is None or val == "":
        return 0
    if isinstance(val, (int, float)):
        return int(val)
    s = str(val).replace(",", "").replace("₩", "").strip()
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return 0


def _parse_date(val):
    """YYYY-MM-DD 문자열 → date. 실패 시 None."""
    if not val:
        return None
    if isinstance(val, date):
        return val
    s = str(val).strip()
    for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def confirmed(rows):
    """상태=집행확정 필터"""
    return [r for r in rows if str(r.get("상태", "")).strip() == "집행확정"]


def proposed(rows):
    """제안일 존재 (취소 포함, 매출 제외 규칙과 별개)"""
    return [r for r in rows if _parse_date(r.get("제안일"))]


def team_revenue_rank(rows, top_n=5):
    """(담당본부+담당팀) 별 집행금액 합산 → 내림차순 Top N"""
    grouped = {}
    for r in confirmed(rows):
        div = str(r.get("담당본부", "")).strip()
        team = str(r.get("담당팀", "")).strip()
        if not div or not team:
            continue
        key = f"{div} {team}"
        grouped[key] = grouped.get(key, 0) + _to_int(r.get("집행금액"))
    ranked = sorted(grouped.items(), key=lambda x: x[1], reverse=True)
    return ranked[:top_n]


def single_max_execution(rows, top_n=3):
    """집행금액 MAX 행 기준 담당자 Top N (같은 담당자 다른 행은 각각)"""
    rows_c = [
        (r, _to_int(r.get("집행금액")))
        for r in confirmed(rows)
    ]
    rows_c.sort(key=lambda x: x[1], reverse=True)
    return rows_c[:top_n]


def first_new_execution(rows, top_n=3):
    """신규 광고주 집행확정 중 집행확정일 오름차순 Top N"""
    items = []
    for r in confirmed(rows):
        if str(r.get("신규 여부", "")).strip() != "신규":
            continue
        d = _parse_date(r.get("집행확정일"))
        if d:
            items.append((r, d))
    items.sort(key=lambda x: x[1])
    return items[:top_n]


def proposal_count_rank(rows, top_n=3):
    """담당자별 제안 건수(제안일 존재하는 모든 행 포함, 취소도 포함)"""
    counts = {}
    for r in proposed(rows):
        name = str(r.get("담당자명", "")).strip()
        if not name:
            continue
        counts[name] = counts.get(name, 0) + 1
    ranked = sorted(counts.items(), key=lambda x: x[1], reverse=True)
    return ranked[:top_n]


def total_revenue(rows) -> int:
    return sum(_to_int(r.get("집행금액")) for r in confirmed(rows))


def _fmt_krw(n: int) -> str:
    return f"₩ {n:,}"


def _fmt_date(d) -> str:
    return d.strftime("%Y-%m-%d") if d else "-"


# ============================
# UI 헬퍼
# ============================
RANK_EMOJI = {1: "🥇", 2: "🥈", 3: "🥉"}


def rank_label(i: int) -> str:
    return RANK_EMOJI.get(i, f"{i}위")


# ============================
# 데이터 로드
# ============================
try:
    netflix = load_tab("netflix")
    smr = load_tab("smr")
except Exception as e:
    st.error(f"프로모션 시트 조회 실패: {e}")
    st.stop()

# ============================
# 헤더
# ============================
today = date.today()
if today < PROMOTION_START:
    dday_label = f"D-{(PROMOTION_START - today).days} (시작 전)"
elif today > PROMOTION_END:
    dday_label = f"D+{(today - PROMOTION_END).days} (종료)"
else:
    dday_label = f"D-{(PROMOTION_END - today).days} 남음"

st.markdown(
    f"<div style='display:flex;align-items:baseline;gap:10px;margin-bottom:4px;'>"
    f"<span style='font-size:20px;font-weight:700;'>🏆 D-PLAN360 프로모션</span>"
    f"<span style='font-size:13px;color:var(--text-muted);'>"
    f"{PROMOTION_START} ~ {PROMOTION_END} · {dday_label}</span>"
    f"</div>",
    unsafe_allow_html=True,
)

# ============================
# 상단 KPI (Netflix / SMR 총 매출)
# ============================
netflix_total = total_revenue(netflix)
smr_total = total_revenue(smr)
netflix_confirmed_ct = len(confirmed(netflix))
netflix_proposed_ct = len(proposed(netflix))
smr_confirmed_ct = len(confirmed(smr))
smr_proposed_ct = len(proposed(smr))


def kpi_card(media_name, color, total, confirmed_ct, proposed_ct):
    return (
        f"<div style='background:#F5F5F5;border:0.5px solid #ddd;border-radius:12px;"
        f"padding:16px 20px;border-top:3px solid {color};'>"
        f"<div style='font-size:12px;color:var(--text-muted);margin-bottom:4px;'>"
        f"{media_name} 총 매출</div>"
        f"<div style='font-size:22px;font-weight:700;color:#111;margin-bottom:6px;'>"
        f"{_fmt_krw(total)}</div>"
        f"<div style='font-size:11px;color:var(--text-muted);'>"
        f"집행확정 {confirmed_ct}건 · 제안 {proposed_ct}건</div>"
        f"</div>"
    )


k1, k2 = st.columns(2)
with k1:
    st.markdown(
        kpi_card("Netflix", NETFLIX_COLOR, netflix_total, netflix_confirmed_ct, netflix_proposed_ct),
        unsafe_allow_html=True,
    )
with k2:
    st.markdown(
        kpi_card("SMR", SMR_COLOR, smr_total, smr_confirmed_ct, smr_proposed_ct),
        unsafe_allow_html=True,
    )

st.markdown("<div style='height:24px;'></div>", unsafe_allow_html=True)

# ============================
# 팀 시상 · Netflix 팀 매출 Top 5
# ============================
st.markdown(
    f"<div style='font-size:14px;font-weight:700;margin-bottom:8px;'>"
    f"🥇 팀 시상 · Netflix 팀 매출 Top 5</div>",
    unsafe_allow_html=True,
)

team_rank = team_revenue_rank(netflix, top_n=5)
if not team_rank:
    st.caption("아직 집행 데이터가 없습니다.")
else:
    max_val = team_rank[0][1] if team_rank[0][1] > 0 else 1
    bars_html = "<div style='background:#F5F5F5;border:0.5px solid #ddd;border-radius:12px;padding:14px 18px;'>"
    for i, (team, amount) in enumerate(team_rank, 1):
        pct = int(amount / max_val * 100) if max_val > 0 else 0
        bars_html += (
            f"<div style='margin-bottom:{8 if i < len(team_rank) else 0}px;'>"
            f"<div style='display:flex;justify-content:space-between;font-size:13px;margin-bottom:4px;'>"
            f"<span><b>{rank_label(i)}</b> {team}</span>"
            f"<span style='font-weight:600;color:#111;'>{_fmt_krw(amount)}</span>"
            f"</div>"
            f"<div style='background:#e8e8e8;border-radius:4px;height:8px;overflow:hidden;'>"
            f"<div style='background:{AMBER};width:{pct}%;height:100%;'></div>"
            f"</div>"
            f"</div>"
        )
    bars_html += "</div>"
    st.markdown(bars_html, unsafe_allow_html=True)

st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)

# ============================
# 개인 시상 (6장 카드)
# ============================
st.markdown(
    "<div style='font-size:14px;font-weight:700;margin-bottom:8px;'>🥇 개인 시상 현황</div>",
    unsafe_allow_html=True,
)

def award_card(title, badge_color, first_line, sub_lines, runner_ups):
    """개인 시상 카드 HTML. sub_lines: list[str], runner_ups: list[(name, value)]"""
    sub_html = "".join(
        f"<div style='font-size:12px;color:var(--text-muted);'>{s}</div>"
        for s in sub_lines if s
    )
    if runner_ups:
        ru_html = (
            "<div style='border-top:0.5px solid #ddd;margin-top:10px;padding-top:8px;'>"
            + "".join(
                f"<div style='font-size:12px;color:#666;margin-bottom:2px;'>"
                f"{rank_label(i+2)} {name} <span style='color:#999;'>{val}</span></div>"
                for i, (name, val) in enumerate(runner_ups)
            )
            + "</div>"
        )
    else:
        ru_html = ""

    return (
        f"<div style='background:#F5F5F5;border:0.5px solid #ddd;border-radius:12px;"
        f"padding:14px 18px;border-top:3px solid {badge_color};height:100%;'>"
        f"<div style='font-size:12px;color:var(--text-muted);margin-bottom:8px;'>{title}</div>"
        f"<div style='font-size:18px;font-weight:700;color:#111;margin-bottom:2px;'>"
        f"🥇 {first_line}</div>"
        f"{sub_html}"
        f"{ru_html}"
        f"</div>"
    )


def empty_card(title, badge_color):
    return (
        f"<div style='background:#F5F5F5;border:0.5px solid #ddd;border-radius:12px;"
        f"padding:14px 18px;border-top:3px solid {badge_color};height:100%;'>"
        f"<div style='font-size:12px;color:var(--text-muted);margin-bottom:8px;'>{title}</div>"
        f"<div style='font-size:13px;color:#999;'>아직 데이터가 없습니다.</div>"
        f"</div>"
    )


# 지표 #2: Netflix 단일 최다집행
nf_single = single_max_execution(netflix, top_n=3)
if nf_single:
    top_row, top_val = nf_single[0]
    card_1 = award_card(
        "🎬 Netflix 단일 광고주 최다 집행",
        NETFLIX_COLOR,
        str(top_row.get("담당자명", "-")),
        [
            _fmt_krw(top_val),
            f"{top_row.get('광고주명', '-')} · {top_row.get('캠페인명', '')}",
        ],
        [(str(r.get("담당자명", "-")), _fmt_krw(v)) for r, v in nf_single[1:]],
    )
else:
    card_1 = empty_card("🎬 Netflix 단일 광고주 최다 집행", NETFLIX_COLOR)

# 지표 #3: Netflix 최초 신규 광고주 캠페인 집행
nf_first_new = first_new_execution(netflix, top_n=3)
if nf_first_new:
    top_row, top_dt = nf_first_new[0]
    card_2 = award_card(
        "🎬 Netflix 최초 신규 광고주 집행",
        NETFLIX_COLOR,
        str(top_row.get("담당자명", "-")),
        [_fmt_date(top_dt), str(top_row.get("광고주명", "-"))],
        [(str(r.get("담당자명", "-")), _fmt_date(d)) for r, d in nf_first_new[1:]],
    )
else:
    card_2 = empty_card("🎬 Netflix 최초 신규 광고주 집행", NETFLIX_COLOR)

# 지표 #4: SMR 최초 신규 광고주 캠페인 집행
sm_first_new = first_new_execution(smr, top_n=3)
if sm_first_new:
    top_row, top_dt = sm_first_new[0]
    card_3 = award_card(
        "📺 SMR 최초 신규 광고주 집행",
        SMR_COLOR,
        str(top_row.get("담당자명", "-")),
        [_fmt_date(top_dt), str(top_row.get("광고주명", "-"))],
        [(str(r.get("담당자명", "-")), _fmt_date(d)) for r, d in sm_first_new[1:]],
    )
else:
    card_3 = empty_card("📺 SMR 최초 신규 광고주 집행", SMR_COLOR)

# 지표 #5: Netflix 최다 제안
nf_prop = proposal_count_rank(netflix, top_n=3)
if nf_prop:
    top_name, top_ct = nf_prop[0]
    card_4 = award_card(
        "🎬 Netflix 최다 캠페인 제안",
        NETFLIX_COLOR,
        top_name,
        [f"{top_ct}건"],
        [(n, f"{v}건") for n, v in nf_prop[1:]],
    )
else:
    card_4 = empty_card("🎬 Netflix 최다 캠페인 제안", NETFLIX_COLOR)

# 지표 #6: SMR 최다 제안
sm_prop = proposal_count_rank(smr, top_n=3)
if sm_prop:
    top_name, top_ct = sm_prop[0]
    card_5 = award_card(
        "📺 SMR 최다 캠페인 제안",
        SMR_COLOR,
        top_name,
        [f"{top_ct}건"],
        [(n, f"{v}건") for n, v in sm_prop[1:]],
    )
else:
    card_5 = empty_card("📺 SMR 최다 캠페인 제안", SMR_COLOR)

# 카드 배치 (3장 + 2장)
r1_a, r1_b, r1_c = st.columns(3)
with r1_a: st.markdown(card_1, unsafe_allow_html=True)
with r1_b: st.markdown(card_2, unsafe_allow_html=True)
with r1_c: st.markdown(card_3, unsafe_allow_html=True)

st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)

r2_a, r2_b, r2_c = st.columns(3)
with r2_a: st.markdown(card_4, unsafe_allow_html=True)
with r2_b: st.markdown(card_5, unsafe_allow_html=True)
# r2_c는 여백

st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)

# ============================
# 카테고리별 리더보드 (매체 x 지표 조합 · Top 10)
# ============================
st.markdown(
    "<div style='font-size:14px;font-weight:700;margin-bottom:8px;'>📋 카테고리별 리더보드 (Top 10)</div>",
    unsafe_allow_html=True,
)

lb_col1, lb_col2 = st.columns([1, 1])
with lb_col1:
    lb_media = st.radio(
        "매체", ["Netflix", "SMR"], horizontal=True, label_visibility="collapsed", key="lb_media"
    )
with lb_col2:
    lb_metric = st.radio(
        "지표", ["매출", "제안 건수", "집행 건수"], horizontal=True,
        label_visibility="collapsed", key="lb_metric"
    )

lb_rows = netflix if lb_media == "Netflix" else smr
lb_color = NETFLIX_COLOR if lb_media == "Netflix" else SMR_COLOR


def leaderboard(rows, metric, top_n=10):
    if metric == "매출":
        agg = {}
        for r in confirmed(rows):
            name = str(r.get("담당자명", "")).strip()
            if not name:
                continue
            key = (name, str(r.get("담당본부", "")).strip(), str(r.get("담당팀", "")).strip())
            agg[key] = agg.get(key, 0) + _to_int(r.get("집행금액"))
        ranked = sorted(agg.items(), key=lambda x: x[1], reverse=True)
        return [(k[0], f"{k[1]} {k[2]}", _fmt_krw(v)) for k, v in ranked[:top_n]]
    elif metric == "제안 건수":
        agg = {}
        for r in proposed(rows):
            name = str(r.get("담당자명", "")).strip()
            if not name:
                continue
            key = (name, str(r.get("담당본부", "")).strip(), str(r.get("담당팀", "")).strip())
            agg[key] = agg.get(key, 0) + 1
        ranked = sorted(agg.items(), key=lambda x: x[1], reverse=True)
        return [(k[0], f"{k[1]} {k[2]}", f"{v}건") for k, v in ranked[:top_n]]
    else:  # 집행 건수
        agg = {}
        for r in confirmed(rows):
            name = str(r.get("담당자명", "")).strip()
            if not name:
                continue
            key = (name, str(r.get("담당본부", "")).strip(), str(r.get("담당팀", "")).strip())
            agg[key] = agg.get(key, 0) + 1
        ranked = sorted(agg.items(), key=lambda x: x[1], reverse=True)
        return [(k[0], f"{k[1]} {k[2]}", f"{v}건") for k, v in ranked[:top_n]]


lb_data = leaderboard(lb_rows, lb_metric, top_n=10)

if not lb_data:
    st.caption("조건에 맞는 데이터가 없습니다.")
else:
    table_html = (
        f"<div style='background:#F5F5F5;border:0.5px solid #ddd;border-radius:12px;"
        f"padding:8px 0;border-top:3px solid {lb_color};overflow:hidden;'>"
        f"<table style='width:100%;border-collapse:collapse;'>"
        f"<thead>"
        f"<tr style='font-size:12px;color:var(--text-muted);'>"
        f"<th style='padding:8px 12px;text-align:center;width:56px;'>순위</th>"
        f"<th style='padding:8px 12px;text-align:left;'>담당자</th>"
        f"<th style='padding:8px 12px;text-align:left;'>소속</th>"
        f"<th style='padding:8px 12px;text-align:right;width:140px;'>{lb_metric}</th>"
        f"</tr>"
        f"</thead><tbody>"
    )
    for i, (name, team, val) in enumerate(lb_data, 1):
        table_html += (
            f"<tr style='font-size:13px;border-top:0.5px solid #e0e0e0;'>"
            f"<td style='padding:8px 12px;text-align:center;'>{rank_label(i)}</td>"
            f"<td style='padding:8px 12px;'>{name}</td>"
            f"<td style='padding:8px 12px;color:#666;'>{team}</td>"
            f"<td style='padding:8px 12px;text-align:right;font-weight:600;'>{val}</td>"
            f"</tr>"
        )
    table_html += "</tbody></table></div>"
    st.markdown(table_html, unsafe_allow_html=True)

# ============================
# 하단 안내
# ============================
st.markdown(
    "<div style='margin-top:24px;padding:10px 14px;background:#FFF8E1;"
    "border-left:3px solid #F2A93B;border-radius:4px;font-size:11px;color:#111;'>"
    "ℹ️ 시트 데이터는 5분마다 자동 반영됩니다. 취소 건은 제안 카운트에 포함되지만 매출 집계에서는 제외됩니다."
    "</div>",
    unsafe_allow_html=True,
)
