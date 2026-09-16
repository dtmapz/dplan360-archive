"""Case Study 자동 카피 생성 — Gemini Flash Latest.

CASESTUDY_SPEC §4에 따라 사용자 입력을 종합해 슬라이드용 필드를 JSON으로 반환.
extra_note는 보조 컨텍스트로만 사용, 단독으로 title/caption을 만들지 않음.
"""
import json
import os
from google import genai
from google.genai import types

MODEL = "gemini-flash-latest"

# 제목 길이 상한(공백 포함). pages/11_CaseStudy.py:TITLE_MAX_LEN 과 같은 값
TITLE_MAX_LEN = 44


def _title_text(title: str) -> str:
    """길이·중복 판정용 평문. [대괄호]는 강조 문법이라 빼고, 줄바꿈은 공백 1칸으로 본다."""
    return (title or "").replace("[", "").replace("]", "").replace("\\n", " ").replace("\n", " ").strip()


def banned_terms(results: list) -> list:
    """제목에 쓰면 안 되는 문자열 — results 의 지표명과 수치."""
    out = []
    for r in results or []:
        for key in ("kpi_name", "value"):
            v = str(r.get(key, "")).strip()
            if len(v) >= 2:
                out.append(v)
    return out


def title_issues(title: str, results: list) -> list:
    """제목 규칙 위반 목록. 비어 있으면 통과."""
    plain = _title_text(title)
    issues = []
    if not plain:
        return ["제목이 비어 있음"]
    if len(plain) > TITLE_MAX_LEN:
        issues.append(f"{TITLE_MAX_LEN}자 초과({len(plain)}자)")
    if any(ch.isdigit() for ch in plain) or "%" in plain:
        issues.append("성과 수치 포함")
    dup = [b for b in banned_terms(results) if b and b in plain]
    if dup:
        issues.append("results 와 중복: " + ", ".join(dict.fromkeys(dup)))
    return issues


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
        "title": types.Schema(
            type=types.Type.STRING,
            description=(
                f"캠페인 실행·전략 중심 헤드라인. 공백 포함 {TITLE_MAX_LEN}자 이내. "
                "숫자·%·성과 수치를 절대 포함하지 않는다."
            ),
        ),
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
    _banned = banned_terms(payload.get("results", []))
    banned_str = "\n".join(f"  · {b}" for b in _banned) or "  · (없음)"

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

# 제목(title) 제약 — 가장 중요. 하나라도 어기면 실패로 간주한다
- 공백 포함 {TITLE_MAX_LEN}자 이내. 초과 금지.
- **숫자를 한 글자도 쓰지 않는다.** %, 배수, 금액, 건수 등 모든 수치 표기 금지.
- 아래 문자열은 제목에 절대 넣지 않는다 (성과 영역과 중복):
{banned_str}
- 성과는 "개선 · 확대 · 효율화 · 절감" 같은 정성 표현까지만.
- 제목은 **무엇을 했는지**(전략·실행·도입한 것)를 쓴다.
- 한국어 띄어쓰기 규칙을 지키고 단어 중간에서 끊지 않는다.
- 강조할 핵심 어구(수치 아님)는 [대괄호]로 감싼다.

좋은 예: "파트너십 광고를 [상시 운영]으로 확장해 구매 효율 개선"
나쁜 예: "파트너십 광고 확장으로 구매 건수 +35% 증대 및 구매당 비용 -26% 절감"  ← 수치 포함·중복·길이 초과

# 규칙
1. eyebrow: 캠페인 성격·매체 조합의 태그라인. 영문 대문자, 30자 이내. 예: "AI × PERFORMANCE", "BRAND AWARENESS", "FULL-FUNNEL GROWTH".
2. title: 아래 "제목 제약"을 그대로 따른다.
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

    # 제목 규칙은 프롬프트만으로 지켜지지 않는다(2026-09-16 실측: 수치 포함·49자).
    # 위반이면 제목만 다시 쓰게 하고, 통과한 결과로 교체한다.
    data["title"] = _enforce_title(client, data.get("title", ""), payload, _banned)
    return data


def _enforce_title(client, title: str, payload: dict, banned: list, tries: int = 2) -> str:
    """제목 규칙 위반 시 제목만 재생성. 끝내 실패하면 가장 덜 위반한 후보를 돌려준다."""
    results = payload.get("results", [])
    best, best_issues = title, title_issues(title, results)
    if not best_issues:
        return title

    for _ in range(tries):
        fix_prompt = f"""아래 캠페인 성공사례 슬라이드의 제목을 다시 써라.

- 캠페인: {payload.get('brand', '')} / {payload.get('advertiser', '')} / 매체 {payload.get('media', '')}
- 실행 전략: {payload.get('strategy', '')}
- 캠페인 목표: {payload.get('objective', '')}

기존 제목(규칙 위반): {best}
위반 내용: {', '.join(best_issues)}

제목 규칙 (하나라도 어기면 실패):
1. 공백 포함 {TITLE_MAX_LEN}자 이내
2. 숫자를 한 글자도 쓰지 않는다 (%, 배수, 금액, 건수 전부 금지)
3. 다음 문자열 사용 금지: {', '.join(banned) or '(없음)'}
4. 무엇을 했는지(전략·실행) 중심으로 쓰고, 성과는 "개선·확대·효율화" 같은 정성 표현까지만
5. 한국어 띄어쓰기 규칙을 지키고 단어 중간에서 끊지 않는다
6. 강조할 핵심 어구(수치 아님)는 [대괄호]로 감싼다

제목 문자열만 출력한다. 따옴표·설명 없이."""
        try:
            r = client.models.generate_content(
                model=MODEL,
                contents=fix_prompt,
                config=types.GenerateContentConfig(temperature=0.2),
            )
        except Exception:
            break
        cand = (r.text or "").strip().strip('"').splitlines()[0].strip() if (r.text or "").strip() else ""
        if not cand:
            continue
        issues = title_issues(cand, results)
        if not issues:
            return cand
        if len(issues) < len(best_issues):
            best, best_issues = cand, issues

    return best
