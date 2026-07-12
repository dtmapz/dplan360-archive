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

    att_current_future = [ev for ev in att_all_events if ev["event_date"][:7] >= current_month]
    att_past = [ev for ev in att_all_events if ev["event_date"][:7] < current_month]

    # 이번달 이후
    if att_current_future:
        html = build_attendance_table(att_current_future, att_members, att_map,
                                      show_count=True, all_events_for_count=att_all_events)
        st.markdown(html, unsafe_allow_html=True)
    else:
        st.caption("이번달 이후 등록된 행사가 없습니다.")

    # 과거 기록
    if att_past:
        past_months = sorted(set(ev["event_date"][:7] for ev in att_past))
        y_start, m_start = past_months[0].split("-")
        y_end, m_end = past_months[-1].split("-")
        label = f"{y_start}년 {int(m_start)}월 ~ {y_end}년 {int(m_end)}월 기록"
        with st.expander(label, expanded=False):
            html = build_attendance_table(att_past, att_members, att_map, show_count=False)
            st.markdown(html, unsafe_allow_html=True)

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
