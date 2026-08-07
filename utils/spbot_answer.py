"""SP봇 답변 파이프라인 — 스펙 §4-3.

1차: 내부DB로 답변 시도
     ↓ (LLM 판정: 불충분)
2차: 웹 검색 전용 프롬프트로 재답변
     ↓
최종 답변 (출처 + 안내 문구)
"""
from utils.spbot_search import get_candidates
from utils.spbot_llm import (
    answer_from_internal,
    judge_answer_sufficient,
    answer_with_web,
)


NOTICE = "\n\n※ 부정확한 답변이 있을 수 있으니 관련 문서를 함께 확인해주세요."


def answer(question: str) -> dict:
    """질문 → 답변 흐름. 반환: {"text","sources","web_sources","stage"}
    stage: 'internal' | 'web' | 'no_candidates_web'
    """
    question = (question or "").strip()
    if not question:
        return {
            "text": "질문을 입력해 주세요.",
            "sources": [], "web_sources": [], "stage": "empty",
        }

    candidates = get_candidates(question)

    if not candidates:
        web_answer, web_sources = answer_with_web(question)
        return {
            "text": web_answer + NOTICE,
            "sources": [],
            "web_sources": web_sources,
            "stage": "no_candidates_web",
        }

    # 1차: 내부 자료 답변
    internal_answer = answer_from_internal(question, candidates)

    # 2차: LLM 판정
    if judge_answer_sufficient(question, internal_answer):
        return {
            "text": internal_answer + NOTICE,
            "sources": candidates,
            "web_sources": [],
            "stage": "internal",
        }

    # 3차: 웹 검색
    web_answer, web_sources = answer_with_web(question)
    return {
        "text": web_answer + NOTICE,
        "sources": [],  # 내부 자료 출처는 오해 유발이라 미노출
        "web_sources": web_sources,
        "stage": "web",
    }
