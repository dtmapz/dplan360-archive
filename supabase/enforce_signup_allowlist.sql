-- ============================================================
-- 회원가입 서버측 게이트 (Supabase Auth)
-- 목적: 앱 우회(직접 REST/스크립트 signup) 시에도 아래 두 조건을 강제
--   1) 이메일 도메인이 @d-plan360.com
--   2) 사전 승인 이메일 화이트리스트(auth.allowed_signup_emails)에 존재
--
-- 조직도 원본은 Google Sheets 이므로, Sheets → Supabase 로 이메일 화이트리스트를
-- 주기 동기화하는 방식으로 운영. (동기화 방법은 파일 하단 [SYNC] 섹션 참고)
--
-- Supabase Dashboard → SQL Editor 에서 1회 실행.
-- ============================================================

-- 1) 화이트리스트 테이블
create table if not exists public.allowed_signup_emails (
  email text primary key,
  updated_at timestamptz not null default now()
);

-- RLS: 서비스 롤만 쓰기, 인증 사용자 읽기 가능
alter table public.allowed_signup_emails enable row level security;

drop policy if exists "allowed_signup_emails_read_authenticated"
  on public.allowed_signup_emails;
create policy "allowed_signup_emails_read_authenticated"
  on public.allowed_signup_emails
  for select
  to authenticated
  using (true);

-- 서비스 롤(anon 아님)로 upsert/delete 하도록 별도 policy 두지 않음
-- (service_role 은 RLS 우회)


-- 2) BEFORE INSERT 트리거 — 도메인 + 화이트리스트 검증
create or replace function public.enforce_signup_allowlist()
returns trigger
language plpgsql
security definer
set search_path = public, auth
as $$
declare
  v_email text := lower(coalesce(new.email, ''));
begin
  if v_email = '' then
    raise exception 'Email is required';
  end if;

  if v_email not like '%@d-plan360.com' then
    raise exception 'Only @d-plan360.com email is allowed'
      using errcode = '22023';
  end if;

  if not exists (
    select 1 from public.allowed_signup_emails
    where email = v_email
  ) then
    raise exception 'This email is not on the organization allowlist. Contact admin.'
      using errcode = '22023';
  end if;

  return new;
end;
$$;

drop trigger if exists enforce_signup_allowlist_trigger on auth.users;
create trigger enforce_signup_allowlist_trigger
  before insert on auth.users
  for each row
  execute function public.enforce_signup_allowlist();


-- ============================================================
-- [SYNC] Google Sheets → Supabase 화이트리스트 동기화
-- ============================================================
-- 방법 A: Streamlit 관리자 페이지에서 "동기화" 버튼
--   조직도 시트에서 활성 이메일 전부 읽어 upsert.
--   utils.sheets.get_all_org_members_sheet() 결과를 아래 형태로 upsert:
--
--     from utils.db import get_client
--     sb = get_client()
--     members = get_all_org_members_sheet()
--     rows = [{"email": m["email"]} for m in members]
--     sb.table("allowed_signup_emails").upsert(rows).execute()
--     # 삭제된 사용자는 별도 diff 후 delete 처리
--
-- 방법 B: GitHub Actions (일 1회)
--   crawlers/ 폴더에 sync_org_allowlist.py 신설 후 workflow 스케줄.
--
-- 방법 C: Google Apps Script (조직도 시트 편집 트리거)
--   onEdit 트리거로 Supabase REST(service_role) upsert 호출.
--
-- 최소 안전선: 초기 부트스트랩만 1회 수동 upsert 해두면
-- 트리거가 방어 역할 시작. 자동 동기화는 이후에 붙여도 됨.
-- ============================================================
