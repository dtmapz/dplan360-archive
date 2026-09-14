# mail_relay — 네이버웍스 SMTP 메일 중계

Apps Script 는 SMTP 로 직접 보낼 수 없다. 그래서 알림 스크립트는 **발송 시각·대상 판단만** 하고,
실제 발송은 이 Cloud Run 함수에 넘긴다.

```
Apps Script (UrlFetchApp) ──HTTPS · X-Relay-Secret──▶ send_mail (Cloud Run)
                                                         └ SMTP_SSL smtp.worksmobile.com:465
                                                           로그인: SMTP_USER (공용 구성원 계정)
                                                           From: MAIL_FROM (표시 이름 + 로그인 주소)
                                                           Reply-To: REPLY_TO (그룹 주소)
```

- 발신자(From)·로그인 계정은 **서버 환경변수로만** 정한다. 요청으로 바꿀 수 없다
- 수신자는 `ALLOWED_RECIPIENT_DOMAINS` 만 허용 — 비밀값이 새도 외부 발송 창구가 되지 않는다
- 봉투 발신자는 로그인 계정이라 **반송 메일은 SMTP_USER 로** 돌아간다
- 개인 계정에 묶이지 않도록 GCP 프로젝트·결제·네이버웍스 로그인 계정 모두 **공용/회사 소유**로 둔다

## API

`POST /` · 헤더 `X-Relay-Secret` · JSON

```json
{ "to": "team@example.com", "subject": "제목", "html": "<p>본문</p>", "text": "" }
```

| 응답 | 의미 |
|---|---|
| 200 `{"ok":true}` | 발송 완료 |
| 400 `bad_request` | 수신 도메인·제목·본문 형식 오류 (`detail` 참고) |
| 401 | 비밀값 불일치 |
| 500 `relay_not_configured` | 환경변수 누락 |
| 502 `smtp_auth_failed` | SMTP 로그인 실패 — SMTP 사용 설정·외부 앱 비밀번호 확인 |
| 502 `smtp_sender_refused` | 로그인 계정에 MAIL_FROM 발신 권한 없음 |

## 환경변수

| 이름 | 보관 | 예시 |
|---|---|---|
| `SMTP_USER` | 환경변수 | 공용 구성원 계정 주소 |
| `SMTP_PASSWORD` | **Secret Manager** | SMTP_USER 의 외부 앱 비밀번호 |
| `RELAY_SECRET` | **Secret Manager** | 임의의 긴 난수 (Apps Script `MAIL_RELAY_SECRET` 과 동일) |
| `MAIL_FROM` | 환경변수 | `SP팀 <SMTP_USER와 같은 주소>` — 표시 이름만 팀명 |
| `REPLY_TO` | 환경변수 (선택) | 그룹 주소 — 답장이 그룹으로 가게 |
| `ALLOWED_RECIPIENT_DOMAINS` | 환경변수 | 회사 도메인 |

> ⚠️ **네이버웍스 SMTP 는 로그인 계정과 다른 주소로 발신할 수 없다.** 그룹 주소를 `MAIL_FROM` 에 넣으면
> 전송 단계에서 `554 5.7.1 The sender address is unauthorized` 로 거부된다(2026-09 확인).
> 그래서 주소는 로그인 계정 그대로 두고, 표시 이름(`SP팀`)과 `REPLY_TO`(그룹 주소)로 팀 명의를 만든다.
| `SMTP_HOST` / `SMTP_PORT` | 선택 | 기본 `smtp.worksmobile.com` / `465` |

## 배포 (GCP 콘솔, 회사 계정)

1. 새 프로젝트 생성 → **결제 계정 연결**(무료 한도 내 사용이어도 필요)
2. API 사용 설정: Cloud Run Admin, Cloud Build, Artifact Registry, Secret Manager
3. Secret Manager 에 비밀 2개 생성: `mail-relay-smtp-password`, `mail-relay-secret`
4. Cloud Run → **함수 작성** → 리전 `asia-northeast3`, 런타임 Python 3.12,
   인증 **"공개 액세스 허용"**(비밀값 헤더로 보호), 진입점 `send_mail`
   - 인라인 편집기에 `main.py`, `requirements.txt` 붙여넣기
   - 변수 및 보안 비밀: 위 환경변수 등록, 비밀 2개는 "보안 비밀 참조"로 `SMTP_PASSWORD`·`RELAY_SECRET` 에 연결
   - 최대 인스턴스 1~2 (알림 용도라 충분)
5. 실행 서비스 계정에 **Secret Manager 보안 비밀 접근자** 역할 부여
6. 발급된 URL 로 테스트:
   ```bash
   curl -X POST "$URL" -H "X-Relay-Secret: $SECRET" -H "Content-Type: application/json" \
     -d '{"to":"받을주소","subject":"중계 테스트","text":"테스트"}'
   ```

> 조직 정책에 "도메인 제한 공유"가 걸려 있으면 공개 액세스 허용이 막힌다. 그 경우 알려줄 것
> (Apps Script ID 토큰 인증 방식으로 바꿔야 함).

로컬 코드 수정 시: `pip install functions-framework` 후 `functions-framework --target=send_mail`.
