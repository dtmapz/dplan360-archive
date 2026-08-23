"""Case Study 자동 카피 생성 — Gemini Flash Latest.

CASESTUDY_SPEC §4에 따라 사용자 입력을 종합해 슬라이드용 필드를 JSON으로 반환.
extra_note는 보조 컨텍스트로만 사용, 단독으로 title/caption을 만들지 않음.
"""
import json
import os
from google import genai
from google.genai import types

MODEL = "gemini-flash-latest"


def _get_client():
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


_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        "eyebrow": types.Schema(type=types.Type.STRING),
        "title": types.Schema(type=types.Type.STRING),
        "caption": types.Schema(type=types.Type.STRING),
        "challenge_bullets": types.Schema(
            type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING)
        ),
        "approach_bullets": types.Schema(
            type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING)
        ),
        "insight_bullets": types.Schema(
            type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING)
        ),
    },
    required=[
        "eyebrow", "title", "caption",
        "challenge_bullets", "approach_bullets", "insight_bullets",
    ],
)


def generate_copy(payload: dict) -> dict:
    """payload 필드:
    brand, advertiser, industry, media, target_gender, target_age,
    period_start, period_end, campaign_types (list),
    objective, strategy, insight, extra_note, results (list of {kpi_name, value})
    """
    results_str = "\n".join(
        f"- {r.get('kpi_name', '')}: {r.get('value', '')}"
        for r in payload.get("results", [])
        if r.get("kpi_name") or r.get("value")
    ) or "(없음)"

    types_str = ", ".join(payload.get("campaign_types", []) or []) or "(미지정)"

    prompt = f"""너는 D-PLAN360 광고 대행사의 시니어 카피라이터다.
아래 캠페인 데이터를 바탕으로 사내 성공사례 슬라이드용 카피를 만든다.

# 캠페인 데이터
- 광고주: {payload.get('advertiser', '')}
- 브랜드: {payload.get('brand', '')}
- 업종: {payload.get('industry', '')}
- 매체: {payload.get('media', '')}
- 타겟: {payload.get('target_gender', '')} · {payload.get('target_age', '')}
- 기간: {payload.get('period_start', '')} ~ {payload.get('period_end', '')}
- 캠페인 타입: {types_str}
- 캠페인 목표(objective, 사용자 초안):
{payload.get('objective', '')}
- 캠페인 전략(strategy, 사용자 초안):
{payload.get('strategy', '')}
- 캠페인 인사이트(insight, 사용자 초안):
{payload.get('insight', '')}
- 캠페인 성과(results):
{results_str}
- 참고 메모(extra_note, 보조 컨텍스트 · 단독 사용 금지):
{payload.get('extra_note', '')}

# 규칙
1. eyebrow: 캠페인 성격·매체 조합의 태그라인. 영문 대문자, 30자 이내. 예: "AI × PERFORMANCE", "BRAND AWARENESS", "FULL-FUNNEL GROWTH".
2. title: 성과 수치 중심 헤드라인. 2~3줄, 총 45자 이내. 강조할 수치는 [대괄호]로 감싼다. results 배열의 수치 최소 1개 이상 반영.
3. caption: 크리에이티브 이미지 아래 한 줄 설명. 브랜드·제품·캠페인 핵심을 함축. 60자 이내. 캠페인 전체 맥락 기반.
4. challenge_bullets: objective를 2~3개 bullet로 구조화. 각 55자 이내. 배경·문제·필요성 등 핵심 포인트별 분리.
5. approach_bullets: strategy를 3개 bullet로 구조화. 각 50자 이내. 실행 액션 중심(도입한 것, 유지한 것, 확장한 것 등).
6. insight_bullets: insight를 2~3개 bullet로 구조화. 각 55자 이내. 테스트 결과·학습·시사점 중심. 수치 반영.
7. 톤: 사내 성공사례 톤 (내부적, 사실 기반, 과장 없음). "혁신적/획기적" 형용사 금지.
8. extra_note는 위 6개 필드 작성 시 **보조 힌트**로만 사용. 단독으로 title/caption을 만들지 않는다.
9. 모든 텍스트는 한국어.
"""

    client = _get_client()
    resp = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=_SCHEMA,
            temperature=0.7,
        ),
    )
    text = resp.text or "{}"
    data = json.loads(text)
    # normalize
    for k in ("challenge_bullets", "approach_bullets", "insight_bullets"):
        data[k] = [str(x).strip() for x in (data.get(k) or []) if str(x).strip()]
    return data
