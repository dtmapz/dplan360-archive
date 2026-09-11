"""주간 뉴스룸 — 주차 계산 + 섹션별 데이터 취합.

원본 카테고리를 **조회 시점에 2주치만 필터**한다. 별도 저장 탭·스냅샷·승인 절차가 없으므로
원본을 수정하면 지난주 뉴스룸 내용도 소급해서 바뀐다(확정된 동작).

섹션 ↔ 출처
  01 미디어 뉴스        ← media_news  (news_type=미디어 뉴스, newsroom=ON, 작성일)
  02 매체 프로모션      ← home_promotion (등록일)
  03 신규 상품 & 미디어 ← media_news  (news_type=신규 상품/신규 미디어, newsroom=ON, 작성일)
  04 미디어 자료        ← media_archive (발행일, 뉴스룸 연동 체크된 아젠다만)
  05 주요 일정          ← events       (탭 주차의 **다음주** 월~금)
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from utils.sheets import (
    get_all_events,
    get_home_promotions,
    get_media_archives,
    get_media_news,
)
from utils.ui import kst_today

NEWS_TYPE_MEDIA = "미디어 뉴스"
NEWS_TYPE_PRODUCT = "신규 상품"
NEWS_TYPE_NEW_MEDIA = "신규 미디어"
WEEKDAY_KO = ["월", "화", "수", "목", "금", "토", "일"]


# ----------------------------------------------------------------------
# 주차
# ----------------------------------------------------------------------

def _today() -> date:
    t = kst_today()
    return t.date() if isinstance(t, datetime) else t


def week_bounds(offset: int = 0, today: date | None = None) -> tuple[date, date]:
    """offset=0 이번주, -1 지난주. 월요일~일요일."""
    t = today or _today()
    monday = t - timedelta(days=t.weekday()) + timedelta(weeks=offset)
    return monday, monday + timedelta(days=6)


def week_label(monday: date) -> str:
    """'N월 M주차' — 월요일이 아니라 **발행일(금요일) 기준**으로 센다 (§11-J).
    8/31(월)~9/4(금) 주간은 9월 1주차다(월요일 기준이면 8월 5주차가 되어 틀림).
    """
    friday = monday + timedelta(days=4)
    return f"{friday.month}월 {(friday.day - 1) // 7 + 1}주차"


def fmt_range(monday: date, sunday: date) -> str:
    return (f"{monday:%Y.%m.%d}({WEEKDAY_KO[monday.weekday()]}) ~ "
            f"{sunday:%m.%d}({WEEKDAY_KO[sunday.weekday()]})")


def _as_date(v) -> date | None:
    if isinstance(v, date):
        return v
    s = str(v or "").strip()[:10]
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _in(v, start: date, end: date) -> bool:
    d = _as_date(v)
    return d is not None and start <= d <= end


# ----------------------------------------------------------------------
# 섹션별 취합
# ----------------------------------------------------------------------

def media_news_section(start: date, end: date) -> list[dict]:
    """01 — 미디어 뉴스. 뉴스룸 반영(ON) + 작성일이 주차 안."""
    return [
        n for n in get_media_news()
        if n["news_type"] == NEWS_TYPE_MEDIA and n["newsroom"] and _in(n["published_date"], start, end)
    ]


def new_items_section(start: date, end: date) -> dict[str, list[dict]]:
    """03 — 신규 상품 / 신규 미디어를 좌우 컬럼용으로 나눠 반환."""
    rows = [n for n in get_media_news() if n["newsroom"] and _in(n["published_date"], start, end)]
    return {
        NEWS_TYPE_PRODUCT: [n for n in rows if n["news_type"] == NEWS_TYPE_PRODUCT],
        NEWS_TYPE_NEW_MEDIA: [n for n in rows if n["news_type"] == NEWS_TYPE_NEW_MEDIA],
    }


def promotions_section(start: date, end: date) -> list[dict]:
    """02 — 등록일이 주차 안인 프로모션. 시작일이 아니라 **등록일** 기준이어야
    '다음 달 시작 프로모션을 이번 주에 등록'한 경우가 이번 주에 잡힌다."""
    return [p for p in get_home_promotions() if _in(p.get("created_date"), start, end)]


def archive_section(start: date, end: date) -> list[dict]:
    """04 — 발행일이 주차 안인 자료 중 **뉴스룸 연동 체크된 아젠다가 1개 이상**인 것.
    아젠다는 체크된 것만 남겨 반환한다."""
    out = []
    for a in get_media_archives():
        basis = a.get("published_date") or a.get("created_at")
        if not _in(basis, start, end):
            continue
        linked = [it for it in (a.get("agenda") or []) if it.get("newsroom")]
        if linked:
            out.append({**a, "newsroom_agenda": linked})
    return out


def schedule_section(tab_monday: date) -> list[tuple[date, list[dict]]]:
    """05 — 탭 주차의 **다음주** 월~금. 요일별 행사 리스트(시간순). 주말은 표시하지 않는다."""
    next_mon = tab_monday + timedelta(weeks=1)
    days = [next_mon + timedelta(days=i) for i in range(5)]
    by_day: dict[date, list[dict]] = {d: [] for d in days}
    for ev in get_all_events():
        d = _as_date(ev.get("event_date"))
        if d in by_day:
            by_day[d].append(ev)
    return [(d, sorted(by_day[d], key=lambda e: e.get("start_time") or "")) for d in days]
