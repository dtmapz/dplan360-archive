import html
from datetime import date

import streamlit as st
from st_click_detector import click_detector

from utils import newsroom as nr
from utils.auth import get_current_user, is_admin
from utils.sheets import (
    get_event_categories,
    get_home_promotions,
    get_media_archives,
    get_media_news,
    get_all_events,
    get_my_attendance,
    toggle_attendance,
    update_event,
)
from utils.ui import set_current_page, promo_card_html

set_current_page("newsroom")

WEEK_OPTIONS = ["지난주", "이번주"]
DAY_ABBR = ["MON", "TUE", "WED", "THU", "FRI"]

# 구분 칩 색 — 미디어 소식 아카이브(13_MediaNews)와 같은 값
TYPE_COLORS = {
    "미디어 뉴스": "#0F5E86",
    "신규 상품": "#993556",
    "신규 미디어": "#2B6A7F",
}
# "~은/~는" 조사 — 빈 슬롯 안내 문구용
TYPE_TOPIC = {"신규 상품": "신규 상품은", "신규 미디어": "신규 미디어는"}

# click_detector(iframe) 기본 동작 보정 — 설치된 번들(main.5b9f06e5) 확인 결과:
#  ① 콘텐츠 앞뒤에 1x1 투명 <img> 스페이서를 끼워 넣는다. 인라인이라 줄 높이(약 20px)만큼
#     목록 위아래에 빈 줄이 생긴다 → 콘텐츠 루트의 **직계** img 만 숨긴다(카드 안 이미지는 더 깊어서 영향 없음)
#  ② 감싸는 div 에 테마 글꼴·글자색을 인라인으로 박는다 → !important 로 덮어야 앱과 같은 글꼴·검은 글자가 된다
#  음수 여백으로 간격을 줄이면 제목이 요소 밖으로 밀려 잘린다(실제 발생) — 원인 요소를 없애는 방식만 쓸 것
_IFRAME_BASE = (
    "<link rel='stylesheet' href='https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;600;700&display=swap'>"
    "<style>"
    "body{margin:0;padding:0 0 2px;}"
    "body > div > img{display:none !important;}"
    "body > div{font-family:'IBM Plex Sans KR',-apple-system,'Malgun Gothic',sans-serif !important;"
    "color:#111 !important;word-break:keep-all;}"
    "a{text-decoration:none !important;color:inherit !important;cursor:pointer;}"
    "</style>"
)

# 목록 내 '중요' — 미디어 소식 목록과 같은 아웃라인 레드 칩
_IMP_OUTLINE = (
    "<span style='display:inline-block;font-size:10px;font-weight:700;border-radius:5px;"
    "padding:1px 6px;color:#D64545;border:1px solid #D64545;margin-right:6px;"
    "vertical-align:1px;'>중요</span>"
)


def _e(v) -> str:
    return html.escape(str(v or ""))


def _short_date(v) -> str:
    if isinstance(v, date):
        return f"{v:%m.%d}"
    s = str(v or "")
    return s[5:10].replace("-", ".") if len(s) >= 10 else "-"


# ----------------------------------------------------------------------
# 팝업 상태 — 뉴스룸 전용 읽기 전용 상세. 수정은 각 원본 페이지에서 한다.
# ----------------------------------------------------------------------

def _open_popup(kind: str, item_id: str) -> None:
    st.session_state["_nr_popup_open"] = True
    st.session_state["_nr_popup_kind"] = kind
    st.session_state["_nr_popup_id"] = item_id


