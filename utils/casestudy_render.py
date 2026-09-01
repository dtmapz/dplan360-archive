"""Case Study 16:9 슬라이드 HTML 렌더러.

CASESTUDY_SPEC §3의 final v2 레이아웃을 데이터 기반으로 재현.
Streamlit에서는 st.components.v1.html로 렌더링. 전체 HTML은 download_button으로 저장.
"""
import html
import re
from typing import Any


def _esc(s: Any) -> str:
    return html.escape(str(s or ""))


def _title_html(title: str) -> str:
    """[대괄호]로 감싼 부분은 accent 스타일."""
    if not title:
        return ""
    parts = re.split(r"(\[[^\]]+\])", title)
    out = []
    for p in parts:
        if p.startswith("[") and p.endswith("]"):
            out.append(f'<span class="accent">{_esc(p[1:-1])}</span>')
        else:
            out.append(_esc(p).replace("\n", "<br>"))
    return "".join(out)


def _bullets_html(items: list[str]) -> str:
    if not items:
        return "<div style='color:#999;font-size:12px;'>(내용 없음)</div>"
    lis = "".join(f"<li>{_esc(x)}</li>" for x in items)
    return f"<ul class='bullet-list'>{lis}</ul>"


def _campaign_type_pills(types: list[str]) -> str:
    types = [t.strip() for t in (types or []) if t.strip()]
    if not types:
        return ""
    if len(types) >= 3:
        return "<span class='type-pill'>FULL-FUNNEL</span>"
    return "".join(f"<span class='type-pill'>{_esc(t.upper())}</span>" for t in types)


def _period_str(start: str, end: str) -> str:
    start = str(start or "").strip()
    end = str(end or "").strip()
    if start and end and start != end:
        return f"{start} ~ {end}"
    return start or end or "-"


def _target_str(gender: str, age: str) -> str:
    g = str(gender or "").strip()
    a = str(age or "").strip()
    if g and a:
        return f"{g} · {a}"
    return g or a or "-"


def _metrics_html(results: list[dict]) -> str:
    results = [r for r in (results or []) if r.get("kpi_name") or r.get("value")]
    if not results:
        return "<div style='color:#999;font-size:12px;'>(성과 데이터 없음)</div>"
    n = min(len(results), 4)
    grid_cls = {2: "metrics-2", 3: "metrics-3", 4: "metrics-4"}.get(n, "metrics-3")
    cells = []
    for i, r in enumerate(results[:4]):
        hero_cls = " hero" if i == 0 else ""
        cells.append(
            f"<div>"
            f"<div class='metric-label'>{_esc(r.get('kpi_name', ''))}</div>"
            f"<div class='metric-value{hero_cls}'>{_esc(r.get('value', ''))}</div>"
            f"</div>"
        )
    return f"<div class='metrics-grid {grid_cls}'>{''.join(cells)}</div>"


