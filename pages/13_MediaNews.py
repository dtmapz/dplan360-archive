import streamlit as st
from datetime import date
from st_click_detector import click_detector

from utils.auth import is_admin
from utils.db import upload_notice_image
from utils.ui import set_current_page
from utils.sheets import (
    get_media_news,
    create_media_news,
    update_media_news,
    delete_media_news,
    get_all_media,
    MEDIA_NEWS_TYPES,
)

set_current_page("media_news")

# 구분별 칩 색상 — 목록에서 종류를 한눈에 구분한다
TYPE_COLORS = {
    "미디어 뉴스":  ("#0F5E86", "rgba(15,94,134,0.13)"),
    "신규 상품":    ("#993556", "rgba(153,53,86,0.13)"),
    "신규 미디어":  ("#2B6A7F", "rgba(43,106,127,0.15)"),
}

POPUP_KEYS = (
    "_mn_popup_open", "_mn_popup_mode", "_mn_popup_id",
    "_mn_f_type", "_mn_f_media", "_mn_f_title", "_mn_f_subtitle",
    "_mn_f_body", "_mn_f_link", "_mn_f_important", "_mn_f_published",
    "_mn_f_image_url", "_mn_f_newsroom",
    "_mn_del_confirm",
)


# ----------------------------------------------------------------------
# 팝업 세션 관리
# ----------------------------------------------------------------------

def _reset_popup_state():
    for key in POPUP_KEYS:
        st.session_state.pop(key, None)


def _keep_popup():
    st.session_state["_mn_popup_open"] = True


def _open_view_popup(news_id: str):
    _reset_popup_state()
    st.session_state["_mn_popup_open"] = True
    st.session_state["_mn_popup_mode"] = "view"
    st.session_state["_mn_popup_id"] = news_id


def _fill_edit_fields(n: dict):
    st.session_state["_mn_f_type"] = n.get("news_type") or MEDIA_NEWS_TYPES[0]
    st.session_state["_mn_f_media"] = n.get("media") or ""
    st.session_state["_mn_f_title"] = n.get("title") or ""
    st.session_state["_mn_f_subtitle"] = n.get("subtitle") or ""
    st.session_state["_mn_f_body"] = n.get("body") or ""
    st.session_state["_mn_f_link"] = n.get("link") or ""
    st.session_state["_mn_f_important"] = bool(n.get("is_important"))
    st.session_state["_mn_f_published"] = n.get("published_date") or ""
    st.session_state["_mn_f_image_url"] = n.get("image_url") or ""
    st.session_state["_mn_f_newsroom"] = bool(n.get("newsroom", True))


def _open_edit_popup(n: dict | None = None):
    _reset_popup_state()
    st.session_state["_mn_popup_open"] = True
    st.session_state["_mn_popup_mode"] = "edit"
    if n:
        st.session_state["_mn_popup_id"] = n["id"]
        _fill_edit_fields(n)
    else:
        st.session_state["_mn_f_type"] = MEDIA_NEWS_TYPES[0]
        st.session_state["_mn_f_important"] = False
        st.session_state["_mn_f_image_url"] = ""
        st.session_state["_mn_f_newsroom"] = True   # 기본 ON


def _switch_to_edit_mode(n: dict):
    st.session_state["_mn_popup_mode"] = "edit"
    _fill_edit_fields(n)


# ----------------------------------------------------------------------
# 게시판 렌더 — 행마다 st.button 을 두면 위젯이 수백 개가 되므로
# click_detector 하나로 통합한다 (§4, 선례: 6_MediaGuide)
# ----------------------------------------------------------------------

def _type_chip(t: str) -> str:
    fg, bg = TYPE_COLORS.get(t, ("#6E6A63", "rgba(110,106,99,0.13)"))
    return (f"<span style='display:inline-block;font-size:10px;font-weight:700;"
            f"border-radius:5px;padding:2px 7px;white-space:nowrap;"
            f"color:{fg};background:{bg};'>{t}</span>")