def _detector(body: str, name: str, offset: int) -> None:
    """click_detector 공통 처리.

    - 앵커 onclick 이 **앵커 자신의 id** 를 보내므로 행·카드 전체를 <a> 로 감싸면 내부 어디를 눌러도 된다.
    - 컴포넌트는 마지막 클릭값을 계속 돌려준다. 예전엔 key 에 순번을 넣어 **컴포넌트를 새로 만들어** 막았는데,
      새로 만드는 순간 iframe 높이가 0이 되어 아래 섹션이 당겨지고 **스크롤 위치가 튀었다**(01 클릭 시 02가 맨 위로).
      → key 는 고정하고, **앵커 id 앞에 클릭 순번을 붙여** 새 클릭만 처리한다. 같은 항목 재클릭도 새 id 라 정상 동작.
    - href 를 없앤다. href="#" 는 누를 때마다 페이지 안 이동(fragment navigation)을 일으킨다.
    """
    nonce = st.session_state.get("_nr_click_nonce", 0)
    body = body.replace("<a href='#' id='", f"<a id='{nonce}::")
    clicked = click_detector(_IFRAME_BASE + body, key=f"nr_det_{name}_{offset}")
    if clicked and "::" in clicked:
        click_nonce, target = clicked.split("::", 1)
        if click_nonce == str(nonce) and "__" in target:
            kind, item_id = target.split("__", 1)
            st.session_state["_nr_click_nonce"] = nonce + 1
            _open_popup(kind, item_id)
            st.rerun()


# ----------------------------------------------------------------------
# 공통 블록
# ----------------------------------------------------------------------

def _section_head(no: str, title: str) -> None:
    st.markdown(
        "<div style='display:flex;align-items:center;gap:9px;margin:16px 0 6px;flex-wrap:wrap;'>"
        "<span style='font-size:12px;font-weight:700;color:#4C4A9E;background:rgba(76,74,158,.12);"
        f"border-radius:4px;padding:2px 8px;font-variant-numeric:tabular-nums;'>{no}</span>"
        f"<span style='font-size:16px;font-weight:700;color:#111;'>{title}</span>"
        "</div>",
        unsafe_allow_html=True,
    )


def _empty_row(msg: str) -> None:
    """섹션 0건 — 섹션은 유지하고 한 줄 안내만 둔다(E-2 B안). 번호가 주마다 바뀌지 않게 하기 위함."""
    st.markdown(
        "<div style='border:1px dashed #D6D3CC;border-radius:8px;padding:12px 15px;"
        "font-size:13px;color:#888;background:repeating-linear-gradient(135deg,transparent 0 7px,"
        f"rgba(128,120,105,.055) 7px 8px),#F7F6F3;'>{msg}</div>",
        unsafe_allow_html=True,
    )


_LIST_CSS = (
    "<style>"
    ".nl{border:1px solid #E3E1DC;border-radius:9px;overflow:hidden;background:#fff;}"
    ".nl a{display:flex;gap:14px;align-items:flex-start;padding:11px 15px;border-bottom:1px solid #EFEDE8;}"
    ".nl a:last-child{border-bottom:none;}"
    ".nl a:hover{background:#FFFDF6;}"
    ".nl .m{flex:0 0 82px;font-size:13px;font-weight:500;color:#555;padding-top:1px;}"
    ".nl .t{flex:1;min-width:0;font-size:14px;font-weight:500;line-height:1.5;}"
    ".nl .s{display:block;font-size:12.5px;color:#888;font-weight:400;margin-top:2px;}"
    ".nl .d{flex:none;font-size:12.5px;color:#999;font-variant-numeric:tabular-nums;padding-top:1px;}"
    "</style>"
)


# ----------------------------------------------------------------------
# 섹션 렌더
# ----------------------------------------------------------------------

def _render_news(items: list[dict], wk: str, offset: int) -> None:
    _section_head("01", "미디어 뉴스")
    if not items:
        _empty_row(f"{wk} 등록된 미디어 뉴스가 없습니다")
        return
    rows = []
    for n in items:
        sub = f"<span class='s'>{_e(n['subtitle'])}</span>" if n["subtitle"] else ""
        imp = _IMP_OUTLINE if n["is_important"] else ""
        rows.append(
            f"<a href='#' id='news__{_e(n['id'])}'>"
            f"<span class='m'>{_e(n['media'])}</span>"
            f"<span class='t'>{imp}{_e(n['title'])}{sub}</span>"
            f"<span class='d'>{_short_date(n['published_date'])}</span></a>"
        )
    _detector(_LIST_CSS + f"<div class='nl'>{''.join(rows)}</div>", "news", offset)


