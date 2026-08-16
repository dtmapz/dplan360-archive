# QNA 크롤러

내부 플랫폼 문의글(QNA) 데이터를 자동으로 크롤링하여 Google Sheets에 누적합니다.

## 개요

- **대상:** `http://works.dplan360.emato.net/page/qnaDetail.php?id=...`
- **저장:** Google Sheets (시트 ID는 `QNA_SHEET_ID` secret 참조, 탭 gid `1776222090`)
- **로그인:** ID/PW 기반 세션 쿠키
- **모드:**
  - **백필:** 초기 실행 (ID 1~2088 전체)
  - **증분:** 매일 새벽 5시 KST (마지막 ID 이후 신규 문의글만)

## 수집 데이터

| 컬럼 | 설명 |
|------|------|
| 문의글ID | 문의글 번호 |
| 제목 | 문의글 제목 |
| 내용 | 문의글 본문 |
| 등록자 | 작성자명 |
| 등록일시 | 작성 날짜시간 (예: 2026.08.07 17:51) |
| 상태 | 상태 (예: 답변완료, 처리중) |
| 댓글수 | 댓글 개수 |
| 댓글_JSON | 댓글 배열 (JSON) |
| 수집일시 | 크롤링 수집 시간 |

### 댓글_JSON 형식

```json
[
  {
    "writer": "이혜영",
    "date": "2026.08.07 17:57",
    "text": "안녕하세요..."
  }
]
```

## 실행 방법

### 1. 로컬 실행

```bash
cd crawlers/qna
pip install -r requirements.txt

export QNA_LOGIN_ID="your_id"
export QNA_LOGIN_PW="your_password"
export GCP_SERVICE_ACCOUNT_JSON='{"type":"service_account",...}'
export QNA_CRAWL_MODE="incremental"  # 또는 "backfill"

python qna_crawler.py
```

### 2. GitHub Actions (자동)

#### 백필 (처음 1회, 수동 트리거)
1. GitHub 레포 → **Actions** 탭
2. **QNA 크롤러 - 백필** 선택
3. **Run workflow** → Start ID / End ID 입력 (기본값: 1, 2088)
4. **Run workflow** 클릭

#### 증분 (매일 새벽 5시 자동)
- **QNA 크롤러 - 증분** 자동 실행
- 수동 실행도 가능 (workflow_dispatch)

## 환경 변수

| 변수 | 설명 | 필수 | 위치 |
|------|------|------|------|
| QNA_LOGIN_ID | 로그인 ID | ✅ | GitHub Secrets |
| QNA_LOGIN_PW | 로그인 비밀번호 | ✅ | GitHub Secrets |
| GCP_SERVICE_ACCOUNT_JSON | GCP 서비스 계정 JSON (Base64) | ✅ | GitHub Secrets |
| QNA_SHEET_ID | 구글 시트 ID | ⭕ | 워크플로우에 hard-coded |
| QNA_SHEET_GID | 시트 탭 GID | ⭕ | 워크플로우에 hard-coded |
| QNA_CRAWL_MODE | 크롤링 모드 (backfill/incremental) | ⭕ | 워크플로우에서 지정 |

## GitHub Secrets 설정

```bash
# GitHub CLI 사용 (권장)
gh secret set QNA_LOGIN_ID -b "your_id"
gh secret set QNA_LOGIN_PW -b "your_password"
gh secret set GCP_SERVICE_ACCOUNT_JSON -b @/path/to/service-account-key.json
```

또는 GitHub 웹 UI:
1. Settings → Secrets and variables → Actions
2. "New repository secret" → 각 항목 추가

## 보안

- ⚠️ id/pw는 GitHub Secrets에만 저장 (코드에 하드코딩 금지)
- ⚠️ 로그 출력에서 민감 정보 차단 (시크릿 마스킹)
- 서비스 계정: 기존 광고 리포트 자동화와 동일 (`dplan360-report-download@...`)

## 트러블슈팅

### 로그인 실패
- ID/PW 확인
- 계정이 활성화되어 있는지 확인

### Google Sheets 접근 불가
- 서비스 계정이 시트 편집 권한 있는지 확인
- GCP_SERVICE_ACCOUNT_JSON 형식 확인 (Base64 인코딩)

### 크롤링 느림
- 각 요청 간 1초 대기 (서버 부하 회피)
- 전체 2088개 크롤링 시 약 30~40분 소요

### 댓글이 안 나옴
- HTML 파싱 셀렉터 변경 확인 (`div.item.bg-white`)
- 사이트 구조 변경 시 유지보수 필요

## 향후 개선

- [ ] 로그 저장 (Supabase 또는 시트)
- [ ] 실패한 ID 재시도 로직
- [ ] 태그/카테고리 추출
- [ ] 이미지 다운로드 (선택)

## 라이선스

내부 사용 전용