def _media_cell(name: str) -> str:
    """매체명은 칩이 아니라 **일반 텍스트**(제목과 동일한 색·굵기).

    모든 행에 등장하는 값이라 칩으로 만들면 색 기둥이 생겨 정작 읽어야 할 제목이 묻힌다.
    강조는 예외적으로만 나오는 '중요' 칩에 몰아준다.
    """
    return (f"<span style='color:#111;font-weight:500;white-space:nowrap;'>{name}</span>")


def _render_board(items: list[dict], admin: bool = False) -> None:
    if not items:
        st.info("조건에 맞는 소식이 없습니다.")
        return

    head = (
        "<tr>"
        "<th style='width:104px;'>구분</th><th style='width:88px;'>매체명</th>"
        "<th>제목</th><th style='width:96px;'>작성일</th></tr>"
    )
    body = []
    for n in items:
        # 중요 = 아웃라인 레드 칩. 매체명을 일반 텍스트로 낮췄으므로 이 정도로도 충분히 눈에 띈다
        imp = ("<span style='display:inline-block;font-size:10px;font-weight:700;"
               "border-radius:5px;padding:1px 6px;color:#D64545;background:transparent;"
               "border:1px solid #D64545;margin-right:6px;'>중요</span>") if n["is_important"] else ""
        # 원문 링크가 있는 글은 목록에서 미리 알 수 있게 표시
        link_mark = ("<span style='font-size:10px;color:#999;margin-left:5px;'>🔗</span>"
                     if n["link"] else "")
        # 뉴스룸 제외 표시는 **관리자에게만** 렌더링한다.
        # 일반 사용자의 브라우저에는 태그도 흐림 처리도 전송되지 않아 모든 글이 동일하게 보인다.
        excluded = admin and not n["newsroom"]
        nr_tag = ("<span style='font-size:9.5px;font-weight:700;border-radius:4px;padding:2px 6px;"
                  "color:#888;background:#F5F5F5;border:1px solid #ddd;margin-left:7px;'>"
                  "뉴스룸 제외</span>") if excluded else ""
        row_style = " style='opacity:.45;'" if excluded else ""
        body.append(
            f"<tr{row_style}>"
            f"<td>{_type_chip(n['news_type'])}</td>"
            f"<td>{_media_cell(n['media']) if n['media'] else ''}</td>"
            f"<td><a href='#' id='news__{n['id']}' "
            f"style='text-decoration:none;color:#111;font-weight:500;cursor:pointer;'>"
            f"{imp}{n['title']}{link_mark}</a>{nr_tag}</td>"
            f"<td style='color:#999;font-variant-numeric:tabular-nums;white-space:nowrap;'>"
            f"{n['published_date'] or '-'}</td>"
            "</tr>"
        )

    html = (
        "<style>"
        ".mn-tbl{border-collapse:collapse;width:100%;font-size:13px;}"
        ".mn-tbl th{background:#F5F5F5;border-top:1px solid #ddd;border-bottom:1px solid #ddd;"
        "padding:9px 12px;text-align:left;font-size:11px;font-weight:700;"
        "letter-spacing:.04em;color:#666;}"
        ".mn-tbl td{border-bottom:1px solid #eee;padding:10px 12px;vertical-align:middle;}"
        ".mn-tbl tr:hover td{background:#FFFDF6;}"
        "</style>"
        "<div style='border:1px solid #ddd;border-radius:8px;overflow:hidden;'>"
        f"<table class='mn-tbl'>{head}{''.join(body)}</table></div>"
    )

    # click_detector 는 새 클릭이 없어도 **마지막 클릭값을 계속 반환**한다.
    # 예전엔 key 에 순번을 넣어 컴포넌트를 새로 만들어 막았는데, 새로 만드는 순간 iframe 높이가 0이 되어
    # 게시판을 스크롤한 뒤 글을 누르면 **화면 위치가 튀었다**(주간 뉴스룸에서 먼저 발견).
    # → key 는 고정하고 **앵커 id 앞에 클릭 순번을 붙여** 새 클릭만 처리한다. 같은 글 재클릭도 새 id 라 정상 동작.
    # href="#" 도 없앤다 — 누를 때마다 페이지 안 이동(fragment navigation)을 일으킨다.
    nonce = st.session_state.get("_mn_click_nonce", 0)
    html = html.replace("<a href='#' id='", f"<a id='{nonce}::")
    clicked = click_detector(html, key="mn_board_det")
    if clicked and "::" in clicked:
        click_nonce, target = clicked.split("::", 1)
        if click_nonce == str(nonce) and target.startswith("news__"):
            st.session_state["_mn_click_nonce"] = nonce + 1
            _open_view_popup(target.replace("news__", "", 1))
            st.rerun()


