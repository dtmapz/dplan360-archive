"""SP봇 Gemini 호출 래퍼 — 크롤러(구조화 출력)와 답변(자유 텍스트) 모두 지원."""
import json
import os
from google import genai
from google.genai import types


MODEL = "gemini-flash-latest"


def _get_client():
    """Streamlit 환경과 GitHub Actions 환경 모두 지원."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        try:
            import streamlit as st
            api_key = st.secrets.get("GEMINI_API_KEY", "")
        except Exception:
            pass
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set (env or streamlit secrets)")
    return genai.Client(api_key=api_key)


def summarize_doc(
    title_hint: str,
    body_text: str,
    approved_categories: list[str],
    pending_categories: list[str],
) -> dict:
    """크롤링한 원본 문서를 SP봇 저장용 메타데이터로 정제.

    반환: {"title","summary","category","new_category_proposal","keywords","status"}
    - category: approved_categories 중 하나 (해당 없으면 빈 문자열)
    - new_category_proposal: approved에 없고 새로 필요한 대분류명 (승인 대기용)
    - status: 활성 or 만료
    """
    schema = types.Schema(
        type=types.Type.OBJECT,
        properties={
            "title": types.Schema(type=types.Type.STRING),
            "summary": types.Schema(type=types.Type.STRING),
            "category": types.Schema(type=types.Type.STRING),
            "new_category_proposal": types.Schema(type=types.Type.STRING),
            "keywords": types.Schema(type=types.Type.STRING),
            "status": types.Schema(type=types.Type.STRING),
        },
        required=["title", "summary", "category", "keywords", "status"],
    )

    approved_str = ", ".join(approved_categories) if approved_categories else "(아직 없음)"
    pending_str = ", ".join(pending_categories) if pending_categories else "(없음)"

    prompt = f"""너는 D-PLAN360 내부 지식 문서를 분류하는 정확한 어시스턴트다.

# 원본 문서 정보
- 참고 제목: {title_hint}
- 본문:
{body_text[:8000]}

# 분류 기준
- 승인된 대분류(반드시 이 중에서 선택하려 시도): {approved_str}
- 대기 중인 대분류 (참고만, 사용 금지): {pending_str}

# 지시
1. title: 실제 문서 주제를 반영한 짧은 제목 (30자 이내)
2. summary: 핵심 내용 1~2문장 (100자 이내)
3. category: 위 승인 대분류 중 가장 적합한 것 하나. 어느 것도 맞지 않으면 빈 문자열
4. new_category_proposal: category를 비웠다면, 이 문서에 어울리는 신규 대분류명 하나 제안 (10자 이내). 아니면 빈 문자열
5. keywords: 검색용 키워드 5~10개, 콤마 구분 (구체 명사·매체명·용어)
6. status: 문서가 최신·유효하면 "활성", 명확히 만료·지난 이벤트면 "만료"
"""

    client = _get_client()
    resp = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema,
        ),
    )
    try:
        data = json.loads(resp.text)
    except Exception:
        return {
            "title": title_hint[:30],
            "summary": "",
            "category": "",
            "new_category_proposal": "",
            "keywords": "",
            "status": "활성",
        }
    return {
        "title": data.get("title", "")[:30] or title_hint[:30],
        "summary": data.get("summary", "")[:100],
        "category": data.get("category", "").strip(),
        "new_category_proposal": data.get("new_category_proposal", "").strip(),
        "keywords": data.get("keywords", "").strip(),
        "status": data.get("status", "활성").strip() or "활성",
    }


def answer_from_internal(question: str, candidates: list[dict], qna_candidates: list[dict] = None) -> tuple[str, list[str]]:
    """1차: 내부 자료 기반 답변. 프롬프트는 '자료 기반' 전용.

    반환: (답변 텍스트, 사용된 게시판 ID 리스트)
    """
    qna_candidates = qna_candidates or []

    # 기존 문서 참고 자료 (Notion은 링크 제외, 다른 출처는 링크 포함)
    ref_items = []
    for c in candidates:
        source_info = c['source_channel']
        # Notion이 아닌 경우만 링크 추가 (사용자가 직접 접근 가능)
        if not c.get('is_notion'):
            source_info += f" ({c['source_link']})"
        ref_items.append(
            f"- 제목: {c['title']}\n요약: {c['summary']}\n본문 발췌: {c['body_excerpt']}\n"
            f"출처: {source_info}"
        )
    ref = "\n\n".join(ref_items)

    # 게시판 QNA 참고 자료
    qna_ref = ""
    if qna_candidates:
        qna_ref_lines = []
        for q in qna_candidates:
            qna_ref_lines.append(
                f"- 제목: {q['title']}\n"
                f"질문 내용: {q['content']}\n"
                f"팀 내 답변: {q['comments_json']}"
            )
        qna_ref = "\n\n" + "\n\n".join(qna_ref_lines) if qna_ref_lines else ""

    full_ref = ref + qna_ref

    prompt = f"""너는 D-PLAN360 사내 지식 어시스턴트 SP봇이다.

# 참고 자료
{full_ref}

