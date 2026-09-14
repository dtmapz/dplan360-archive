"""
네이버웍스 SMTP 메일 중계 — Cloud Run functions (Python 3.12)

Apps Script 는 SMTP 로 직접 보낼 수 없어서 **발송만** 이 함수가 대신한다.
발송 시각·대상 판단은 계속 Apps Script 가 한다.

    POST /    헤더  X-Relay-Secret: <RELAY_SECRET>
    {"to": "a@example.com" | ["a@example.com", ...], "subject": "...", "html": "...", "text": "..."}
    → 200 {"ok": true, "message_id": "..."}

환경변수 (코드에 주소·비밀값을 두지 않는다 — Public 레포)
    SMTP_USER                  SMTP 로그인 공용 구성원 계정. 그룹 메일은 로그인할 수 없다
    SMTP_PASSWORD              SMTP_USER 의 외부 앱 비밀번호          ← Secret Manager
    RELAY_SECRET               Apps Script 와 공유하는 비밀값           ← Secret Manager
    MAIL_FROM                  받는 사람에게 보이는 발신자. 예) SP팀 <sender@example.com>
                               ⚠️ 네이버웍스 SMTP 는 로그인 계정과 다른 주소로 발신할 수 없다
                               (554 5.7.1 The sender address is unauthorized). 주소는 SMTP_USER 와
                               같게 두고 표시 이름만 바꾼다
    REPLY_TO                   (선택) 답장 받을 주소. 그룹 메일로 답장이 가게 할 때 사용
    ALLOWED_RECIPIENT_DOMAINS  수신 허용 도메인(콤마 구분). 이 외 주소로는 보내지 않는다
    SMTP_HOST / SMTP_PORT      기본 smtp.worksmobile.com / 465 (SSL)

보안 원칙
    · 발신자(From)와 로그인 계정은 서버 환경변수로만 정한다 — 요청으로 바꿀 수 없음
    · 수신자는 허용 도메인만 — 비밀값이 새도 외부 스팸 발송 창구가 되지 않게
    · 로그에 수신 주소·본문을 남기지 않는다 (건수·결과만)
"""

import hmac
import html as html_lib
import json
import logging
import os
import re
import smtplib
from email.message import EmailMessage
from email.utils import formatdate, getaddresses, make_msgid, parseaddr

import functions_framework

MAX_RECIPIENTS = 10
MAX_SUBJECT_LEN = 300
MAX_BODY_LEN = 500_000
SMTP_TIMEOUT_SEC = 20

_ADDR_RE = re.compile(r"^[^@\s]+@([^@\s]+\.[^@\s]+)$")

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("mail_relay")


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _reply(status: int, **body):
    return (
        json.dumps(body, ensure_ascii=False),
        status,
        {"Content-Type": "application/json; charset=utf-8"},
    )


def _parse_recipients(value, allowed_domains: set[str]) -> list[str]:
    """문자열 또는 문자열 리스트 → 허용 도메인 주소 리스트(중복 제거, 순서 유지)."""
    items = value if isinstance(value, list) else [value]
    if not items or not all(isinstance(v, str) for v in items):
        raise ValueError("to 는 문자열 또는 문자열 배열이어야 합니다")

    out: list[str] = []
    for _, addr in getaddresses(items):
        addr = addr.strip().lower()
        if not addr:
            continue
        m = _ADDR_RE.match(addr)
        if not m:
            raise ValueError("잘못된 수신 주소 형식")
        if m.group(1) not in allowed_domains:
            raise ValueError("허용되지 않은 수신 도메인")
        if addr not in out:
            out.append(addr)

    if not out:
        raise ValueError("수신자가 없습니다")
    if len(out) > MAX_RECIPIENTS:
        raise ValueError(f"수신자는 최대 {MAX_RECIPIENTS}명")
    return out


def _html_to_text(html: str) -> str:
    """HTML 메일의 텍스트 대체본 — 텍스트만 보이는 클라이언트용 최소 변환."""
    s = re.sub(r"(?is)<(script|style)\b.*?</\1>", "", html)
    s = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|h[1-6]|li|table)>", "\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = html_lib.unescape(s)
    s = re.sub(r"[ \t]+", " ", s)
    return re.sub(r"\n\s*\n+", "\n\n", s).strip()


def _server_text(raw) -> str:
    """SMTP 서버 응답 문구(bytes/str) → 로그·응답용 짧은 문자열."""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", "replace")
    return " ".join(str(raw or "").split())[:200]


def _build_message(mail_from: str, to: list[str], subject: str, html: str, text: str,
                   reply_to: str = "") -> EmailMessage:
    from_domain = parseaddr(mail_from)[1].rpartition("@")[2] or None
    msg = EmailMessage()
    msg["From"] = mail_from
    msg["To"] = ", ".join(to)
    if reply_to:
        msg["Reply-To"] = reply_to
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=from_domain)
    msg.set_content(text or _html_to_text(html) or " ")
    if html:
        msg.add_alternative(html, subtype="html")
    return msg