# ----------------------------------------------------------------------
# 팝업
# ----------------------------------------------------------------------

@st.dialog(" ")
def render_news_popup():
    # 첫 줄에서 플래그를 소비한다. X로 닫아도 Streamlit 이 알려주지 않으므로,
    # 이 줄이 없으면 플래그가 남아 다른 페이지에 갔다 돌아왔을 때 팝업이 다시 열린다 (§12).
    # 내부 rerun 으로 팝업을 유지해야 할 때만 _keep_popup() 으로 되살린다.
    st.session_state.pop("_mn_popup_open", None)
    mode = st.session_state.get("_mn_popup_mode", "view")
    news_id = st.session_state.get("_mn_popup_id")
    target = next((n for n in get_media_news() if n["id"] == news_id), None)
    if mode == "edit":
        _render_edit_mode(target)
    else:
        _render_view_mode(target)


def _render_view_mode(n: dict | None):
    if not n:
        st.warning("소식을 찾을 수 없습니다.")
        return

    fg, _ = TYPE_COLORS.get(n["news_type"], ("#F2A93B", ""))
    imp = ("<span style='background:#D64545;color:#fff;font-size:10px;font-weight:700;"
           "border-radius:4px;padding:2px 7px;margin-right:6px;'>중요</span>"
           if n["is_important"] else "")
    meta = " · ".join(x for x in [n["media"], n["news_type"], n["published_date"]] if x)
    subtitle = (f"<div style='font-size:12px;color:#C8C8C8;margin-top:5px;line-height:1.5;'>"
                f"{n['subtitle']}</div>") if n["subtitle"] else ""

    st.markdown(
        "<div style='background:#0B0B0B;color:#fff;border-radius:8px;padding:18px 20px;margin-bottom:16px;'>"
        f"<div style='font-size:11px;color:#F2A93B;font-weight:700;margin-bottom:5px;'>{meta}</div>"
        f"<div style='font-size:18px;font-weight:700;line-height:1.4;'>{imp}{n['title']}</div>"
        f"{subtitle}</div>",
        unsafe_allow_html=True,
    )

    # 상세 이미지 — 헤더 바로 아래. 원본 비율을 유지하고 폭에 맞춰 축소한다(잘라내지 않음).
    # 공지 캡처는 크롭되면 내용이 사라지므로 use_container_width 로 폭만 맞춘다.
    if n.get("image_url"):
        st.image(n["image_url"], use_container_width=True)
        st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)

    # 본문·링크는 둘 다 선택 입력이고, 있는 것만 보여준다 (등록 시 최소 하나는 필수)
    if n["body"]:
        st.markdown(
            f"<div style='background:#F5F5F5;border:1px solid #e5e5e5;border-radius:8px;"
            f"padding:13px 15px;font-size:13.5px;line-height:1.75;white-space:pre-wrap;"
            f"margin-bottom:16px;'>{n['body']}</div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            "<div style='border:1px dashed #ccc;border-radius:8px;padding:12px 15px;"
            "font-size:12.5px;color:#888;background:#FAFAFA;margin-bottom:16px;'>"
            "[원문 보기] 버튼을 눌러 상세 내용을 확인하세요.</div>",
            unsafe_allow_html=True,
        )

    if n["link"]:
        st.link_button("🔗 원문 보기", n["link"], type="primary", use_container_width=True)

    if is_admin():
        st.divider()
        if st.button("✎ 수정하기", key=f"mn_edit_entry_{n['id']}", use_container_width=True):
            _switch_to_edit_mode(n)
            _keep_popup()
            st.rerun()