_PROMO_CSS = (
    "<style>"
    ".pg{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;}"
    ".pg a{display:block;border-radius:8px;}"
    ".pg a:hover > div{box-shadow:0 0 0 1.5px #F2A93B;}"
    "</style>"
)


def _render_promos(items: list[dict], wk: str, offset: int) -> None:
    _section_head("02", "매체 프로모션")
    if not items:
        _empty_row(f"{wk} 등록된 매체 프로모션이 없습니다")
        return
    # 미디어 프로모션 페이지와 같은 카드를 쓰되, 버튼 없이 **카드 자체를 클릭**한다(01 목록과 같은 방식).
    # 카드 이미지가 늦게 로드돼도 click_detector 가 ResizeObserver 로 높이를 따라가므로 잘리지 않는다.
    cards = "".join(
        f"<a href='#' id='promo__{_e(p['id'])}'>{promo_card_html(p, standalone=True)}</a>"
        for p in items
    )
    _detector(_PROMO_CSS + f"<div class='pg'>{cards}</div>", "promo", offset)


_NEW_CSS = (
    "<style>"
    ".two{display:grid;grid-template-columns:1fr 1fr;gap:14px;}"
    # 그리드 자식은 기본 stretch → 두 컬럼 높이가 같아진다.
    # 안쪽은 반드시 flex 컬럼이어야 빈 슬롯의 flex:1 이 실제로 남은 높이를 채운다(§17-26 시안 버그와 동일 원리).
    ".col{display:flex;flex-direction:column;min-width:0;}"
    ".ch{font-size:12px;font-weight:700;color:#888;padding-bottom:7px;border-bottom:1px solid #E3E1DC;"
    "margin-bottom:10px;letter-spacing:.02em;}"
    ".list{display:flex;flex-direction:column;gap:10px;flex:1;min-height:0;}"
    ".ic{display:block;border:1px solid #E3E1DC;border-radius:9px;padding:13px 15px;background:#fff;}"
    ".ic:hover{border-color:#F2A93B;}"
    ".top{display:flex;align-items:center;gap:8px;margin-bottom:7px;}"
    ".chip{display:inline-block;font-size:11px;font-weight:700;color:#fff;border-radius:5px;padding:2px 8px;}"
    ".mm{font-size:12.5px;color:#666;font-weight:500;}"
    ".tt{font-size:14.5px;font-weight:700;line-height:1.45;margin-bottom:3px;}"
    ".sub{font-size:13px;color:#777;line-height:1.55;margin-bottom:9px;}"
    ".cta{font-size:12.5px;font-weight:600;color:#B9770F;}"
    ".empty{flex:1 1 auto;min-height:100px;border:1px dashed #D6D3CC;border-radius:9px;display:flex;"
    "flex-direction:column;align-items:center;justify-content:center;text-align:center;gap:3px;"
    "background:repeating-linear-gradient(135deg,transparent 0 7px,rgba(128,120,105,.055) 7px 8px),#F7F6F3;}"
    ".e1{font-size:13px;font-weight:600;color:#888;}"
    ".e2{font-size:11.5px;color:#999;}"
    "</style>"
)


def _new_card(n: dict) -> str:
    color = TYPE_COLORS.get(n["news_type"], "#666")
    imp = _IMP_OUTLINE if n["is_important"] else ""
    sub = f"<div class='sub'>{_e(n['subtitle'])}</div>" if n["subtitle"] else ""
    return (
        f"<a href='#' id='news__{_e(n['id'])}' class='ic'>"
        f"<div class='top'><span class='chip' style='background:{color};'>{_e(n['news_type'])}</span>"
        f"<span class='mm'>{_e(n['media'])}</span></div>"
        f"<div class='tt'>{imp}{_e(n['title'])}</div>{sub}"
        "<div class='cta'>세부 내용 확인하기 →</div></a>"
    )


