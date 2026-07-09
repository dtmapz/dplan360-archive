import streamlit as st
from datetime import datetime, date
from utils import db
from utils.auth import get_current_user, is_admin
from utils.ui import set_current_page, render_pending_dialog

set_current_page("calendar")

user = get_current_user()
user_email = user.get("email", "") if user else ""
admin = is_admin()

# 구분별 컬러 매핑
CATEGORY_COLORS = {
    "매체설명회": "#1D9E75",
    "온라인":    "#378ADD",
    "오프라인":  "#BA7517",
}

def get_category_color_map() -> dict:
    cats = db.get_event_categories()
    return {c["name"]: c["color"] for c in cats}

def category_color(cat: str, color_map: dict) -> str:
    return color_map.get(cat, "#888780")


# ---------- 이벤트 상세/수정 dialog ----------
@st.dialog("행사 상세")
def event_detail_dialog(event: dict):
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
        # 일시
        s = event.get("start_time", "")[:5] if event.get("start_time") else ""
        e = event.get("end_time", "")[:5] if event.get("end_time") else ""
        st.write(f"**일시**: {event['event_date']} {s} ~ {e}")
        st.write(f"**구분**: {event.get('category', '-')}")
        st.write(f"**장소**: {event.get('venue', '-')}")
        if event.get("memo"):
            st.write(f"**메모**: {event['memo']}")

        # 관리자: requires_check 토글
        if admin:
            new_req = st.toggle(
                "참석 여부 설정",
                value=bool(event.get("requires_check")),
                key=f"req_toggle_{event['id']}",
            )
            if new_req != bool(event.get("requires_check")):
                db.update_event(event["id"], requires_check=new_req)
                st.rerun()

        # 일반 사용자: requires_check ON일 때 참석 여부 토글
        if not admin and event.get("requires_check"):
            attended_ids = st.session_state.get("my_attendance", [])
            current = event["id"] in attended_ids
            new_val = st.toggle("참석 여부", value=current, key=f"att_{event['id']}")
            if new_val != current:
                db.toggle_attendance(event["id"], user_email, new_val)
                # 세션 캐시 갱신
                if new_val:
                    st.session_state["my_attendance"] = attended_ids + [event["id"]]
                else:
                    st.session_state["my_attendance"] = [x for x in attended_ids if x != event["id"]]
                st.rerun()

        # 관리자 삭제 버튼
        if admin:
            st.divider()
            if st.button("행사 삭제", type="secondary", key=f"del_{event['id']}"):
                db.delete_event(event["id"])
                st.session_state["_active_dialog"] = None
                st.rerun()

    else:
        # 수정 모드
        title = st.text_input("행사명", value=event["title"])
        event_date = st.date_input("날짜", value=date.fromisoformat(event["event_date"]))
        col_s, col_e = st.columns(2)
        with col_s:
            from datetime import time as dtime
            def parse_time(t):
                if not t: return dtime(9, 0)
                parts = t[:5].split(":")
                return dtime(int(parts[0]), int(parts[1]))
            start_time = st.time_input("시작 시간", value=parse_time(event.get("start_time")))
        with col_e:
            end_time = st.time_input("종료 시간", value=parse_time(event.get("end_time")))
        category = st.selectbox("구분", ["매체설명회", "온라인", "오프라인"],
                                index=["매체설명회", "온라인", "오프라인"].index(event.get("category", "매체설명회"))
                                if event.get("category") in ["매체설명회", "온라인", "오프라인"] else 0)
        venue = st.text_input("장소", value=event.get("venue", ""))
        memo = st.text_area("메모", value=event.get("memo", "") or "", height=80)

        if st.button("저장", type="primary"):
            if not title or not venue:
                st.error("행사명과 장소는 필수입니다.")
            elif start_time_str >= end_time_str:
                st.error("종료 시간은 시작 시간보다 늦어야 합니다.")
            else:
                db.update_event(event["id"],
                    title=title, event_date=str(event_date),
                    start_time=str(start_time), end_time=str(end_time),
                    category=category, venue=venue, memo=memo or None)
                st.session_state[f"event_edit_{event['id']}"] = False
                st.session_state["_active_dialog"] = None
                st.rerun()


# ---------- 메인 ----------
st.markdown("## 📅 EVENT CALENDAR")

if admin:
    tab_cal, tab_list, tab_reg = st.tabs(["월별 달력", "리스트", "+ 행사 등록"])
else:
    tab_cal, tab_list = st.tabs(["월별 달력", "리스트"])
    tab_reg = None

# 참석 여부 세션 캐시 초기화 (최초 1회)
if "my_attendance" not in st.session_state:
    st.session_state["my_attendance"] = db.get_my_attendance(user_email)