def _render_edit_mode(existing: dict | None):
    is_edit = existing is not None
    st.markdown("#### 소식 수정" if is_edit else "#### 소식 등록")

    media_options = [m["name"] for m in get_all_media() if m.get("name")]
    cur_media = st.session_state.get("_mn_f_media") or ""
    if cur_media and cur_media not in media_options:
        media_options.append(cur_media)

    c1, c2 = st.columns(2)
    with c1:
        cur_type = st.session_state.get("_mn_f_type") or MEDIA_NEWS_TYPES[0]
        st.selectbox("구분 *", MEDIA_NEWS_TYPES,
                     index=MEDIA_NEWS_TYPES.index(cur_type) if cur_type in MEDIA_NEWS_TYPES else 0,
                     key="_mn_f_type")
    with c2:
        st.selectbox("매체명 *", media_options,
                     index=media_options.index(cur_media) if cur_media in media_options else 0,
                     key="_mn_f_media",
                     help="등록된 매체 목록에서 선택합니다")

    st.text_input("제목 *", key="_mn_f_title", placeholder="예: Google Ads 데모그래픽 타게팅 정책 변경 안내")
    st.text_input("부제목", key="_mn_f_subtitle", placeholder="목록·상세에 함께 보이는 한 줄 설명")
    st.text_area("본문", key="_mn_f_body", height=130,
                 placeholder="플랫폼에서 바로 읽을 내용")
    # 상세 이미지 — 기존 인프라 재사용(media-hub-images 버킷 · UUID 파일명, §9)
    cur_img = st.session_state.get("_mn_f_image_url") or ""
    if cur_img:
        ic1, ic2 = st.columns([3, 1])
        with ic1:
            st.image(cur_img, use_container_width=True)
        with ic2:
            st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
            if st.button("이미지 삭제", key="mn_img_del", use_container_width=True):
                st.session_state["_mn_f_image_url"] = ""
                _keep_popup()
                st.rerun()
    else:
        up = st.file_uploader("상세 이미지", type=["png", "jpg", "jpeg", "gif", "webp"],
                              key="_mn_w_image_uploader",
                              help="공지 캡처 등 상세 이미지를 등록하면 상세 화면 상단에 표시됩니다")
        if up is not None:
            try:
                st.session_state["_mn_f_image_url"] = upload_notice_image(up.getvalue(), up.name)
                _keep_popup()
                st.rerun()
            except Exception as e:
                st.error(f"이미지 업로드에 실패했습니다: {e}")

    st.text_input("원문 링크", key="_mn_f_link", placeholder="https://…")
    st.caption("본문과 원문 링크 중 **최소 하나**는 입력해야 합니다.")

    c3, c4 = st.columns(2)
    with c3:
        cur_pub = st.session_state.get("_mn_f_published")
        st.date_input("작성일 *", key="_mn_f_published_date",
                      value=date.fromisoformat(cur_pub) if cur_pub else date.today(),
                      help="주간 뉴스룸의 주차 판정 기준입니다")
    with c4:
        st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)
        st.checkbox("중요 표시", key="_mn_f_important",
                    help="목록에서 제목 앞에 붉은 '중요' 칩이 표시됩니다")
        st.checkbox("주간 뉴스룸 반영", key="_mn_f_newsroom",
                    help="기본 체크됨. 해제하면 주간 뉴스룸에 노출되지 않습니다 "
                         "(일반 사용자에게는 이 구분이 보이지 않습니다)")

    st.divider()
    save_col, cancel_col, del_col = st.columns([2, 1, 1])

    if save_col.button("저장", key="mn_save_btn", type="primary", use_container_width=True):
        title = (st.session_state.get("_mn_f_title") or "").strip()
        body = (st.session_state.get("_mn_f_body") or "").strip()
        link = (st.session_state.get("_mn_f_link") or "").strip()
        if not title:
            st.error("제목은 필수입니다.")
            return
        if not (st.session_state.get("_mn_f_media") or "").strip():
            st.error("매체명은 필수입니다.")
            return
        if not body and not link:
            st.error("본문과 원문 링크 중 최소 하나는 입력해야 합니다.")
            return
        _save_news(is_edit, existing)
        return

    if cancel_col.button("취소", key="mn_cancel_btn", use_container_width=True):
        _reset_popup_state()
        st.rerun()

    if is_edit:
        if not st.session_state.get("_mn_del_confirm"):
            if del_col.button("삭제", key="mn_del_btn", use_container_width=True):
                st.session_state["_mn_del_confirm"] = True
                _keep_popup()
                st.rerun()
        else:
            st.error("정말 삭제하시겠습니까?")
            dc1, dc2 = st.columns(2)
            if dc1.button("삭제 확정", key="mn_del_confirm_btn", type="primary", use_container_width=True):
                delete_media_news(existing["row"])
                _reset_popup_state()
                st.rerun()
            if dc2.button("취소", key="mn_del_cancel_btn", use_container_width=True):
                st.session_state.pop("_mn_del_confirm", None)
                _keep_popup()
                st.rerun()


