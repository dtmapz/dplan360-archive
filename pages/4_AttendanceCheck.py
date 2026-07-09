import streamlit as st
import pandas as pd
from datetime import date
from utils import db
from utils.auth import get_current_user
from utils.ui import set_current_page

set_current_page("attendance")

user = get_current_user()
user_email = user.get("email", "") if user else ""

today = date.today()
current_month = today.strftime("%Y-%m")


def build_table(events: list[dict], members: list[dict], attendance_map: dict,
                show_count: bool = True, all_events_for_count: list[dict] = None) -> str:
    """HTML 표 생성"""
    if not events or not members:
        return "<p style='color:var(--text-muted); font-size:13px;'>데이터가 없습니다.</p>"

    # 월별 이벤트 그룹
    from itertools import groupby
    month_events = {}
    for ev in events:
        m = ev["event_date"][:7]
        month_events.setdefault(m, []).append(ev)

    # 월별 컬럼 색상
    month_colors = [
        ("#E1F5EE", "#0F6E56", "#085041"),
        ("#E6F1FB", "#185FA5", "#0C447C"),
        ("#FAEEDA", "#854F0B", "#633806"),
        ("#FBEAF0", "#993556", "#72243E"),
        ("#EAF3DE", "#3B6D11", "#27500A"),
        ("#EEEDFE", "#534AB7", "#3C3489"),
    ]

    html = "<div style='overflow-x:auto;'><table style='width:100%; border-collapse:collapse; font-size:12px;'>"

    # 헤더 1행: 소속/구성원/참여횟수 + 월별 그룹
    html += "<thead><tr>"
    html += "<th rowspan='2' style='border:0.5px solid var(--border); padding:6px 10px; background:var(--surface-1); color:var(--text-secondary); font-weight:500; white-space:nowrap;'>소속</th>"
    html += "<th rowspan='2' style='border:0.5px solid var(--border); padding:6px 10px; background:var(--surface-1); color:var(--text-secondary); font-weight:500; white-space:nowrap;'>구성원</th>"
    if show_count:
        html += "<th rowspan='2' style='border:0.5px solid var(--border); padding:6px 10px; background:var(--surface-1); color:var(--text-secondary); font-weight:500; white-space:nowrap;'>26년 누적<br>참여횟수</th>"

    for i, (month, evs) in enumerate(month_events.items()):
        bg, fg, _ = month_colors[i % len(month_colors)]
        y, m = month.split("-")
        html += (f"<th colspan='{len(evs)}' style='border:0.5px solid var(--border); "
                 f"padding:6px 10px; background:{bg}; color:{fg}; font-weight:500;'>"
                 f"{int(m)}월</th>")
    html += "</tr>"

    # 헤더 2행: 행사별 날짜/이름
    html += "<tr>"
    for i, (month, evs) in enumerate(month_events.items()):
        bg, _, fg2 = month_colors[i % len(month_colors)]
        for ev in evs:
            d = date.fromisoformat(ev["event_date"])
            html += (f"<th style='border:0.5px solid var(--border); padding:5px 8px; "
                     f"background:{bg}; color:{fg2}; font-size:11px; white-space:nowrap;'>"
                     f"{d.month}/{d.day}<br>{ev['title']}</th>")
    html += "</tr></thead><tbody>"

    # 소속 그룹화
    from itertools import groupby as gby
    sorted_members = sorted(members, key=lambda x: (x.get("division", ""), x.get("team", ""), x.get("name", "")))

    def group_key(m):
        return f"{m.get('division', '')} {m.get('team', '')}".strip()

    prev_group = None
    group_rows = {}
    for m in sorted_members:
        g = group_key(m)
        group_rows.setdefault(g, []).append(m)

    for group, gmembers in group_rows.items():
        for idx, member in enumerate(gmembers):
            html += "<tr>"
            if idx == 0:
                html += (f"<td rowspan='{len(gmembers)}' style='border:0.5px solid var(--border); "
                         f"padding:6px 10px; background:var(--surface-1); font-weight:500; "
                         f"color:var(--text-secondary); white-space:nowrap; vertical-align:middle;'>"
                         f"{group}</td>")
            html += (f"<td style='border:0.5px solid var(--border); padding:6px 10px; "
                     f"text-align:left; white-space:nowrap;'>{member.get('name', '')}</td>")

            if show_count:
                base = all_events_for_count if all_events_for_count is not None else events
                count = sum(
                    1 for ev in base
                    if attendance_map.get((ev["id"], member.get("email", "")))
                )
                html += (f"<td style='border:0.5px solid var(--border); padding:6px 10px; "
                         f"text-align:center;'>{count}</td>")

            for evs in month_events.values():
                for ev in evs:
                    attended = attendance_map.get((ev["id"], member.get("email", "")), False)
                    cell = "<span style='color:#1D9E75; font-size:14px;'>✓</span>" if attended else ""
                    html += (f"<td style='border:0.5px solid var(--border); "
                             f"padding:6px 10px; text-align:center;'>{cell}</td>")
            html += "</tr>"

    html += "</tbody></table></div>"
    return html


# ---------- 데이터 로드 ----------
all_events = db.get_attendance_summary()
raw_members = db.get_client().table("organization").select("*").order("team").order("name").execute().data

# SP팀, team이 없는 경우(본부장/실장급) 제외
members_filtered = [
    m for m in raw_members
    if m.get("team") and m.get("team") not in ("SP팀", "-", "")
]

# 본부 순서 지정
division_order = ["미디어컨설팅본부", "그로스마케팅본부"]

def division_sort_key(m):
    div = m.get("division", "")
    try:
        return (division_order.index(div), m.get("team", ""), m.get("name", ""))
    except ValueError:
        return (len(division_order), m.get("team", ""), m.get("name", ""))

members = sorted(members_filtered, key=division_sort_key)

# 참석 맵: (event_id, email) -> bool
attendance_map = {}
for ev in all_events:
    for att in (ev.get("attendance") or []):
        if att.get("attended"):
            attendance_map[(ev["id"], att["member_email"])] = True

# 이번달 이후 vs 이전월 분리
current_future = [ev for ev in all_events if ev["event_date"][:7] >= current_month]
past = [ev for ev in all_events if ev["event_date"][:7] < current_month]

# 전체 참여횟수용: 모든 이벤트 기준
all_event_ids = {ev["id"] for ev in all_events}

# ---------- 이번달 이후 표 ----------
if current_future:
    st.markdown(
        f"<div style='font-size:13px; font-weight:500; color:var(--text-muted); margin-bottom:8px;'>"
        f"{today.year}년 {today.month}월 이후</div>",
        unsafe_allow_html=True,
    )
    # 참여횟수는 전체 누적 기준이므로 all_events 전달
    html = build_table(current_future, members, attendance_map, show_count=True, all_events_for_count=all_events)
    st.markdown(html, unsafe_allow_html=True)
else:
    st.caption("이번달 이후 등록된 행사가 없습니다.")

# ---------- 이전월 접기/펼치기 ----------
if past:
    past_months = sorted(set(ev["event_date"][:7] for ev in past))
    y_start, m_start = past_months[0].split("-")
    y_end, m_end = past_months[-1].split("-")
    label = f"{y_start}년 {int(m_start)}월 ~ {y_end}년 {int(m_end)}월 기록"

    with st.expander(label, expanded=False):
        html = build_table(past, members, attendance_map, show_count=False)
        st.markdown(html, unsafe_allow_html=True)