with tab_cal:
    try:
        from streamlit_calendar import calendar as st_calendar

        events = db.get_all_events()
        color_map = get_category_color_map()
        cal_events = []
        for ev in events:
            color = category_color(ev.get("category", ""), color_map)
            start = ev["event_date"]
            if ev.get("start_time"):
                start += f"T{ev['start_time'][:5]}"
            end = ev["event_date"]
            if ev.get("end_time"):
                end += f"T{ev['end_time'][:5]}"
            cal_events.append({
                "id": ev["id"],
                "title": ev["title"],
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
            if clicked_ev:
                st.session_state["_active_dialog"] = ("event_detail", clicked_ev, "calendar")
                st.rerun()

    except ImportError:
        st.error("streamlit-calendar 패키지가 필요합니다. requirements.txt에 추가 후 재배포해주세요.")

with tab_list:
    events = db.get_all_events()
    if not events:
        st.caption("등록된 행사가 없습니다.")
    else:
        current_date = None
        attended_ids = st.session_state.get("my_attendance", [])
        for ev in events:
            if ev["event_date"] != current_date:
                current_date = ev["event_date"]
                d = date.fromisoformat(current_date)
                weekdays = ["월", "화", "수", "목", "금", "토", "일"]
                st.markdown(
                    f"<div style='font-size:13px; font-weight:500; color:var(--text-muted); "
                    f"margin:16px 0 4px;'>{d.year}년 {d.month}월 {d.day}일 ({weekdays[d.weekday()]})</div>",
                    unsafe_allow_html=True,
                )

            color_map = get_category_color_map()
            color = category_color(ev.get("category", ""), color_map)
            s = ev.get("start_time", "")[:5] if ev.get("start_time") else ""
            e = ev.get("end_time", "")[:5] if ev.get("end_time") else ""

            col_ev, col_att = st.columns([6, 1])
            with col_ev:
                st.markdown(
                    f"<div style='border-left:3px solid {color}; padding:8px 12px; "
                    f"background:var(--surface-1); border-radius:0 8px 8px 0; margin-bottom:4px; cursor:pointer;'>"
                    f"<span style='font-size:13px; font-weight:500;'>{ev['title']}</span>"
                    f"<span style='font-size:12px; color:var(--text-muted); margin-left:8px;'>{s}~{e} · {ev.get('venue','')}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
                if st.button("상세보기", key=f"list_detail_{ev['id']}", use_container_width=False):
                    st.session_state["_active_dialog"] = ("event_detail", ev, "calendar")
                    st.rerun()

            # 일반 사용자 + requires_check ON인 경우 토글
            with col_att:
                if not admin and ev.get("requires_check"):
                    current = ev["id"] in attended_ids
                    new_val = st.toggle("참석", value=current, key=f"list_att_{ev['id']}")
                    if new_val != current:
                        db.toggle_attendance(ev["id"], user_email, new_val)
                        if new_val:
                            st.session_state["my_attendance"] = attended_ids + [ev["id"]]
                        else:
                            st.session_state["my_attendance"] = [x for x in attended_ids if x != ev["id"]]
                        st.rerun()

# ---------- 이벤트 등록 dialog (관리자 전용) ----------
if tab_reg is not None:
    with tab_reg:
        title = st.text_input("행사명*", key="reg_title")
        event_date = st.date_input("날짜*", value=date.today(), key="reg_date")
        col_s, col_e = st.columns(2)
        with col_s:
            start_time_str = st.text_input("시작 시간* (HH:MM)", placeholder="09:00", key="reg_start")
        with col_e:
            end_time_str = st.text_input("종료 시간* (HH:MM)", placeholder="10:00", key="reg_end")
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
        venue = st.text_input("장소*", key="reg_venue")
        memo = st.text_area("메모 (선택)", height=80, key="reg_memo")
        requires_check = st.toggle("참석 여부 설정", key="reg_check")

        if st.button("등록", type="primary", key="reg_submit"):
            if not title or not venue or not start_time_str or not end_time_str:
                st.error("행사명 / 날짜 / 시작-종료 시간 / 장소는 필수입니다.")
            elif start_time_str >= end_time_str:
                st.error("종료 시간은 시작 시간보다 늦어야 합니다.")
            else:
                db.create_event(
                    title=title, event_date=str(event_date),
                    start_time=str(start_time), end_time=str(end_time),
                    category=category, venue=venue,
                    memo=memo or None, requires_check=requires_check,
                )
                st.success("등록되었습니다.")
                st.rerun()

# ---------- dialog 디스패처 ----------
dialog = st.session_state.get("_active_dialog")
if dialog:
    kind, payload, origin = dialog
    if origin != "calendar":
        st.session_state["_active_dialog"] = None
    else:
        st.session_state["_active_dialog"] = None
        if kind == "event_detail":
            event_detail_dialog(payload)
