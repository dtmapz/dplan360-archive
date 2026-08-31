"""관리자 페이지 — 조직도 관리 + 화이트리스트 동기화.

기능:
- 상단 우측: `동기화 실행` 버튼 (조직도 → Supabase 화이트리스트)
- 하단: 로그인 가능 사용자 표 (본부/팀/이름/이메일/활성/마지막 접속)
- 관리자는 여기서 사용자 추가/편집/활성 토글/삭제 → 시트 + Supabase 반영
"""
import streamlit as st
from datetime import datetime, timezone, timedelta

from utils.auth import get_current_user, is_admin
from utils.ui import set_current_page
from utils.sheets import (
    get_all_org_members_with_row,
    add_org_member,
    update_org_member,
    set_org_active,
    delete_org_member,
)
from utils.db import list_auth_last_sign_in, delete_auth_user
from utils.org_sync import sync_allowlist

set_current_page("admin")

user = get_current_user()
if not is_admin():
    st.warning("관리자 전용 페이지입니다.")
    st.stop()


# ------------------------------------------------------------
# 헤더 + 동기화 버튼
# ------------------------------------------------------------
head_c, sync_c = st.columns([5, 1.2])
head_c.markdown(
    "<div style='font-size:20px;font-weight:700;margin-bottom:4px;'>⚙️ 관리자</div>"
    "<div style='font-size:12px;color:#888;'>조직도 · 로그인 화이트리스트 관리</div>",
    unsafe_allow_html=True,
)

with sync_c:
    if st.button("🔄 동기화 실행", use_container_width=True,
                 help="조직도 시트 → Supabase 화이트리스트 즉시 반영\n(매일 04시 자동 실행됨)"):
        with st.spinner("동기화 중..."):
            try:
                r = sync_allowlist()
                st.success(f"활성 {r['total']} · +{len(r['added'])} · −{len(r['removed'])} · 유지 {r['kept']}")
            except Exception as e:
                st.error(f"동기화 실패: {e}")

st.divider()


# ------------------------------------------------------------
# 사용자 목록
# ------------------------------------------------------------
KST = timezone(timedelta(hours=9))


def _fmt_last(iso_str: str) -> str:
    if not iso_str:
        return "-"
    try:
        s = iso_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s).astimezone(KST)
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return iso_str[:16]


@st.cache_data(ttl=60)
def _last_sign_in_map() -> dict[str, str]:
    try:
        return list_auth_last_sign_in()
    except Exception as e:
        st.warning(f"Supabase 접속 이력 조회 실패 ({e}) — '마지막 접속' 컬럼은 비워집니다.")
        return {}


members = get_all_org_members_with_row()
last_map = _last_sign_in_map()

# 필터
f1, f2, f3 = st.columns([1.5, 2, 1.2])
q = f1.text_input("검색 (이름/이메일/팀)", key="_adm_q", placeholder="예: mj.park, 그로스")
divisions = sorted({m["division"] for m in members if m["division"]})
sel_div = f2.multiselect("본부", divisions, key="_adm_div")
sel_active = f3.selectbox("활성 여부", ["전체", "활성만", "비활성만"], key="_adm_active")


def _match(m):
    if q:
        needle = q.strip().lower()
        hay = f"{m['name']} {m['email']} {m['team']} {m['division']}".lower()
        if needle not in hay:
            return False
    if sel_div and m["division"] not in sel_div:
        return False
    if sel_active == "활성만" and not m["is_active"]:
        return False
    if sel_active == "비활성만" and m["is_active"]:
        return False
    return True


filtered = [m for m in members if _match(m)]

# 요약
total_active = sum(1 for m in members if m["is_active"])
st.caption(f"전체 {len(members)}명 · 활성 {total_active}명 · 표시 {len(filtered)}명")

# ------------------------------------------------------------
# 테이블 + 액션
# ------------------------------------------------------------

# 헤더
h_cols = st.columns([1.2, 1.3, 1.2, 2.4, 0.7, 1.4, 1.2])
for c, label in zip(h_cols, ["본부", "팀", "이름", "이메일", "활성", "마지막 접속", "관리"]):
    c.markdown(f"<div style='font-size:12px;color:#666;font-weight:600;'>{label}</div>",
               unsafe_allow_html=True)
st.markdown("<hr style='margin:4px 0;border:none;border-top:1px solid #eee;'/>",
            unsafe_allow_html=True)

for m in filtered:
    row = st.columns([1.2, 1.3, 1.2, 2.4, 0.7, 1.4, 1.2])
    style = "" if m["is_active"] else "color:#aaa;"
    role_badge = ""
    if m["role"] == "admin":
        role_badge = " <span style='background:#F2A93B;color:#fff;font-size:9px;padding:1px 5px;border-radius:3px;margin-left:4px;'>ADMIN</span>"
    row[0].markdown(f"<div style='font-size:12px;{style}'>{m['division'] or '-'}</div>", unsafe_allow_html=True)
    row[1].markdown(f"<div style='font-size:12px;{style}'>{m['team'] or '-'}</div>", unsafe_allow_html=True)
    row[2].markdown(f"<div style='font-size:12px;{style}'>{m['name'] or '-'}{role_badge}</div>", unsafe_allow_html=True)
    row[3].markdown(f"<div style='font-size:12px;{style}'>{m['email'] or '-'}</div>", unsafe_allow_html=True)
    row[4].markdown(
        f"<div style='font-size:12px;'>{'🟢' if m['is_active'] else '⚪'}</div>",
        unsafe_allow_html=True,
    )
    last_str = _fmt_last(last_map.get(m["email"], ""))
    row[5].markdown(f"<div style='font-size:12px;color:#666;'>{last_str}</div>",
                    unsafe_allow_html=True)
    if row[6].button("편집", key=f"_adm_edit_{m['row']}", use_container_width=True):
        # 이전 편집 위젯 값 초기화 (다른 유저 잔존 방지)
        for k in list(st.session_state.keys()):
            if k.startswith("_adm_e_"):
                del st.session_state[k]
        st.session_state.pop("_adm_del_confirm", None)
        st.session_state["_adm_edit_row"] = m["row"]
        st.rerun()

