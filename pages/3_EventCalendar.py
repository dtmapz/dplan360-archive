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


def get_category_color_map() -> dict:
    cats = db.get_event_categories()
    return {c["name"]: c["color"] for c in cats}


def category_color(cat: str, color_map: dict) -> str:
    return color_map.get(cat, "#888780")


# ---------- 이벤트 상세 dialog ----------
@st.dialog("행사 상세")
def event_detail_dialog(event: dict):
    color_map = get_category_color_map()
    edit_mode = st.session_state.get(f"event_edit_{event['id']}", False)

    col_t, col_btn = st.columns([5, 1])
    with col_t:
        st.markdown(f"### {event['title']}")
    if admin:
        with col_btn:
            if st.button("수정", key=f"ev_edit_{event['id']}"):
                st.session_state[f"event_edit_{event['id']}"] = not edit_mode
                st.rerun()

    if not edit_mode:
        s = event.get("start_time", "")[:5] if event.get("start_time") else ""
        e = event.get("end_time", "")[:5] if event.get("end_time") else ""
        cat = event.get("category", "-")
        color = category_color(cat, color_map)

        col_cat, col_title2 = st.columns([1, 4])
        with col_cat:
            st.markdown(
                f"<span style='background:{color}; color:#fff; font-size:12px; "
                f"padding:3px 10px; border-radius:4px;'>{cat}</span>",
                unsafe_allow_html=True,
            )
        with col_title2:
            st.markdown(f"**{event['title']}**")
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
st.markdown("## 📅 EVENT CALENDAR")

# 참석 여부 세션 캐시 초기화
if "my_attendance" not in st.session_state:
    st.session_state["my_attendance"] = db.get_my_attendance(user_email)

# 등록 완료 알럿
if st.session_state.pop("_event_registered", False):
    st.success("행사가 등록되었습니다.")

if admin:
    tab_cal, tab_list, tab_reg = st.tabs(["월별 달력", "리스트", "+ 행사 등록"])
else:
    tab_cal, tab_list = st.tabs(["월별 달력", "리스트"])
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
            s = ev.get("start_time", "")[:5] if ev.get("start_time") else ""
            cat = ev.get("category", "")
            start = ev["event_date"] + (f"T{s}" if s else "")
            end_t = ev.get("end_time", "")[:5] if ev.get("end_time") else ""
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
            clicked_ev = next((e for e in events if e["id"] == clicked_id), None)
            if clicked_ev and st.session_state.get("_cal_dialog") != clicked_id:
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
        current_date = None
        for ev in events:
            if ev["event_date"] != current_date:
                current_date = ev["event_date"]
                d = date.fromisoformat(current_date)
                weekdays = ["월", "화", "수", "목", "금", "토", "일"]
                st.markdown(
                    f"<div style='font-size:13px; font-weight:500; color:var(--text-muted); "
                    f"margin:16px 0 6px;'>{d.year}년 {d.month}월 {d.day}일 ({weekdays[d.weekday()]})</div>",
                    unsafe_allow_html=True,
                )

            color = category_color(ev.get("category", ""), color_map)
            cat = ev.get("category", "")
            s = ev.get("start_time", "")[:5] if ev.get("start_time") else ""
            e = ev.get("end_time", "")[:5] if ev.get("end_time") else ""
            venue = ev.get("venue", "")

            col_info, col_toggle = st.columns([5, 1])
            with col_info:
                st.markdown(
                    f"<div style='display:flex; align-items:center; gap:10px; "
                    f"padding:8px 12px; background:var(--surface-1); "
                    f"border-radius:8px; margin-bottom:4px;'>"
                    f"<span style='background:{color}; color:#fff; font-size:11px; "
                    f"padding:2px 8px; border-radius:4px; white-space:nowrap;'>{cat}</span>"
                    f"<span style='font-size:13px; font-weight:500;'>{ev['title']}</span>"
                    f"<span style='font-size:12px; color:var(--text-muted);'>{s}~{e} · {venue}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
            with col_toggle:
                if admin and ev.get("requires_check") is not None:
                    new_req = st.toggle("참석설정", value=bool(ev.get("requires_check")),
                                        key=f"list_req_{ev['id']}")
                    if new_req != bool(ev.get("requires_check")):
                        db.update_event(ev["id"], requires_check=new_req)
                        st.rerun()
                elif not admin and ev.get("requires_check"):
                    current = ev["id"] in attended_ids
                    new_val = st.toggle("참석", value=current, key=f"list_att_{ev['id']}")
                    if new_val != current:
                        db.toggle_attendance(ev["id"], user_email, new_val)
                        st.session_state["my_attendance"] = (
                            attended_ids + [ev["id"]] if new_val
                            else [x for x in attended_ids if x != ev["id"]]
                        )
                        st.rerun()

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