def _new_column(label: str, items: list[dict], other_count: int, wk: str) -> str:
    cards = "".join(_new_card(n) for n in items)
    # 모자란 쪽 하단에 안내 슬롯 **1개**가 남은 높이를 채운다(건수 차이만큼 반복하지 않음)
    if not items:
        cards += (f"<div class='empty'><span class='e1'>{wk} {label} 소식이 없어요</span>"
                  "<span class='e2'>새 소식이 등록되면 이 자리에 표시됩니다</span></div>")
    elif len(items) < other_count:
        cards += (f"<div class='empty'><span class='e1'>{wk} {TYPE_TOPIC.get(label, label)} 여기까지예요</span>"
                  "<span class='e2'>추가 소식이 등록되면 이 자리에 표시됩니다</span></div>")
    return (f"<div class='col'><div class='ch'>{label} · {len(items)}건</div>"
            f"<div class='list'>{cards}</div></div>")


def _render_new_items(groups: dict[str, list[dict]], wk: str, offset: int) -> None:
    _section_head("03", "신규 상품 & 미디어")
    products = groups[nr.NEWS_TYPE_PRODUCT]
    medias = groups[nr.NEWS_TYPE_NEW_MEDIA]
    if not products and not medias:
        _empty_row(f"{wk} 등록된 신규 상품·미디어 소식이 없습니다")
        return
    body = (
        _NEW_CSS + "<div class='two'>"
        + _new_column(nr.NEWS_TYPE_PRODUCT, products, len(medias), wk)
        + _new_column(nr.NEWS_TYPE_NEW_MEDIA, medias, len(products), wk)
        + "</div>"
    )
    _detector(body, "new", offset)


def _render_archive(items: list[dict], wk: str, offset: int) -> None:
    _section_head("04", "미디어 자료")
    if not items:
        _empty_row(f"{wk} 뉴스룸에 연동된 미디어 자료가 없습니다")
        return
    rows = []
    for a in items:
        agendas = " · ".join(_e(it["text"]) for it in a["newsroom_agenda"])
        rows.append(
            f"<a href='#' id='arch__{_e(a['id'])}'>"
            f"<span class='m'>{_e(a.get('publisher'))}</span>"
            f"<span class='t'>{_e(a['title'])}<span class='s'>{agendas}</span></span>"
            f"<span class='d'>{_short_date(a.get('published_date') or a.get('created_at'))}</span></a>"
        )
    _detector(_LIST_CSS + f"<div class='nl'>{''.join(rows)}</div>", "arch", offset)


_CAL_CSS = (
    "<style>"
    ".cal{display:grid;grid-template-columns:repeat(5,1fr);gap:9px;}"
    ".cc{border:1px solid #E3E1DC;border-radius:9px;overflow:hidden;background:#fff;display:flex;flex-direction:column;}"
    ".chd{background:#F5F5F5;border-bottom:1px solid #E3E1DC;padding:8px 6px;text-align:center;}"
    ".dw{font-size:10.5px;font-weight:700;letter-spacing:.08em;color:#888;}"
    ".dn{font-size:15px;font-weight:700;font-variant-numeric:tabular-nums;line-height:1.3;}"
    ".cb{padding:8px;display:flex;flex-direction:column;gap:7px;flex:1;min-height:88px;}"
    ".ev{display:block;border:1px solid #E3E1DC;border-left:3px solid #F2A93B;border-radius:7px;padding:7px 9px;}"
    ".ev:hover{background:#FFFDF6;}"
    ".tm{font-size:11.5px;font-weight:700;color:#B9770F;font-variant-numeric:tabular-nums;}"
    ".nm{font-size:13px;font-weight:700;line-height:1.4;margin:2px 0 5px;}"
    ".go{font-size:11.5px;color:#888;font-weight:600;}"
    ".none{flex:1;display:flex;align-items:center;justify-content:center;font-size:12px;color:#bbb;}"
    "</style>"
)


def _render_schedule(days: list[tuple[date, list[dict]]], next_word: str, offset: int) -> None:
    _section_head("05", "주요 일정")
    if not any(evs for _, evs in days):
        _empty_row(f"{next_word} 등록된 일정이 없습니다")
        return
    cols = []
    for i, (d, evs) in enumerate(days):
        if evs:
            inner = "".join(
                f"<a href='#' id='ev__{_e(ev['id'])}' class='ev'>"
                f"<div class='tm'>{_e(ev.get('start_time') or '시간 미정')}</div>"
                f"<div class='nm'>{_e(ev['title'])}</div>"
                "<div class='go'>세부 내용 확인 →</div></a>"
                for ev in evs
            )
            body = f"<div class='cb'>{inner}</div>"
        else:
            body = "<div class='cb'><div class='none'>일정 없음</div></div>"
        cols.append(
            f"<div class='cc'><div class='chd'><div class='dw'>{DAY_ABBR[i]}</div>"
            f"<div class='dn'>{d:%m.%d}</div></div>{body}</div>"
        )
    _detector(_CAL_CSS + f"<div class='cal'>{''.join(cols)}</div>", "cal", offset)


