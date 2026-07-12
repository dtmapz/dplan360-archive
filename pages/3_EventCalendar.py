import streamlit as st
from datetime import datetime, date
import re
from utils import db
from utils.auth import get_current_user, is_admin
from utils.ui import set_current_page

set_current_page("calendar")

user = get_current_user()
user_email = user.get("email", "") if user else ""
admin = is_admin()

today = date.today()
current_month = today.strftime("%Y-%m")


def get_category_color_map() -> dict:
    cats = db.get_event_categories()
    return {c["name"]: c["color"] for c in cats}


def category_color(cat: str, color_map: dict) -> str:
    return color_map.get(cat, "#888780")


@st.dialog("행사 상세")
def event_detail_dialog(event: dict):
    color_map = get_category_color_map()
    cat = event.get("category", "-")
    color = category_color(cat, color_map)
    edit_mode = st.session_state.get(f"event_edit_{event['id']}", False)

    # 헤더: 구분뱃지 + 행사명 + 수정버튼
    if admin:
        col_info, col_btn = st.columns([5, 1])
    else:
        col_info = st.container()
        col_btn = None

    with col_info:
        st.markdown(
            f"<div style='display:flex; align-items:center; gap:10px; margin-bottom:4px;'>"
            f"<span style='background:{color}; color:#fff; font-size:12px; "
            f"padding:3px 10px; border-radius:4px; white-space:nowrap;'>{cat}</span>"
            f"<span style='font-size:15px; font-weight:500;'>{event['title']}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )

    if admin and col_btn:
        with col_btn:
            if st.button("수정", key=f"ev_edit_{event['id']}"):
                st.session_state[f"event_edit_{event['id']}"] = not edit_mode
                st.rerun()

    if not edit_mode:
        s = event.get("start_time", "")[:5] if event.get("start_time") else ""
        e = event.get("end_time", "")[:5] if event.get("end_time") else ""
        st.write(f"**일시**: {event['event_date']} {s} ~ {e}")
        st.write(f"**장소**: {event.get('venue', '-')}")
        if event.get("memo"):
            st.write(f"**메모**: {event['memo']}")

        if admin:
            new_req = st.toggle(
                "참석 여부 설정",
                value=bool(event.get("requires_check")),
                key=f"req_toggle_{event['id']}",
            )
            if new_req != bool(event.get("requires_check")):
                db.update_event(event["id"], requires_check=new_req)
                st.rerun()

        if not admin and event.get("requires_check"):
            attended_ids = st.session_state.get("my_attendance", [])
            current = event["id"] in attended_ids
            new_val = st.toggle("참석 여부", value=current, key=f"att_{event['id']}")
            if new_val != current:
                db.toggle_attendance(event["id"], user_email, new_val)
                st.session_state["my_attendance"] = (
                    attended_ids + [event["id"]] if new_val
                    else [x for x in attended_ids if x != event["id"]]
                )
                st.rerun()

        if admin:
            st.divider()
            if st.button("행사 삭제", key=f"del_{event['id']}"):
                db.delete_event(event["id"])
                st.session_state["_cal_dialog"] = None
                st.rerun()

    else:
        title = st.text_input("행사명", value=event["title"])
        event_date = st.date_input("날짜", value=date.fromisoformat(event["event_date"]))
        col_s, col_e = st.columns(2)
        with col_s:
            start_time_str = st.text_input("시작 시간 (HH:MM)",
                value=event.get("start_time", "")[:5], key="edit_start")
        with col_e:
            end_time_str = st.text_input("종료 시간 (HH:MM)",
                value=event.get("end_time", "")[:5], key="edit_end")

        all_cats = db.get_event_categories()
        cat_names = [c["name"] for c in all_cats]
        cur_idx = cat_names.index(event.get("category")) if event.get("category") in cat_names else 0
        category = st.selectbox("구분", cat_names, index=cur_idx)
        venue = st.text_input("장소", value=event.get("venue", ""))
        memo = st.text_area("메모", value=event.get("memo", "") or "", height=80)

        if st.button("저장", type="primary"):
            time_pattern = re.compile(r"^\d{2}:\d{2}$")
            if not title or not venue:
                st.error("행사명과 장소는 필수입니다.")
            elif not time_pattern.match(start_time_str) or not time_pattern.match(end_time_str):
                st.error("시간 형식이 올바르지 않습니다. HH:MM 형식으로 입력해주세요.")
            elif start_time_str >= end_time_str:
                st.error("종료 시간은 시작 시간보다 늦어야 합니다.")
            else:
                db.update_event(event["id"],
                    title=title, event_date=str(event_date),
                    start_time=start_time_str, end_time=end_time_str,
                    category=category, venue=venue, memo=memo or None)
                st.session_state[f"event_edit_{event['id']}"] = False
                st.session_state["_cal_dialog"] = None
                st.rerun()


# ---------- 메인 ----------
if "my_attendance" not in st.session_state:
    st.session_state["my_attendance"] = db.get_my_attendance(user_email)

if st.session_state.pop("_event_registered", False):
    st.success("행사가 등록되었습니다.")


if admin:
    tab_cal, tab_list, tab_att, tab_reg = st.tabs(["월별 달력", "리스트", "교육 참여 체크", "+ 행사 등록"])
else:
    tab_cal, tab_list, tab_att = st.tabs(["월별 달력", "리스트", "교육 참여 체크"])
    tab_reg = None

# ---------- 월별 달력 ----------
with tab_cal:
    try:
        from streamlit_calendar import calendar as st_calendar

        events = db.get_all_events()
        color_map = get_category_color_map()
        cal_events = []
        for ev in events:
            color = category_color(ev.get("category", ""), color_map)
            cat = ev.get("category", "")
            s = ev.get("start_time", "")[:5] if ev.get("start_time") else ""
            end_t = ev.get("end_time", "")[:5] if ev.get("end_time") else ""
            start = ev["event_date"] + (f"T{s}" if s else "")
            end = ev["event_date"] + (f"T{end_t}" if end_t else "")
            cal_events.append({
                "id": ev["id"],
                "title": f"{ev['title']} [{cat}]",
                "start": start,
                "end": end,
                "backgroundColor": color,
                "borderColor": color,
                "textColor": "#ffffff",
                "extendedProps": ev,
            })

        cal_options = {
            "initialView": "dayGridMonth",
            "locale": "ko",
            "headerToolbar": {
                "left": "today prev,next",
                "center": "title",
                "right": "",
            },
            "height": 650,
            "selectable": False,
            "editable": False,
        }

        cal_result = st_calendar(events=cal_events, options=cal_options, key="main_cal")

        if cal_result and cal_result.get("eventClick"):
            clicked_id = cal_result["eventClick"]["event"]["id"]
            if st.session_state.get("_cal_dialog") != clicked_id:
                st.session_state["_cal_dialog"] = clicked_id
                st.rerun()

    except ImportError:
        st.error("streamlit-calendar 패키지가 필요합니다.")

# ---------- 리스트 ----------
with tab_list:
    events = db.get_all_events()
    color_map = get_category_color_map()
    attended_ids = st.session_state.get("my_attendance", [])

    if not events:
        st.caption("등록된 행사가 없습니다.")
    else:
        from itertools import groupby
        weekdays = ["월", "화", "수", "목", "금", "토", "일"]

        def month_key(ev):
            return ev["event_date"][:7]

        # 현재월 이후 / 과거 분리
        future_events = [ev for ev in events if ev["event_date"][:7] >= current_month]
        past_events = [ev for ev in events if ev["event_date"][:7] < current_month]

        def render_event_card(ev, m_int):
            color = category_color(ev.get("category", ""), color_map)
            cat = ev.get("category", "")
            s = ev.get("start_time", "")[:5] if ev.get("start_time") else ""
            e = ev.get("end_time", "")[:5] if ev.get("end_time") else ""
            venue = ev.get("venue", "")
            d = date.fromisoformat(ev["event_date"])
            date_label = f"{m_int}월 {d.day}일 ({weekdays[d.weekday()]})"

            col_card, col_toggle = st.columns([6, 1])
            with col_card:
                st.markdown(
                    f"<div style='display:flex; align-items:center; gap:10px; "
                    f"padding:10px 14px; background:var(--surface-2); "
                    f"border:0.5px solid var(--border); border-radius:8px; "
                    f"border-left:4px solid {color}; margin-bottom:6px;'>"
                    f"<span style='background:{color}; color:#fff; font-size:11px; "
                    f"padding:2px 8px; border-radius:4px; white-space:nowrap;'>{cat}</span>"
                    f"<span style='font-size:13px; font-weight:500; color:var(--text-primary);'>{ev['title']}</span>"
                    f"<span style='font-size:13px; color:var(--text-muted);'>{s}~{e} · {venue}</span>"
                    f"<span style='font-size:13px; color:var(--text-muted); margin-left:auto; white-space:nowrap;'>{date_label}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
            with col_toggle:
                if admin:
                    new_req = st.toggle("참석설정", value=bool(ev.get("requires_check")),
                                        key=f"list_req_{ev['id']}")
                    if new_req != bool(ev.get("requires_check")):
                        db.update_event(ev["id"], requires_check=new_req)
                        st.rerun()
                elif ev.get("requires_check"):
                    current_att = ev["id"] in attended_ids
                    new_val = st.toggle("참석", value=current_att, key=f"list_att_{ev['id']}")
                    if new_val != current_att:
                        db.toggle_attendance(ev["id"], user_email, new_val)
                        st.session_state["my_attendance"] = (
                            attended_ids + [ev["id"]] if new_val
                            else [x for x in attended_ids if x != ev["id"]]
                        )
                        st.rerun()

        # 현재월 이후: 월별 펼친 상태
        for month, month_evs in groupby(future_events, key=month_key):
            y, m = month.split("-")
            with st.expander(f"{y}년 {int(m)}월", expanded=True):
                for ev in list(month_evs):
                    render_event_card(ev, int(m))

        # 과거: 하나로 통합, 접힌 상태
        if past_events:
            past_months = sorted(set(ev["event_date"][:7] for ev in past_events))
            first_y, first_m = past_months[0].split("-")
            last_y, last_m = past_months[-1].split("-")
            label = f"{first_y}년 {int(first_m)}월 ~ {last_y}년 {int(last_m)}월 기록"
            with st.expander(label, expanded=False):
                for ev in past_events:
                    m_int = int(ev["event_date"][5:7])
                    render_event_card(ev, m_int)



# ---------- 교육 참여 체크 ----------
with tab_att:
    month_colors = [
        ("#E1F5EE", "#0F6E56", "#085041"),
        ("#E6F1FB", "#185FA5", "#0C447C"),
        ("#FAEEDA", "#854F0B", "#633806"),
        ("#FBEAF0", "#993556", "#72243E"),
        ("#EAF3DE", "#3B6D11", "#27500A"),
        ("#EEEDFE", "#534AB7", "#3C3489"),
    ]

    def build_attendance_table(events_list, members_list, att_map,
                               show_count=True, all_events_for_count=None):
        if not events_list or not members_list:
            return "<p style='color:var(--text-muted); font-size:13px;'>데이터가 없습니다.</p>"

        month_events = {}
        for ev in events_list:
            m = ev["event_date"][:7]
            month_events.setdefault(m, []).append(ev)

        html = "<div style='overflow-x:auto;'><table style='border-collapse:collapse; font-size:13px; min-width:100%;'>"
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
        html += "</tr><tr>"
        for i, (month, evs) in enumerate(month_events.items()):
            bg, _, fg2 = month_colors[i % len(month_colors)]
            for ev in evs:
                d = date.fromisoformat(ev["event_date"])
                html += (f"<th style='border:0.5px solid var(--border); padding:5px 8px; "
                         f"background:{bg}; color:{fg2}; font-size:11px; white-space:nowrap;'>"
                         f"{d.month}/{d.day}<br>{ev['title']}</th>")
        html += "</tr>"

        html += "<tr>"
        html += "<th style='border:0.5px solid var(--border); padding:5px 8px; background:var(--surface-1);'></th>"
        html += "<th style='border:0.5px solid var(--border); padding:5px 8px; background:var(--surface-1);'></th>"
        if show_count:
            html += "<th style='border:0.5px solid var(--border); padding:5px 8px; background:var(--surface-1);'></th>"
        for i, (month, evs) in enumerate(month_events.items()):
            bg, _, fg2 = month_colors[i % len(month_colors)]
            for ev in evs:
                count = sum(
                    1 for mbr in members_list
                    if att_map.get((ev["id"], mbr.get("email", "")))
                )
                html += (f"<th style='border:0.5px solid var(--border); padding:5px 8px; "
                         f"background:{bg}; color:{fg2}; font-size:11px; white-space:nowrap;'>"
                         f"참여 {count}명</th>")
        html += "</tr></thead><tbody>"

        sorted_members = sorted(members_list, key=lambda x: (x.get("division", ""), x.get("team", ""), x.get("name", "")))
        group_rows = {}
        for mbr in sorted_members:
            g = f"{mbr.get('division', '')} {mbr.get('team', '')}".strip()
            group_rows.setdefault(g, []).append(mbr)

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
                    base = all_events_for_count if all_events_for_count is not None else events_list
                    cnt = sum(1 for ev in base if att_map.get((ev["id"], member.get("email", ""))))
                    html += (f"<td style='border:0.5px solid var(--border); padding:6px 10px; "
                             f"text-align:center;'>{cnt}</td>")
                for evs in month_events.values():
                    for ev in evs:
                        attended = att_map.get((ev["id"], member.get("email", "")), False)
                        cell = "<span style='color:#1D9E75; font-size:14px;'>✓</span>" if attended else ""
                        html += (f"<td style='border:0.5px solid var(--border); "
                                 f"padding:6px 10px; text-align:center;'>{cell}</td>")
                html += "</tr>"

        html += "</tbody></table></div>"
        return html

    # 데이터 로드
    att_all_events = db.get_attendance_summary()
    raw_members = db.get_client().table("organization").select("*").order("team").order("name").execute().data
    att_members = [m for m in raw_members if m.get("team") and m.get("team") not in ("SP팀", "-", "")]
    division_order = ["미디어컨설팅본부", "그로스마케팅본부"]

    def div_key(m):
        div = m.get("division", "")
        try:
            return (division_order.index(div), m.get("team", ""), m.get("name", ""))
        except ValueError:
            return (len(division_order), m.get("team", ""), m.get("name", ""))

    att_members = sorted(att_members, key=div_key)

    att_map = {}
    for ev in att_all_events:
        for att in (ev.get("attendance") or []):
            if att.get("attended"):
                att_map[(ev["id"], att["member_email"])] = True

    total_members = len(att_members)
    total_events = len(att_all_events)

    # ===== 대시보드 데이터 계산 =====

    # 인원별 참여 횟수
    member_counts = {}
    for mbr in att_members:
        email = mbr.get("email", "")
        name = mbr.get("name", "")
        team = mbr.get("team", "")
        cnt = sum(1 for ev in att_all_events if att_map.get((ev["id"], email)))
        member_counts[email] = {"name": name, "team": team, "count": cnt}

    # 팀별 평균 참여 횟수
    team_totals = {}
    for info in member_counts.values():
        team = info["team"]
        team_totals.setdefault(team, []).append(info["count"])
    team_avg = {t: sum(counts) / len(counts) for t, counts in team_totals.items() if counts}
    team_avg_sorted = sorted(team_avg.items(), key=lambda x: x[1], reverse=True)

    # Top 10 참여자
    top10 = sorted(member_counts.values(), key=lambda x: x["count"], reverse=True)[:10]

    # 월별 참여율
    monthly_rates = {}
    for ev in att_all_events:
        m = ev["event_date"][:7]
        monthly_rates.setdefault(m, []).append(ev)
    month_rate_data = {}
    for m, evs in sorted(monthly_rates.items()):
        total_slots = len(evs) * total_members
        attended_slots = sum(1 for ev in evs for mbr in att_members if att_map.get((ev["id"], mbr.get("email", ""))))
        month_rate_data[m] = round(attended_slots / total_slots * 100, 1) if total_slots > 0 else 0

    # 행사별 참여율 Top 5
    event_rates = []
    for ev in att_all_events:
        cnt = sum(1 for mbr in att_members if att_map.get((ev["id"], mbr.get("email", ""))))
        rate = round(cnt / total_members * 100, 1) if total_members > 0 else 0
        event_rates.append({"title": ev["title"], "date": ev["event_date"], "rate": rate})
    event_rates_sorted = sorted(event_rates, key=lambda x: x["rate"], reverse=True)[:5]

    # 참여율 구간 분포
    member_rates_list = []
    for info in member_counts.values():
        r = round(info["count"] / total_events * 100, 1) if total_events > 0 else 0
        member_rates_list.append(r)
    high = sum(1 for r in member_rates_list if r >= 80)
    mid = sum(1 for r in member_rates_list if 50 <= r < 80)
    low = sum(1 for r in member_rates_list if r < 50)

    # ===== 대시보드 렌더링 =====

    # Row 1: 팀별 평균 참여 + Top 10
    col_team, col_top = st.columns([1.2, 0.8])
    with col_team:
        st.markdown("<div style='font-size:14px;font-weight:600;margin-bottom:10px;'>팀별 평균 참여 횟수</div>", unsafe_allow_html=True)
        if team_avg_sorted:
            max_avg = team_avg_sorted[0][1] if team_avg_sorted else 1
            bars_html = ""
            for team, avg in team_avg_sorted:
                pct = min(avg / max_avg * 100, 100)
                bars_html += (
                    f"<div style='display:flex;align-items:center;gap:8px;margin-bottom:8px;'>"
                    f"<div style='font-size:12px;width:110px;text-align:right;color:var(--text-secondary);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'>{team}</div>"
                    f"<div style='flex:1;height:18px;background:var(--surface-2);border-radius:4px;overflow:hidden;'>"
                    f"<div style='height:100%;width:{pct}%;background:#1D9E75;border-radius:4px;display:flex;align-items:center;padding-left:6px;font-size:10px;color:#fff;'>{avg:.1f}회</div>"
                    f"</div></div>"
                )
            st.markdown(bars_html, unsafe_allow_html=True)
        else:
            st.caption("데이터가 없습니다.")

    with col_top:
        st.markdown("<div style='font-size:14px;font-weight:600;margin-bottom:10px;'>참여 횟수 Top 10</div>", unsafe_allow_html=True)
        if top10:
            rank_html = ""
            for i, info in enumerate(top10, 1):
                rank_html += (
                    f"<div style='display:flex;align-items:center;gap:8px;padding:5px 0;"
                    f"border-bottom:0.5px solid var(--border);'>"
                    f"<div style='width:20px;font-size:12px;font-weight:600;color:var(--text-muted);text-align:center;'>{i}</div>"
                    f"<div style='font-size:12px;flex:1;'>{info['name']}</div>"
                    f"<div style='font-size:12px;font-weight:600;color:#1D9E75;'>{info['count']}회</div>"
                    f"</div>"
                )
            st.markdown(rank_html, unsafe_allow_html=True)
        else:
            st.caption("데이터가 없습니다.")

    st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)

    # Row 2: 월별 참여율 추이
    st.markdown("<div style='font-size:14px;font-weight:600;margin-bottom:10px;'>월별 전체 참여율 추이</div>", unsafe_allow_html=True)
    if month_rate_data:
        import altair as alt
        import pandas as pd
        chart_data = pd.DataFrame([
            {"월": f"{int(m.split('-')[1])}월", "참여율": rate, "sort": m}
            for m, rate in month_rate_data.items()
        ]).sort_values("sort")
        chart = alt.Chart(chart_data).mark_line(
            point=alt.OverlayMarkDef(filled=True, size=50),
            color="#1D9E75",
            strokeWidth=2.5
        ).encode(
            x=alt.X("월:N", sort=chart_data["월"].tolist(), axis=alt.Axis(labelAngle=0)),
            y=alt.Y("참여율:Q", scale=alt.Scale(domain=[0, 100]), title="참여율 (%)"),
            tooltip=["월", "참여율"]
        ).properties(height=200, width="container")
        st.altair_chart(chart, use_container_width=True)
    else:
        st.caption("데이터가 없습니다.")

    st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)

    # Row 3: 행사별 참여율 Top 5 + 참여율 구간 분포 도넛
    col_ev, col_donut = st.columns([1.2, 0.8])
    with col_ev:
        st.markdown("<div style='font-size:14px;font-weight:600;margin-bottom:10px;'>참여율 높은 행사 Top 5</div>", unsafe_allow_html=True)
        if event_rates_sorted:
            ev_bars = ""
            for info in event_rates_sorted:
                d = date.fromisoformat(info["date"])
                label = f"{info['title']} ({d.month}/{d.day})"
                ev_bars += (
                    f"<div style='display:flex;align-items:center;gap:8px;margin-bottom:8px;'>"
                    f"<div style='font-size:12px;width:160px;text-align:right;color:var(--text-secondary);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'>{label}</div>"
                    f"<div style='flex:1;height:18px;background:var(--surface-2);border-radius:4px;overflow:hidden;'>"
                    f"<div style='height:100%;width:{info['rate']}%;background:#185FA5;border-radius:4px;display:flex;align-items:center;padding-left:6px;font-size:10px;color:#fff;'>{info['rate']}%</div>"
                    f"</div></div>"
                )
            st.markdown(ev_bars, unsafe_allow_html=True)
        else:
            st.caption("데이터가 없습니다.")

    with col_donut:
        st.markdown("<div style='font-size:14px;font-weight:600;margin-bottom:10px;'>참여율 구간 분포</div>", unsafe_allow_html=True)
        total_p = high + mid + low
        if total_p > 0:
            h_pct = round(high / total_p * 100)
            m_pct = round(mid / total_p * 100)
            l_pct = 100 - h_pct - m_pct
            # SVG 도넛
            circumference = 2 * 3.14159 * 48
            h_len = circumference * h_pct / 100
            m_len = circumference * m_pct / 100
            l_len = circumference * l_pct / 100
            donut_svg = (
                f"<div style='display:flex;align-items:center;gap:20px;justify-content:center;'>"
                f"<svg viewBox='0 0 120 120' width='110' height='110'>"
                f"<circle cx='60' cy='60' r='48' fill='none' stroke='#1D9E75' stroke-width='20' "
                f"stroke-dasharray='{h_len} {circumference - h_len}' stroke-dashoffset='0' transform='rotate(-90 60 60)'/>"
                f"<circle cx='60' cy='60' r='48' fill='none' stroke='#F59E0B' stroke-width='20' "
                f"stroke-dasharray='{m_len} {circumference - m_len}' stroke-dashoffset='-{h_len}' transform='rotate(-90 60 60)'/>"
                f"<circle cx='60' cy='60' r='48' fill='none' stroke='#EF4444' stroke-width='20' "
                f"stroke-dasharray='{l_len} {circumference - l_len}' stroke-dashoffset='-{h_len + m_len}' transform='rotate(-90 60 60)'/>"
                f"<text x='60' y='58' font-size='14' font-weight='600' fill='var(--text-primary)' text-anchor='middle'>{total_p}명</text>"
                f"<text x='60' y='72' font-size='10' fill='var(--text-muted)' text-anchor='middle'>전체</text>"
                f"</svg>"
                f"<div style='display:flex;flex-direction:column;gap:6px;'>"
                f"<div style='display:flex;align-items:center;gap:6px;font-size:12px;color:var(--text-secondary);'>"
                f"<span style='display:inline-block;width:10px;height:10px;border-radius:2px;background:#1D9E75;'></span>80%↑ {high}명 ({h_pct}%)</div>"
                f"<div style='display:flex;align-items:center;gap:6px;font-size:12px;color:var(--text-secondary);'>"
                f"<span style='display:inline-block;width:10px;height:10px;border-radius:2px;background:#F59E0B;'></span>50~80% {mid}명 ({m_pct}%)</div>"
                f"<div style='display:flex;align-items:center;gap:6px;font-size:12px;color:var(--text-secondary);'>"
                f"<span style='display:inline-block;width:10px;height:10px;border-radius:2px;background:#EF4444;'></span>50%↓ {low}명 ({l_pct}%)</div>"
                f"</div></div>"
            )
            st.markdown(donut_svg, unsafe_allow_html=True)
        else:
            st.caption("데이터가 없습니다.")

    # ===== 관리자 전용: 전체 인원 테이블 =====
    if admin:
        st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)
        with st.expander("전체 인원 참여 현황 상세 테이블", expanded=False):
            if att_all_events:
                html = build_attendance_table(att_all_events, att_members, att_map,
                                              show_count=True, all_events_for_count=att_all_events)
                st.markdown(html, unsafe_allow_html=True)
            else:
                st.caption("등록된 행사가 없습니다.")