def _save_news(is_edit: bool, existing: dict | None):
    published = st.session_state.get("_mn_f_published_date")
    payload = {
        "news_type": st.session_state.get("_mn_f_type") or MEDIA_NEWS_TYPES[0],
        "media": (st.session_state.get("_mn_f_media") or "").strip(),
        "title": (st.session_state.get("_mn_f_title") or "").strip(),
        "subtitle": (st.session_state.get("_mn_f_subtitle") or "").strip(),
        "body": (st.session_state.get("_mn_f_body") or "").strip(),
        "link": (st.session_state.get("_mn_f_link") or "").strip(),
        "is_important": bool(st.session_state.get("_mn_f_important")),
        "image_url": (st.session_state.get("_mn_f_image_url") or "").strip(),
        "newsroom": bool(st.session_state.get("_mn_f_newsroom", True)),
        "published_date": published.isoformat() if isinstance(published, date) else "",
    }
    if is_edit:
        payload["id"] = existing["id"]
        payload["created_at"] = existing["created_at"]
        update_media_news(existing["row"], payload)
    else:
        create_media_news(payload)

    _reset_popup_state()
    st.rerun()


# ----------------------------------------------------------------------
# 페이지 본문
# ----------------------------------------------------------------------

admin = is_admin()

head_col, btn_col = st.columns([5, 1])
with head_col:
    # 페이지 상단 타이틀·서브카피는 노출하지 않는다 (사이드바 메뉴명이 이미 제목 역할)
    st.markdown("<div style='height:4px;'></div>", unsafe_allow_html=True)
if admin:
    if btn_col.button("＋ 소식 등록", key="mn_add_btn", use_container_width=True):
        _open_edit_popup(None)
        st.rerun()

all_news = get_media_news()
media_options = sorted({n["media"] for n in all_news if n["media"]})

with st.container(border=True):
    fc1, fc2, fc3 = st.columns([1.3, 2, 0.55])
    sel_media = fc1.multiselect(
        "매체명", media_options, key="mn_media_filter",
        placeholder="전체 (선택 시 필터링)",
    )
    keyword = fc2.text_input(
        "키워드 검색", key="mn_keyword",
        placeholder="제목 · 부제목 · 본문에서 검색",
    )
    fc3.markdown("<div style='height:26px;'></div>", unsafe_allow_html=True)
    if fc3.button("초기화", key="mn_reset_filter", use_container_width=True):
        for k in ("mn_media_filter", "mn_keyword"):
            st.session_state.pop(k, None)
        st.rerun()

filtered = all_news
if sel_media:
    filtered = [n for n in filtered if n["media"] in sel_media]
if keyword:
    kw = keyword.strip().lower()
    filtered = [
        n for n in filtered
        if kw in n["title"].lower() or kw in n["subtitle"].lower() or kw in n["body"].lower()
    ]

if sel_media or keyword:
    st.caption(f"조회 결과 {len(filtered)}건 / 전체 {len(all_news)}건")

_render_board(filtered, admin=admin)

if st.session_state.get("_mn_popup_open"):
    render_news_popup()