# ----------------------------------------------------------------------
# 읽기 전용 상세 팝업 (A안) — 뉴스룸을 벗어나지 않고 확인. 수정 기능은 두지 않는다.
# ----------------------------------------------------------------------

def _dark_header(meta: str, title_html: str, subtitle: str = "") -> None:
    sub = (f"<div style='font-size:12px;color:#C8C8C8;margin-top:5px;line-height:1.5;'>{subtitle}</div>"
           if subtitle else "")
    st.markdown(
        "<div style='background:#0B0B0B;color:#fff;border-radius:8px;padding:18px 20px;margin-bottom:16px;'>"
        f"<div style='font-size:11px;color:#F2A93B;font-weight:700;margin-bottom:5px;'>{meta}</div>"
        f"<div style='font-size:18px;font-weight:700;line-height:1.4;'>{title_html}</div>{sub}</div>",
        unsafe_allow_html=True,
    )


def _view_news(n: dict | None) -> None:
    if not n:
        st.warning("소식을 찾을 수 없습니다.")
        return
    imp = ("<span style='background:#D64545;color:#fff;font-size:10px;font-weight:700;"
           "border-radius:4px;padding:2px 7px;margin-right:6px;'>중요</span>" if n["is_important"] else "")
    meta = " · ".join(x for x in [n["media"], n["news_type"], n["published_date"]] if x)
    _dark_header(meta, imp + n["title"], n["subtitle"])
    if n.get("image_url"):
        st.image(n["image_url"], use_container_width=True)
        st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)
    if n["body"]:
        st.markdown(
            "<div style='background:#F5F5F5;border:1px solid #e5e5e5;border-radius:8px;padding:13px 15px;"
            f"font-size:13.5px;line-height:1.75;white-space:pre-wrap;margin-bottom:16px;'>{n['body']}</div>",
            unsafe_allow_html=True,
        )
    elif n["link"]:
        st.markdown(
            "<div style='border:1px dashed #ccc;border-radius:8px;padding:12px 15px;font-size:12.5px;"
            "color:#888;background:#FAFAFA;margin-bottom:16px;'>"
            "[원문 보기] 버튼을 눌러 상세 내용을 확인하세요.</div>",
            unsafe_allow_html=True,
        )
    if n["link"]:
        st.link_button("🔗 원문 보기", n["link"], type="primary", use_container_width=True)


def _view_promo(p: dict | None) -> None:
    if not p:
        st.warning("프로모션 정보를 찾을 수 없습니다.")
        return
    # 매체명·카테고리 칩은 카드에 이미 보이므로 팝업에서는 생략한다 (미디어 프로모션 팝업과 동일)
    st.markdown(f"### {p['name']}")
    if p["subtitle"]:
        st.caption(p["subtitle"])
    st.markdown(f"**운영 기간**  \n{p['start_date'] or '-'} ~ {p['end_date'] or '상시'}")
    if p["memo"]:
        st.markdown(
            "<div style='background:#FFF8E1;border-left:3px solid #F2A93B;border-radius:6px;"
            f"padding:12px 14px;font-size:12px;margin-top:10px;'>{p['memo']}</div>",
            unsafe_allow_html=True,
        )
    # 상세 이미지는 맨 아래 — 미디어 프로모션 페이지 팝업과 같은 순서
    if p["image_url"]:
        st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)
        st.image(p["image_url"], use_container_width=True)


