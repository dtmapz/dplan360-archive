# D-PLAN360 Archive

사내 매체 정보 아카이브 (Streamlit + Supabase)

## 폴더 구조
```
streamlit_app.py        # 진입점
pages/1_HOME.py          # 검색 + 신규 매체 등록
pages/2_마일스톤.py        # 카테고리별 매체 현황 (01~04 전체노출 / 05 접기·펼치기)
utils/db.py              # Supabase 쿼리 함수 모음
utils/ui.py              # 공통 스타일 + 카드그리드 + 상세/수정 dialog
.streamlit/config.toml   # 테마 색상 (Midnight Executive)
.streamlit/secrets.toml.example  # secrets 작성 예시 (실제 키는 절대 커밋 금지)
```

## 로컬 실행
```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # 값 채워넣기
streamlit run streamlit_app.py
```

## Streamlit Cloud 배포
1. 이 폴더를 GitHub repo로 push (secrets.toml은 .gitignore 처리)
2. share.streamlit.io에서 repo 연결, main file은 `streamlit_app.py`
3. App settings > Secrets에 SUPABASE_URL, SUPABASE_KEY 입력

## 운영 / 인수인계 메모
- Supabase 무료 프로젝트는 7일간 미접속 시 자동 일시정지 → 정지 시 Supabase 대시보드에서 수동 Restore
- 백업: 분기 1회 `supabase db dump` 또는 Table Editor에서 CSV export 권장
- 수정 권한은 별도 로그인 없이 전체 팀원 오픈 (마일스톤 상세 팝업 [수정] 버튼)
- 신규 대분류/중분류는 신규 등록 폼 또는 수정 폼의 "+ 새 카테고리 추가" 옵션으로 코드 수정 없이 추가 가능