st.divider()


# ------------------------------------------------------------
# 편집 / 신규 등록 / 삭제
# ------------------------------------------------------------

def _sync_after_change():
    try:
        sync_allowlist()
    except Exception as e:
        st.warning(f"화이트리스트 동기화 실패: {e} (수동으로 상단 동기화 버튼 눌러주세요)")


@st.dialog("사용자 편집", width="large")
def _edit_dialog(target_row: int):
    m = next((x for x in members if x["row"] == target_row), None)
    if not m:
        st.warning("사용자를 찾을 수 없습니다.")
        return

    st.markdown(f"**{m['name']}** · `{m['email']}`")

    # 위젯 key에 row 번호를 포함시켜 다른 유저를 열 때 완전 새 위젯으로 인식
    ks = f"_adm_e_{m['row']}"
    c1, c2 = st.columns(2)
    div = c1.text_input("본부", value=m["division"], key=f"{ks}_div")
    team = c2.text_input("팀", value=m["team"], key=f"{ks}_team")
    c1, c2 = st.columns(2)
    name = c1.text_input("이름", value=m["name"], key=f"{ks}_name")
    pos = c2.text_input("직급", value=m.get("position", ""), key=f"{ks}_pos")
    c1, c2 = st.columns(2)
    role = c1.selectbox("권한", ["user", "admin"],
                        index=(1 if m["role"] == "admin" else 0), key=f"{ks}_role")
    active = c2.selectbox("활성", ["활성 (Y)", "비활성 (N)"],
                          index=(0 if m["is_active"] else 1), key=f"{ks}_active")

    st.divider()
    save_c, del_c, cancel_c = st.columns([2, 1, 1])
    if save_c.button("💾 저장", type="primary", use_container_width=True):
        update_org_member(m["row"], {
            "division": div, "team": team, "name": name, "position": pos,
            "email": m["email"], "role": role,
            "is_active": "Y" if active.startswith("활성") else "N",
        })
        _sync_after_change()
        st.session_state.pop("_adm_edit_row", None)
        st.rerun()

    if not st.session_state.get("_adm_del_confirm"):
        if del_c.button("🗑 삭제", use_container_width=True,
                        help="시트에서 완전 삭제 + Supabase 로그인 계정도 삭제"):
            st.session_state["_adm_del_confirm"] = True
            st.rerun()
    else:
        st.error("⚠️ 시트 행 + Supabase 로그인 계정 모두 삭제됩니다. 되돌릴 수 없습니다.")
        dc1, dc2 = st.columns(2)
        if dc1.button("완전 삭제 확정", type="primary", key="_adm_del_confirm_btn",
                     use_container_width=True):
            try:
                delete_auth_user(m["email"])
            except Exception as e:
                st.warning(f"Supabase 계정 삭제 실패: {e}")
            delete_org_member(m["row"])
            _sync_after_change()
            st.session_state.pop("_adm_del_confirm", None)
            st.session_state.pop("_adm_edit_row", None)
            st.rerun()
        if dc2.button("취소", key="_adm_del_cancel", use_container_width=True):
            st.session_state.pop("_adm_del_confirm", None)
            st.rerun()

    if cancel_c.button("닫기", use_container_width=True, key="_adm_e_close"):
        st.session_state.pop("_adm_edit_row", None)
        st.rerun()


@st.dialog("신규 사용자 등록", width="large")
def _add_dialog():
    c1, c2 = st.columns(2)
    div = c1.text_input("본부 *", key="_adm_n_div")
    team = c2.text_input("팀 *", key="_adm_n_team")
    c1, c2 = st.columns(2)
    name = c1.text_input("이름 *", key="_adm_n_name")
    pos = c2.text_input("직급", key="_adm_n_pos")
    c1, c2 = st.columns(2)
    email = c1.text_input("이메일 * (@d-plan360.com)", key="_adm_n_email")
    role = c2.selectbox("권한", ["user", "admin"], key="_adm_n_role")

    st.divider()
    ok_c, cancel_c = st.columns([2, 1])
    if ok_c.button("➕ 등록", type="primary", use_container_width=True):
        if not (div and team and name and email):
            st.error("본부/팀/이름/이메일은 필수입니다.")
            return
        try:
            add_org_member({
                "division": div, "team": team, "name": name, "position": pos,
                "email": email, "role": role, "is_active": "Y",
            })
            _sync_after_change()
            st.session_state.pop("_adm_add_open", None)
            st.rerun()
        except Exception as e:
            st.error(str(e))

    if cancel_c.button("취소", use_container_width=True, key="_adm_n_close"):
        st.session_state.pop("_adm_add_open", None)
        st.rerun()


# 하단 신규 등록 트리거
if st.button("+ 신규 사용자 등록", type="primary"):
    # 이전 신규 등록 잔존 값 초기화
    for k in list(st.session_state.keys()):
        if k.startswith("_adm_n_"):
            del st.session_state[k]
    st.session_state["_adm_add_open"] = True
    st.rerun()

if st.session_state.get("_adm_edit_row"):
    _edit_dialog(st.session_state["_adm_edit_row"])

if st.session_state.get("_adm_add_open"):
    _add_dialog()