# ---------- 행사 등록 ----------
if tab_reg is not None:
    with tab_reg:
        all_cats = db.get_event_categories()
        cat_names = [c["name"] for c in all_cats]
        cat_options = cat_names + ["+ 새 구분 추가"]
        cat_choice = st.selectbox("구분*", cat_options, key="reg_cat")

        if cat_choice == "+ 새 구분 추가":
            new_cat = st.text_input("새 구분명 입력", key="new_cat_input")
            new_color = st.color_picker("색상 선택", value="#4F8EF7", key="new_cat_color")
            if st.button("추가", key="add_cat_btn"):
                if not new_cat:
                    st.error("구분명을 입력해주세요.")
                elif new_cat in cat_names:
                    st.error("이미 존재하는 구분명입니다.")
                else:
                    db.create_event_category(new_cat, new_color)
                    st.success(f"'{new_cat}' 구분이 추가되었습니다.")
                    st.rerun()
            category = new_cat or ""
        else:
            category = cat_choice

        title = st.text_input("행사명*", key="reg_title")
        event_date = st.date_input("날짜*", value=date.today(), key="reg_date")
        col_s, col_e = st.columns(2)
        with col_s:
            start_time_str = st.text_input("시작 시간* (HH:MM)", placeholder="09:00", key="reg_start")
        with col_e:
            end_time_str = st.text_input("종료 시간* (HH:MM)", placeholder="10:00", key="reg_end")
        venue = st.text_input("장소*", key="reg_venue")
        memo = st.text_area("메모 (선택)", height=80, key="reg_memo")
        requires_check = st.toggle("참석 여부 설정", key="reg_check")

        if st.button("등록", type="primary", key="reg_submit"):
            time_pattern = re.compile(r"^\d{2}:\d{2}$")
            if not title or not venue or not start_time_str or not end_time_str or not category:
                st.error("모든 필수 항목을 입력해주세요.")
            elif not time_pattern.match(start_time_str) or not time_pattern.match(end_time_str):
                st.error("시간 형식이 올바르지 않습니다. HH:MM 형식으로 입력해주세요.")
            elif start_time_str >= end_time_str:
                st.error("종료 시간은 시작 시간보다 늦어야 합니다.")
            else:
                db.create_event(
                    title=title, event_date=str(event_date),
                    start_time=start_time_str, end_time=end_time_str,
                    category=category, venue=venue,
                    memo=memo or None, requires_check=requires_check,
                )
                st.session_state["_event_registered"] = True
                st.rerun()

# ---------- 달력 클릭 dialog 처리 ----------
cal_dialog_id = st.session_state.get("_cal_dialog")
if cal_dialog_id:
    events = db.get_all_events()
    clicked_ev = next((e for e in events if e["id"] == cal_dialog_id), None)
    if clicked_ev:
        event_detail_dialog(clicked_ev)
    st.session_state["_cal_dialog"] = None
