"""SP봇 시트 CRUD — spbot_docs, spbot_categories 탭 접근."""
import streamlit as st
from datetime import date
from utils.sheets import _get_sheet


# ======================================================================
# spbot_categories 탭
# ======================================================================

@st.cache_data(ttl=300)
def get_all_categories() -> list[dict]:
    """모든 카테고리 조회. status='승인'인 것만 답변 필터로 사용."""
    ws = _get_sheet("spbot_categories")
    rows = ws.get_all_records()
    result = []
    for i, r in enumerate(rows):
        name = str(r.get("카테고리명", "")).strip()
        if not name:
            continue
        r["_row"] = i + 2
        r["카테고리명"] = name
        r["상태"] = str(r.get("상태", "")).strip() or "대기"
        r["등록일"] = str(r.get("등록일", "")).strip()
        result.append(r)
    return result


def get_approved_category_names() -> list[str]:
    return [c["카테고리명"] for c in get_all_categories() if c["상태"] == "승인"]


def get_pending_category_names() -> list[str]:
    return [c["카테고리명"] for c in get_all_categories() if c["상태"] == "대기"]


def add_category_if_new(name: str, initial_status: str = "대기") -> None:
    """이미 있으면 skip, 없으면 추가."""
    name = (name or "").strip()
    if not name:
        return
    existing = {c["카테고리명"] for c in get_all_categories()}
    if name in existing:
        return
    ws = _get_sheet("spbot_categories")
    ws.append_row([name, initial_status, date.today().isoformat()],
                  value_input_option="USER_ENTERED")
    get_all_categories.clear()


def set_category_status(name: str, status: str) -> None:
    """상태 변경 (승인/대기/반려)."""
    for c in get_all_categories():
        if c["카테고리명"] == name:
            ws = _get_sheet("spbot_categories")
            ws.update(
                values=[[status]],
                range_name=f"B{c['_row']}",
                value_input_option="USER_ENTERED",
            )
            get_all_categories.clear()
            return


# ======================================================================
# spbot_docs 탭
# ======================================================================

DOC_HEADERS = [
    "문서ID", "제목", "요약", "카테고리", "키워드", "본문",
    "출처채널", "원본링크", "상태", "등록일", "최종수정일",
]


@st.cache_data(ttl=300)
def get_all_docs() -> list[dict]:
    """전체 문서 조회."""
    ws = _get_sheet("spbot_docs")
    rows = ws.get_all_records()
    result = []
    for i, r in enumerate(rows):
        if not r.get("문서ID"):
            continue
        r["_row"] = i + 2
        result.append(r)
    return result


def get_doc_by_source_link(source_link: str) -> dict | None:
    """원본링크로 조회 (중복 확인용)."""
    link = (source_link or "").strip()
    if not link:
        return None
    for d in get_all_docs():
        if str(d.get("원본링크", "")).strip() == link:
            return d
    return None


def _next_doc_id() -> str:
    """DOC-NNNN 형식으로 다음 ID 생성."""
    max_num = 0
    for d in get_all_docs():
        did = str(d.get("문서ID", ""))
        parts = did.split("-")
        if len(parts) == 2 and parts[0] == "DOC":
            try:
                max_num = max(max_num, int(parts[1]))
            except ValueError:
                pass
    return f"DOC-{max_num + 1:04d}"


def create_doc(
    title: str,
    summary: str,
    category: str,
    keywords: str,
    body: str,
    source_channel: str,
    source_link: str,
    status: str = "활성",
) -> str:
    """신규 문서 등록. 문서ID 반환."""
    doc_id = _next_doc_id()
    today = date.today().isoformat()
    row_data = [
        doc_id,
        (title or "")[:500],
        (summary or "")[:1000],
        (category or "").strip(),
        (keywords or "").strip(),
        (body or "")[:49000],  # 시트 셀 5만자 제한 여유
        source_channel or "",
        source_link or "",
        status or "활성",
        today,
        today,
    ]
    ws = _get_sheet("spbot_docs")
    ws.append_row(row_data, value_input_option="USER_ENTERED")
    get_all_docs.clear()
    return doc_id


def update_doc(
    row_num: int,
    title: str,
    summary: str,
    category: str,
    keywords: str,
    body: str,
    status: str = "활성",
) -> None:
    """기존 문서 갱신 (원본이 바뀐 경우). 최종수정일 자동 갱신."""
    ws = _get_sheet("spbot_docs")
    existing_id = ws.cell(row_num, 1).value or ""
    existing_source_ch = ws.cell(row_num, 7).value or ""
    existing_source_lnk = ws.cell(row_num, 8).value or ""
    existing_created = ws.cell(row_num, 10).value or date.today().isoformat()
    today = date.today().isoformat()
    row_data = [
        existing_id,
        (title or "")[:500],
        (summary or "")[:1000],
        (category or "").strip(),
        (keywords or "").strip(),
        (body or "")[:49000],
        existing_source_ch,
        existing_source_lnk,
        status or "활성",
        existing_created,
        today,
    ]
    ws.update(
        values=[row_data],
        range_name=f"A{row_num}:K{row_num}",
        value_input_option="USER_ENTERED",
    )
    get_all_docs.clear()


def upsert_doc(
    source_channel: str,
    source_link: str,
    title: str,
    summary: str,
    category: str,
    keywords: str,
    body: str,
    status: str = "활성",
) -> tuple[str, str]:
    """source_link 기준 upsert. (문서ID, 'created' or 'updated') 반환."""
    existing = get_doc_by_source_link(source_link)
    if existing:
        update_doc(
            existing["_row"], title, summary, category, keywords, body, status,
        )
        return existing["문서ID"], "updated"
    doc_id = create_doc(
        title, summary, category, keywords, body,
        source_channel, source_link, status,
    )
    return doc_id, "created"


def delete_doc(row_num: int) -> None:
    ws = _get_sheet("spbot_docs")
    ws.delete_rows(row_num)
    get_all_docs.clear()


# ======================================================================
# QNA 게시판 시트 (크롤링된 문의글 + 댓글)
# ======================================================================

@st.cache_data(ttl=300)
def get_all_qna_docs() -> list[dict]:
    """게시판 시트에서 모든 QNA 조회."""
    try:
        from google.oauth2 import service_account
        import gspread

        # 서비스 계정으로 게시판 시트 접근 (다른 시트 ID)
        QNA_SHEET_ID = "1VSS1zHcoOiumySmzxyj-34zy3Qs7ln8Azp_TEZeKaDQ"
        creds = service_account.Credentials.from_service_account_info(
            dict(st.secrets["gcp_service_account"]),
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
        gc = gspread.authorize(creds)
        spreadsheet = gc.open_by_key(QNA_SHEET_ID)

        # gid로 워크시트 찾기
        ws = None
        for sheet in spreadsheet.worksheets():
            if sheet.id == 1776222090:
                ws = sheet
                break

        if not ws:
            import logging
            logging.warning("게시판 시트(gid=1776222090)를 찾을 수 없음")
            return []

        rows = ws.get_all_records()
        result = []
        for i, r in enumerate(rows):
            qna_id = r.get("문의글ID", "")
            if not qna_id or str(qna_id).strip() == "":
                continue
            r["_row"] = i + 2
            r["qna_id"] = str(qna_id).strip()
            result.append(r)
        return result
    except Exception as e:
        import logging
        logging.warning(f"게시판 시트 조회 실패: {e}")
        return []