# 규칙
- 위 자료 안의 정보만 사용해 답하라. 모든 자료를 충분히 활용하라 (내부 문서, 게시판 등)
- 자료에 정확히 없는 사실은 만들어내지 말라
- 자료가 질문과 관련은 있지만 정확히 다른 하위 주제라면, 정확한 부분만 답하고 애매한 부분은 명시하라
- 자료에 질문 답이 전혀 없을 때만 "관련 자료 없음"이라고 짧게 밝혀라 (긴 사족 없이)
- **절대 금지:** 답변 본문에 하이퍼링크, URL, "바로가기" 등을 포함하지 말 것. 출처 표시는 시스템이 자동으로 처리함

# 질문
{question}
"""
    client = _get_client()
    resp = client.models.generate_content(model=MODEL, contents=prompt)
    answer_text = (resp.text or "").strip()

    # 게시판 글이 제공되었으면, 모두 사용된 것으로 간주
    # (LLM이 자동으로 가장 관련된 자료만 참고하므로, 선택된 게시판 글은 모두 관련 있음)
    used_qna_ids = [q['qna_id'] for q in qna_candidates] if qna_candidates else []

    return answer_text, used_qna_ids


def judge_answer_sufficient(question: str, answer: str) -> bool:
    """2차 판정: 별도 짧은 LLM 호출로 '답변이 실질적 정보를 담고 있는가' Yes/No.
    구조화 출력 강제. 애매하면 False (웹 검색으로 넘김).
    """
    schema = types.Schema(
        type=types.Type.OBJECT,
        properties={
            "sufficient": types.Schema(type=types.Type.BOOLEAN),
            "reason": types.Schema(type=types.Type.STRING),
        },
        required=["sufficient", "reason"],
    )
    prompt = f"""아래 답변이 사용자 질문에 대해 실질적으로 도움되는 정보를 담고 있는지 판단해라.

# 판정 기준 (내용 위주로 실제 판단, 특정 단어 유무만으로 결정하지 말 것)
- 답변이 질문의 핵심에 대해 구체적 절차·설명·정보를 제공하면 True
- 답변이 "관련 자료 없음" · "확인 불가" 정도로만 짧게 끝나거나, 질문과 완전 무관한 다른 주제만 다루면 False
- 답변이 부분적으로만 답하지만 그 부분만이라도 실질 정보라면 True
- 판단 애매하면 True (사용자에게 정보 제공을 우선)

# 질문
{question}

# 답변
{answer}
"""
    client = _get_client()
    try:
        resp = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=schema,
            ),
        )
        data = json.loads(resp.text or "{}")
        return bool(data.get("sufficient", False))
    except Exception:
        return False


def answer_with_web(question: str) -> tuple[str, list[dict]]:
    """3차: 웹 검색 활용 답변. 반환: (답변 텍스트, 웹 출처 리스트)
    웹 출처: [{"title": ..., "uri": ...}] — Gemini grounding metadata에서 추출.
    """
    prompt = f"""너는 D-PLAN360 사내 지식 어시스턴트 SP봇이다.
사용자 질문에 대해 웹 검색 결과를 적극 활용해 도움이 되는 답변을 작성해라.

# 규칙
- 검색된 최신 정보를 근거로 구체적으로 답하라
- 확신이 없는 부분은 그렇다고 명시해라
- 답변 끝에 별도의 면책·주의 문구를 붙이지 마라 (시스템이 자동으로 추가한다)

# 질문
{question}
"""
    client = _get_client()
    resp = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
        ),
    )
    text = (resp.text or "").strip()

    # Grounding metadata에서 웹 출처 추출 (여러 접근 경로 시도)
    web_sources = _extract_web_sources(resp)
    return text, web_sources


def _extract_web_sources(resp) -> list[dict]:
    """Gemini 응답에서 웹 출처 추출. SDK 버전별 접근 경로 방어적으로 처리."""
    import sys
    web_sources = []
    seen_uris = set()

    def _add(uri: str, title: str):
        uri = (uri or "").strip()
        if not uri or uri in seen_uris:
            return
        seen_uris.add(uri)
        web_sources.append({"title": (title or uri).strip(), "uri": uri})

    try:
        candidates = getattr(resp, "candidates", None) or []
        for cand in candidates:
            # 경로 1: candidate.grounding_metadata.grounding_chunks[].web
            gm = getattr(cand, "grounding_metadata", None)
            if gm:
                chunks = getattr(gm, "grounding_chunks", None) or []
                for c in chunks:
                    web = getattr(c, "web", None)
                    if web:
                        _add(getattr(web, "uri", ""), getattr(web, "title", ""))
                # 경로 2: grounding_metadata.web_search_queries + search_entry_point (URL만)
                # → 표시엔 부적합, 스킵
            # 경로 3: candidate.citation_metadata.citation_sources (구버전)
            cm = getattr(cand, "citation_metadata", None)
            if cm:
                sources = getattr(cm, "citation_sources", None) or []
                for s in sources:
                    _add(getattr(s, "uri", ""), getattr(s, "title", ""))
    except Exception as e:
        print(f"[SPBOT] grounding 추출 실패: {e}", file=sys.stderr)

    return web_sources