@functions_framework.http
def send_mail(request):
    if request.method != "POST":
        return _reply(405, ok=False, error="method_not_allowed")

    relay_secret = _env("RELAY_SECRET")
    smtp_user = _env("SMTP_USER")
    smtp_password = _env("SMTP_PASSWORD")
    mail_from = _env("MAIL_FROM")
    reply_to = _env("REPLY_TO")
    allowed_domains = {d.strip().lower() for d in _env("ALLOWED_RECIPIENT_DOMAINS").split(",") if d.strip()}
    if not (relay_secret and smtp_user and smtp_password and mail_from and allowed_domains):
        log.error("환경변수 미설정 — RELAY_SECRET/SMTP_USER/SMTP_PASSWORD/MAIL_FROM/ALLOWED_RECIPIENT_DOMAINS")
        return _reply(500, ok=False, error="relay_not_configured")
    if reply_to and ("\r" in reply_to or "\n" in reply_to or not _ADDR_RE.match(parseaddr(reply_to)[1])):
        log.error("REPLY_TO 형식 오류")
        return _reply(500, ok=False, error="relay_not_configured")

    given = request.headers.get("X-Relay-Secret", "")
    if not hmac.compare_digest(given.encode(), relay_secret.encode()):
        return _reply(401, ok=False, error="unauthorized")

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _reply(400, ok=False, error="invalid_json")

    subject = payload.get("subject")
    html = payload.get("html") or ""
    text = payload.get("text") or ""
    try:
        to = _parse_recipients(payload.get("to"), allowed_domains)
        if not isinstance(subject, str) or not subject.strip():
            raise ValueError("subject 가 비어 있습니다")
        if "\r" in subject or "\n" in subject or len(subject) > MAX_SUBJECT_LEN:
            raise ValueError("subject 형식 오류")
        if not isinstance(html, str) or not isinstance(text, str):
            raise ValueError("html/text 는 문자열이어야 합니다")
        if not (html or text):
            raise ValueError("html 또는 text 중 하나는 필요합니다")
        if len(html) + len(text) > MAX_BODY_LEN:
            raise ValueError("본문이 너무 큽니다")
    except ValueError as e:
        return _reply(400, ok=False, error="bad_request", detail=str(e))

    msg = _build_message(mail_from, to, subject.strip(), html, text, reply_to)

    host = _env("SMTP_HOST", "smtp.worksmobile.com")
    port = int(_env("SMTP_PORT", "465"))
    # 어느 단계에서 실패했는지 — connect(연결) / login(로그인) / send(전송)
    stage = "connect"
    try:
        with smtplib.SMTP_SSL(host, port, timeout=SMTP_TIMEOUT_SEC) as smtp:
            stage = "login"
            smtp.login(smtp_user, smtp_password)
            stage = "send"
            # 봉투 발신자는 로그인 계정 — 반송 메일은 SMTP_USER 로 돌아간다.
            # 받는 사람에게 보이는 발신자는 헤더 From(MAIL_FROM).
            refused = smtp.send_message(msg, from_addr=smtp_user, to_addrs=to)
    except smtplib.SMTPAuthenticationError as e:
        log.error("SMTP 로그인 실패 %s %s — SMTP 사용 설정·외부 앱 비밀번호 확인", e.smtp_code, _server_text(e.smtp_error))
        return _reply(502, ok=False, error="smtp_auth_failed", smtp_code=e.smtp_code,
                      smtp_message=_server_text(e.smtp_error))
    except smtplib.SMTPSenderRefused as e:
        log.error("발신자 거부 %s %s — SMTP_USER 에 MAIL_FROM 발신 권한이 있는지 확인", e.smtp_code, _server_text(e.smtp_error))
        return _reply(502, ok=False, error="smtp_sender_refused", smtp_code=e.smtp_code,
                      smtp_message=_server_text(e.smtp_error))
    except smtplib.SMTPRecipientsRefused:
        log.error("수신자 전원 거부")
        return _reply(502, ok=False, error="smtp_recipients_refused")
    except smtplib.SMTPResponseException as e:
        # 전송(DATA) 단계 거부 등 — 서버 응답 문구가 원인 파악의 핵심이라 그대로 돌려준다(비밀값 없음)
        log.error("SMTP 응답 오류 stage=%s %s %s %s", stage, type(e).__name__, e.smtp_code, _server_text(e.smtp_error))
        return _reply(502, ok=False, error="smtp_failed", stage=stage, detail=type(e).__name__,
                      smtp_code=e.smtp_code, smtp_message=_server_text(e.smtp_error))
    except (smtplib.SMTPException, OSError) as e:
        log.error("SMTP 발송 실패 stage=%s %s %s", stage, type(e).__name__, str(e)[:200])
        return _reply(502, ok=False, error="smtp_failed", stage=stage, detail=type(e).__name__,
                      message=str(e)[:200])

    if refused:
        log.warning("일부 수신자 거부 %d건", len(refused))
    log.info("발송 완료 — 수신 %d건, 거부 %d건", len(to) - len(refused), len(refused))
    return _reply(200, ok=True, message_id=msg["Message-ID"], refused=len(refused))