def _view_archive(a: dict | None) -> None:
    if not a:
        st.warning("자료를 찾을 수 없습니다.")
        return
    st.markdown(
        "<div style='background:#0B0B0B;color:#fff;border-radius:8px;padding:18px 20px;margin-bottom:16px;'>"
        f"<div style='font-size:11px;color:#F2A93B;font-weight:700;margin-bottom:4px;'>"
        f"{a['year']}년 {a['month']} · {a.get('publisher') or ''} 발간</div>"
        f"<div style='font-size:18px;font-weight:700;'>{a['title']}</div>"
        f"<div style='font-size:12px;color:#C8C8C8;margin-top:4px;'>발행일 {a['published_date'] or '-'}</div>"
        "</div>",
        unsafe_allow_html=True,
    )
    agenda = a.get("agenda") or []
    if agenda:
        rows = []
        for i, it in enumerate(agenda):
            nr_mark = ("<span style='flex:0 0 auto;font-size:9.5px;font-weight:700;color:#0F5E86;"
                       "background:rgba(15,94,134,0.12);padding:1px 6px;border-radius:4px;'>뉴스룸</span>"
                       if it.get("newsroom") else "")
            rows.append(
                "<div style='display:flex;gap:10px;align-items:center;font-size:13px;color:#111;"
                "padding:6px 8px;border-radius:4px;margin-bottom:2px;'>"
                "<span style='flex:0 0 auto;font-size:11px;font-weight:700;color:#F2A93B;"
                "background:rgba(242,169,59,0.18);width:20px;height:20px;border-radius:5px;"
                f"display:flex;align-items:center;justify-content:center;'>{i + 1}</span>"
                f"<span style='flex:1;'>{it.get('text') or ''}</span>{nr_mark}</div>"
            )
        st.markdown(
            "<div style='background:#FFF8E1;border-left:3px solid #F2A93B;border-radius:6px;"
            f"padding:10px 12px;margin-bottom:18px;'>{''.join(rows)}</div>",
            unsafe_allow_html=True,
        )
    if a["drive_link"]:
        st.link_button("📄 드라이브에서 열기", a["drive_link"], type="primary", use_container_width=True)
    if a.get("memo"):
        st.markdown(
            "<div style='background:#F6F8FC;border:1px solid #E5EAF5;border-radius:8px;padding:10px 12px;"
            f"font-size:13px;white-space:pre-wrap;line-height:1.5;margin-top:14px;'>{a['memo']}</div>",
            unsafe_allow_html=True,
        )


def _view_event(ev: dict | None) -> None:
    if not ev:
        st.warning("행사 정보를 찾을 수 없습니다.")
        return
    color = {c["name"]: c["color"] for c in get_event_categories()}.get(ev.get("category"), "#888780")
    st.markdown(
        "<div style='display:flex;align-items:center;gap:10px;margin-bottom:10px;'>"
        f"<span style='background:{color};color:#fff;font-size:12px;padding:3px 10px;border-radius:4px;"
        f"white-space:nowrap;'>{ev.get('category') or '-'}</span>"
        f"<span style='font-size:16px;font-weight:700;'>{ev['title']}</span></div>",
        unsafe_allow_html=True,
    )
    s, e = (ev.get("start_time") or "")[:5], (ev.get("end_time") or "")[:5]
    st.write(f"**일시**: {ev['event_date']} {s}{' ~ ' + e if e else ''}")
    st.write(f"**장소**: {ev.get('venue') or '-'}")
    if ev.get("memo"):
        st.write(f"**메모**: {ev['memo']}")
    # 캘린더 팝업과 같은 참석 토글 — 관리자: 참석 여부 설정 / 일반 사용자: 참석 체크 행사에서만 참석 여부.
    # 팝업 안 조작은 팝업만 다시 그려지므로 st.rerun() 을 부르지 않는다(전체 재실행 시 팝업이 닫힘).
    # update_event / toggle_attendance 가 캐시를 비우므로 다음 조작 때 최신 값으로 다시 읽힌다.
    if is_admin():
        st.divider()
        req = bool(ev.get("requires_check"))
        new_req = st.toggle("참석 여부 설정", value=req, key=f"nr_req_{ev['id']}")
        if new_req != req:
            update_event(ev["id"], requires_check=new_req)
    elif ev.get("requires_check"):
        st.divider()
        email = (get_current_user() or {}).get("email", "")
        current = ev["id"] in get_my_attendance(email)
        new_val = st.toggle("참석 여부", value=current, key=f"nr_att_{ev['id']}")
        if new_val != current:
            toggle_attendance(ev["id"], email, new_val)