_STYLE = """
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: #E8EAED; font-family: 'Pretendard Variable', Pretendard, -apple-system, 'Malgun Gothic', sans-serif; padding: 12px; }
.cs-slide {
  width: 1280px; height: 720px; background: #fff;
  box-shadow: 0 4px 24px rgba(0,0,0,0.08);
  display: grid; grid-template-rows: 72px 40px 1fr 40px;
  overflow: hidden; margin: 0 auto;
  transform-origin: top left;
}
.cs-header { background: #0F1E3D; color: #fff; display:flex; align-items:center; justify-content:space-between; padding:0 40px; }
.cs-header-left { display:flex; align-items:center; gap:20px; }
.cs-badge { background:#4C7DFF; color:#fff; font-size:11px; font-weight:700; letter-spacing:1.2px; padding:6px 12px; border-radius:3px; }
.cs-brand-info { display:flex; align-items:baseline; gap:12px; }
.cs-brand-name { font-size:20px; font-weight:700; }
.cs-advertiser { font-size:13px; color:#A5B4CE; }
.cs-header-right { display:flex; align-items:center; gap:16px; }
.scope-badge { font-size:10.5px; font-weight:700; letter-spacing:1.2px; padding:5px 10px; border-radius:3px; display:flex; align-items:center; gap:6px; }
.scope-internal { background:#35476B; color:#E5E9F0; }
.scope-external { background:#16A34A; color:#fff; }
.scope-dot { width:6px; height:6px; border-radius:50%; background:currentColor; }
.cs-logo { font-size:12px; font-weight:700; letter-spacing:2px; color:#A5B4CE; }
.meta-strip { background:#F5F7FB; border-bottom:1px solid #E5E9F0; display:flex; align-items:center; padding:0 40px; gap:24px; font-size:12px; color:#374151; }
.meta-item { display:flex; align-items:center; gap:8px; }
.meta-key { font-size:10.5px; font-weight:700; color:#6B7280; letter-spacing:1px; text-transform:uppercase; }
.meta-val { font-weight:600; color:#0F1E3D; }
.meta-divider { width:1px; height:14px; background:#D1D5DB; }
.type-pill { background:#EEF2FF; color:#4C7DFF; font-size:10.5px; font-weight:700; padding:3px 8px; border-radius:3px; letter-spacing:0.3px; margin-left:4px; }
.cs-body { padding:20px 40px 18px; display:grid; grid-template-columns: 560px 1fr; grid-template-rows:auto 1fr; gap:18px 32px; min-height:0; }
.creative-block { display:flex; flex-direction:column; gap:8px; }
.creative { width:560px; height:315px; background: linear-gradient(135deg, #D4C5B0 0%, #A89578 100%); position:relative; overflow:hidden; border-radius:4px; }
.creative img { width:100%; height:100%; object-fit:cover; display:block; }
.creative-placeholder { color:rgba(255,255,255,0.6); font-size:13px; text-transform:uppercase; letter-spacing:1.5px; position:absolute; top:50%; left:50%; transform:translate(-50%,-50%); }
.creative-caption { font-size:13px; color:#6B7280; line-height:1.5; padding-left:2px; }
.right-top { display:flex; flex-direction:column; gap:14px; min-width:0; }
.eyebrow { font-size:11.5px; font-weight:700; color:#4C7DFF; letter-spacing:1.8px; margin-bottom:8px; }
.cs-title { font-size:23px; font-weight:800; line-height:1.28; color:#0F1E3D; letter-spacing:-0.5px; }
.cs-title .accent { color:#4C7DFF; }
.results { background:#F5F7FB; border-left:3px solid #4C7DFF; padding:14px 18px; border-radius:0 4px 4px 0; }
.results-label { font-size:11px; font-weight:700; color:#4C7DFF; letter-spacing:1.5px; margin-bottom:10px; }
.metrics-grid { display:grid; gap:12px; }
.metrics-2 { grid-template-columns: repeat(2,1fr); }
.metrics-3 { grid-template-columns: repeat(3,1fr); }
.metrics-4 { grid-template-columns: repeat(4,1fr); }
.metric-label { font-size:11.5px; color:#6B7280; margin-bottom:3px; }
.metric-value { font-size:24px; font-weight:800; color:#0F1E3D; letter-spacing:-1px; line-height:1; }
.metric-value.hero { color:#4C7DFF; font-size:26px; }
.bottom-row { grid-column: 1 / -1; display:grid; grid-template-columns: 1fr 1fr 1fr; gap:28px; }
.section-title { font-size:15px; font-weight:700; color:#0F1E3D; margin-bottom:10px; padding-bottom:8px; border-bottom:2px solid #0F1E3D; display:flex; align-items:center; justify-content:space-between; }
.section-title .kr { color:#6B7280; font-weight:500; font-size:12px; }
.bullet-list { list-style:none; }
.bullet-list li { padding-left:16px; position:relative; margin-bottom:6px; font-size:14px; line-height:1.5; color:#374151; }
.bullet-list li::before { content:''; position:absolute; left:0; top:8px; width:5px; height:5px; background:#4C7DFF; border-radius:50%; }
.cs-footer { background:#F5F7FB; border-top:1px solid #E5E9F0; }
</style>
"""


