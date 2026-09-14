"""
공개 개인정보처리방침 — Google OAuth 동의 화면("D-PLAN360 알림")에 등록하는 URL.

streamlit_app.py 가 로그인 확인보다 먼저 `?page=privacy` 를 검사해 이 페이지만 그리고 멈춘다.
로그인 없이 누구나 보는 화면이므로 내부 주소는 시크릿에서만 읽는다(§17-24).
"""

import html

import streamlit as st

EFFECTIVE_DATE = "2026년 9월 14일"

_SECTIONS = [
    (
        "1. 개요",
        "<p>\"D-PLAN360 알림\"(이하 '서비스')은 디플랜360이 사내 업무 자동화를 위해 운영하는 "
        "Google Apps Script 기반 알림 서비스입니다. 사내 구성원만을 대상으로 하며 외부에 제공되지 않습니다.</p>",
    ),
    (
        "2. 접근하는 정보",
        "<p>서비스는 설치된 Google 스프레드시트에 기록된 사내 업무 데이터만 읽고 씁니다.</p>"
        "<ul>"
        "<li>사내 행사 일정(행사명, 일시, 장소, 메모), 소재 가이드 검증 결과, 캠페인 집행 이력 요약</li>"
        "<li>알림 발송 여부 표시</li>"
        "</ul>"
        "<p>Google 계정의 메일, 드라이브 파일, 연락처 등 그 밖의 정보에는 접근하지 않습니다.</p>",
    ),
    (
        "3. 이용 목적",
        "<p>행사 참석 안내 등 업무 알림 메일을 사내 구성원에게 발송하는 데에만 사용합니다.</p>",
    ),
    (
        "4. 제3자 제공 및 처리 위탁",
        "<p>정보를 제3자에게 판매하거나 제공하지 않습니다. 메일 발송을 위해 Google Cloud(발송 중계)와 "
        "네이버웍스(사내 메일)를 이용하며, 알림은 회사 도메인 주소로만 발송됩니다.</p>",
    ),
    (
        "5. 보관 및 파기",
        "<p>서비스는 정보를 따로 저장하지 않습니다. 원본 데이터는 해당 스프레드시트에만 있으며, "
        "시트에서 삭제하면 서비스에서도 더 이상 사용되지 않습니다.</p>",
    ),
    (
        "6. Google 사용자 데이터 정책 준수",
        "<p>Google API를 통해 받은 정보의 사용과 전송은 Google API 서비스 사용자 데이터 정책"
        "(제한적 사용 요건 포함)을 준수합니다.</p>",
    ),
]


def render_privacy_policy() -> None:
    """로그인 없이 보이는 개인정보처리방침 한 장. 사이드바는 숨긴다."""
    # 문의 주소는 시크릿으로만 참조(§17-24) — 미설정 시 팀명만 표시
    contact_email = st.secrets.get("PRIVACY_CONTACT_EMAIL", "")
    contact = "디플랜360 SP팀" + (f"({html.escape(contact_email)})" if contact_email else "")

    sections = "".join(
        f"<h2 style='font-size:15px; font-weight:700; color:#0B0B0B; margin:28px 0 8px;'>{title}</h2>"
        f"<div class='pp-body'>{body}</div>"
        for title, body in _SECTIONS
    )
    sections += (
        "<h2 style='font-size:15px; font-weight:700; color:#0B0B0B; margin:28px 0 8px;'>7. 문의</h2>"
        f"<div class='pp-body'><p>{contact}</p></div>"
    )

    st.markdown(
        "<style>"
        "[data-testid='stSidebar'], [data-testid='collapsedControl'] { display: none; }"
        ".pp-body p, .pp-body li { font-size:14px; line-height:1.75; color:#333; margin:0 0 6px; }"
        ".pp-body ul { margin:4px 0 8px; padding-left:20px; }"
        "</style>"
        "<div style='max-width:720px; margin:48px auto 80px;'>"
        "<div style='font-size:11px; font-weight:700; letter-spacing:0.12em; color:#7A4E0A;'>D-PLAN360</div>"
        "<h1 style='font-size:20px; font-weight:700; color:#0B0B0B; margin:6px 0 4px;'>"
        "D-PLAN360 알림 개인정보처리방침</h1>"
        f"<div style='font-size:12px; color:#888; padding-bottom:16px; border-bottom:0.5px solid #ddd;'>"
        f"시행일: {EFFECTIVE_DATE}</div>"
        f"{sections}"
        "</div>",
        unsafe_allow_html=True,
    )
