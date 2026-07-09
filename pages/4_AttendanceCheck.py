import streamlit as st
from datetime import date
from utils import db
from utils.auth import get_current_user
from utils.ui import set_current_page

set_current_page("attendance")

user = get_current_user()
user_email = user.get("email", "") if user else ""
events = db.get_attendance_summary()

if not events:
    st.info("참석 여부 설정된 행사가 없습니다.")
else:
    for ev in events:
        attendance = ev.get("attendance") or []
        attended = [a for a in attendance if a.get("attended")]
        total = len(attended)

        d = date.fromisoformat(ev["event_date"])
        weekdays = ["월", "화", "수", "목", "금", "토", "일"]
        label = f"{d.month}/{d.day}({weekdays[d.weekday()]}) {ev['title']} · 참석 {total}명"

        with st.expander(label, expanded=False):
            if not attended:
                st.caption("참석 체크한 인원이 없습니다.")
            else:
                # 참석자 이메일 기준으로 organization 테이블과 매칭
                sb = db.get_client()
                emails = [a["member_email"] for a in attended]
                org_res = sb.table("organization").select("*").in_("email", emails).execute()
                org_map = {o["email"]: o for o in org_res.data}

                rows = []
                for a in attended:
                    em = a["member_email"]
                    org = org_map.get(em, {})
                    rows.append({
                        "소속팀": org.get("team", "-"),
                        "이름": org.get("name", em),
                        "직급": org.get("position", "-"),
                        "이메일": em,
                    })

                import pandas as pd
                df = pd.DataFrame(rows)
                st.dataframe(df, hide_index=True, use_container_width=True)