def build_slide_html(cs: dict, ai: dict, standalone: bool = True, scale: float = 1.0) -> str:
    """cs: sheet dict / ai: llm output.

    standalone=True → 완전한 HTML(다운로드/새 탭용).
    standalone=False → body 내용만(streamlit components용).
    scale: 슬라이드 축소 배율 (1.0 = 1280px).
    """
    scope = (cs.get("share_scope") or "Internal").strip()
    scope_cls = "scope-external" if scope.lower() == "external" else "scope-internal"
    scope_label = scope.upper()

    brand_line_right = " · ".join(
        [x for x in [cs.get("advertiser"), cs.get("industry")] if x]
    )

    creative_url = cs.get("creative_image_url") or ""
    if creative_url:
        creative_inner = f"<img src='{_esc(creative_url)}' alt='creative'/>"
    else:
        creative_inner = "<div class='creative-placeholder'>CAMPAIGN CREATIVE · 16:9</div>"

    wrap_w = round(1280 * scale)
    wrap_h = round(720 * scale)
    body_html = f"""
<div class='cs-slide-wrap' style='width:{wrap_w}px; height:{wrap_h}px; overflow:hidden; margin:0 auto;'>
<div class='cs-slide' style='transform: scale({scale}); transform-origin: top left; margin:0;'>
  <div class='cs-header'>
    <div class='cs-header-left'>
      <span class='cs-badge'>CASE STUDY</span>
      <div class='cs-brand-info'>
        <span class='cs-brand-name'>{_esc(cs.get('brand', ''))}</span>
        <span class='cs-advertiser'>{_esc(brand_line_right)}</span>
      </div>
    </div>
    <div class='cs-header-right'>
      <span class='scope-badge {scope_cls}'><span class='scope-dot'></span>{_esc(scope_label)}</span>
      <span class='cs-logo'>D-PLAN360</span>
    </div>
  </div>

  <div class='meta-strip'>
    <div class='meta-item'><span class='meta-key'>Media</span><span class='meta-val'>{_esc(cs.get('media', '-'))}</span></div>
    <div class='meta-divider'></div>
    <div class='meta-item'><span class='meta-key'>Period</span><span class='meta-val'>{_esc(_period_str(cs.get('period_start', ''), cs.get('period_end', '')))}</span></div>
    <div class='meta-divider'></div>
    <div class='meta-item'><span class='meta-key'>Target</span><span class='meta-val'>{_esc(_target_str(cs.get('target_gender', ''), cs.get('target_age', '')))}</span></div>
    <div class='meta-divider'></div>
    <div class='meta-item'><span class='meta-key'>Type</span>{_campaign_type_pills(cs.get('campaign_types', []))}</div>
  </div>

  <div class='cs-body'>
    <div class='creative-block'>
      <div class='creative'>{creative_inner}</div>
      <div class='creative-caption'>{_esc(ai.get('caption', ''))}</div>
    </div>

    <div class='right-top'>
      <div>
        <div class='eyebrow'>{_esc(ai.get('eyebrow', ''))}</div>
        <h1 class='cs-title'>{_title_html(ai.get('title', ''))}</h1>
      </div>
      <div class='results'>
        <div class='results-label'>RESULTS</div>
        {_metrics_html(cs.get('results', []))}
      </div>
    </div>

    <div class='bottom-row'>
      <div>
        <div class='section-title'>Challenge <span class='kr'>캠페인 목표</span></div>
        {_bullets_html(ai.get('challenge_bullets', []))}
      </div>
      <div>
        <div class='section-title'>Approach <span class='kr'>캠페인 전략</span></div>
        {_bullets_html(ai.get('approach_bullets', []))}
      </div>
      <div>
        <div class='section-title'>Insight <span class='kr'>인사이트 · 테스트</span></div>
        {_bullets_html(ai.get('insight_bullets', []))}
      </div>
    </div>
  </div>

  <div class='cs-footer'></div>
</div>
</div>
"""

    if not standalone:
        return _STYLE + body_html

    return f"""<!DOCTYPE html><html lang='ko'><head><meta charset='UTF-8'>
<title>{_esc(cs.get('brand', ''))} Case Study</title>
<link href='https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/variable/pretendardvariable-dynamic-subset.css' rel='stylesheet'>
{_STYLE}
</head><body>{body_html}</body></html>"""