@st.dialog(" ")
def _render_popup() -> None:
    # 첫 줄에서 플래그 소비 — X로 닫아도 알림이 없어 남으면 재진입 시 다시 열린다(§12, §17-26 ②)
    st.session_state.pop("_nr_popup_open", None)
    kind = st.session_state.get("_nr_popup_kind")
    item_id = st.session_state.get("_nr_popup_id")
    if kind == "news":
        _view_news(next((n for n in get_media_news() if n["id"] == item_id), None))
    elif kind == "promo":
        _view_promo(next((p for p in get_home_promotions() if str(p["id"]) == item_id), None))
    elif kind == "arch":
        _view_archive(next((a for a in get_media_archives() if a["id"] == item_id), None))
    elif kind == "ev":
        _view_event(next((ev for ev in get_all_events() if ev["id"] == item_id), None))


# ----------------------------------------------------------------------
# 페이지 본문
# ----------------------------------------------------------------------

week = st.segmented_control(
    "주차", WEEK_OPTIONS, default="이번주", key="nr_week", label_visibility="collapsed",
)
offset = -1 if week == "지난주" else 0
wk = "지난주" if offset == -1 else "이번 주"
next_word = "이번 주" if offset == -1 else "다음 주"
monday, sunday = nr.week_bounds(offset)

st.markdown(
    "<div style='background:#F5F5F5;border:1px solid #E3E1DC;border-left:4px solid #4C4A9E;"
    "border-radius:10px;padding:15px 20px;margin:10px 0 2px;'>"
    f"<div style='font-size:20px;font-weight:700;color:#111;'>{nr.week_label(monday)}</div>"
    f"<div style='font-size:13px;color:#888;font-variant-numeric:tabular-nums;'>"
    f"{nr.fmt_range(monday, sunday)}</div></div>",
    unsafe_allow_html=True,
)

news = nr.media_news_section(monday, sunday)
promos = nr.promotions_section(monday, sunday)
new_groups = nr.new_items_section(monday, sunday)
archives = nr.archive_section(monday, sunday)
schedule = nr.schedule_section(monday)

has_any = any([
    news, promos, archives,
    new_groups[nr.NEWS_TYPE_PRODUCT], new_groups[nr.NEWS_TYPE_NEW_MEDIA],
    any(evs for _, evs in schedule),
])

if not has_any:
    # 전체 0건 — 빈 섹션 5개를 나열하지 않고 한 덩어리로 안내(E-3)
    hint = ("각 카테고리에 소식이 등록되면 이곳에 자동으로 모입니다 · 지난주 탭에서 지난 소식을 확인할 수 있습니다"
            if offset == 0 else "각 카테고리에 등록된 소식이 없었습니다")
    st.markdown(
        "<div style='border:1px dashed #D6D3CC;border-radius:10px;padding:34px 20px;text-align:center;"
        "margin-top:18px;background:repeating-linear-gradient(135deg,transparent 0 7px,"
        "rgba(128,120,105,.05) 7px 8px),#F7F6F3;'>"
        "<div style='font-size:26px;opacity:.55;margin-bottom:6px;'>🗞️</div>"
        f"<div style='font-size:15px;font-weight:700;color:#111;margin-bottom:4px;'>"
        f"{'아직 이번 주 소식이 등록되지 않았습니다' if offset == 0 else '지난주에 등록된 소식이 없습니다'}</div>"
        f"<div style='font-size:12.5px;color:#888;'>{hint}</div></div>",
        unsafe_allow_html=True,
    )
else:
    _render_news(news, wk, offset)
    _render_promos(promos, wk, offset)
    _render_new_items(new_groups, wk, offset)
    _render_archive(archives, wk, offset)
    _render_schedule(schedule, next_word, offset)

if st.session_state.get("_nr_popup_open"):
    _render_popup()
