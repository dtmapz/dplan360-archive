"""SP봇 검색·스코어링 — 스펙 §3 초기값.

score = 제목일치×3 + 카테고리일치×2 + 본문/키워드일치×1 + 최신성 가산점
- 최종수정일 90일 이내 → +2
- 90일~1년 → +1
- 1년 초과 → 0
- 상태='만료' 문서는 제외

주의: 가중치·후보 개수 5는 시작점. 실제 질문 10~20건으로 튜닝 필요.
"""
from datetime import date, datetime, timedelta
from utils.spbot_sheets import get_all_docs, get_all_qna_docs


TOP_K = 5
MIN_SCORE = 3  # 최소 매칭 임계값 (제목 1건 매칭 수준)


def _parse_date(s: str) -> date | None:
    s = (s or "").strip()
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def _freshness_bonus(last_modified: date | None, today: date) -> int:
    if not last_modified:
        return 0
    diff = (today - last_modified).days
    if diff <= 90:
        return 2
    if diff <= 365:
        return 1
    return 0


def _tokenize(text: str) -> list[str]:
    """단순 토큰화 — 공백·콤마 분리, 소문자화, 1자 이하 제거."""
    if not text:
        return []
    text = text.lower()
    for sep in [",", "·", "/", "\n", "\t"]:
        text = text.replace(sep, " ")
    tokens = [t.strip() for t in text.split()]
    return [t for t in tokens if len(t) > 1]


def _count_hits(query_tokens: list[str], text: str) -> int:
    if not text or not query_tokens:
        return 0
    text_lower = text.lower()
    return sum(1 for t in query_tokens if t in text_lower)


def score_docs(question: str, docs: list[dict]) -> list[dict]:
    """docs에 점수 부여. 만료 제외, 점수 오름차순 정렬 결과 반환."""
    today = date.today()
    q_tokens = _tokenize(question)
    scored = []
    for d in docs:
        if str(d.get("상태", "")).strip() == "만료":
            continue
        title = str(d.get("제목", ""))
        summary = str(d.get("요약", ""))
        category = str(d.get("카테고리", ""))
        keywords = str(d.get("키워드", ""))
        body = str(d.get("본문", ""))

        title_hits = _count_hits(q_tokens, title)
        category_hits = _count_hits(q_tokens, category)
        body_hits = _count_hits(q_tokens, body + " " + keywords + " " + summary)

        base = title_hits * 3 + category_hits * 2 + body_hits * 1
        if base == 0:
            continue  # 하나도 안 걸린 문서는 제외

        modified = _parse_date(str(d.get("최종수정일", "")))
        bonus = _freshness_bonus(modified, today)
        score = base + bonus

        scored.append({**d, "_score": score})
    scored.sort(key=lambda x: x["_score"], reverse=True)
    return scored


def get_candidates(question: str, top_k: int = TOP_K,
                   min_score: int = MIN_SCORE) -> list[dict]:
    """질문에 대한 상위 top_k 후보. 최소 점수 미만은 제외."""
    docs = get_all_docs()
    scored = [d for d in score_docs(question, docs) if d["_score"] >= min_score][:top_k]
    return [
        {
            "doc_id": d.get("문서ID", ""),
            "title": d.get("제목", ""),
            "summary": d.get("요약", ""),
            "body_excerpt": str(d.get("본문", ""))[:1500],
            "source_channel": d.get("출처채널", ""),
            "source_link": d.get("원본링크", ""),
            "score": d.get("_score", 0),
        }
        for d in scored
    ]


# ======================================================================
# 게시판 QNA 검색
# ======================================================================

def score_qna_docs(question: str, qna_docs: list[dict]) -> list[dict]:
    """게시판 문의글에 점수 부여. 제목×3 + 내용×2 + 댓글×1.
    점수 내림차순 정렬 결과 반환."""
    q_tokens = _tokenize(question)
    scored = []
    for d in qna_docs:
        title = str(d.get("제목", ""))
        content = str(d.get("내용", ""))
        comments_json = str(d.get("댓글_JSON", ""))

        title_hits = _count_hits(q_tokens, title)
        content_hits = _count_hits(q_tokens, content)
        comment_hits = _count_hits(q_tokens, comments_json)

        base = title_hits * 3 + content_hits * 2 + comment_hits * 1
        if base == 0:
            continue

        score = base
        scored.append({**d, "_score": score})
    scored.sort(key=lambda x: x["_score"], reverse=True)
    return scored


def get_qna_candidates(question: str, top_k: int = TOP_K,
                       min_score: int = MIN_SCORE) -> list[dict]:
    """게시판에서 질문과 유사한 상위 top_k 게시글. 최소 점수 미만은 제외."""
    qna_docs = get_all_qna_docs()
    scored = [d for d in score_qna_docs(question, qna_docs) if d["_score"] >= min_score][:top_k]
    return [
        {
            "qna_id": d.get("qna_id", d.get("문의글ID", "")),
            "title": d.get("제목", ""),
            "content": str(d.get("내용", ""))[:800],
            "comments_json": d.get("댓글_JSON", ""),
            "author": d.get("등록자", ""),
            "created_date": d.get("등록일시", ""),
            "score": d.get("_score", 0),
        }
        for d in scored
    ]
