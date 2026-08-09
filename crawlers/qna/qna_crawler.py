#!/usr/bin/env python3
import os
import sys
import json
import time
import logging
import base64
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

import requests
from bs4 import BeautifulSoup
import gspread
from google.oauth2 import service_account

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

BASE_URL = "http://works.dplan360.emato.net"
LOGIN_URL = f"{BASE_URL}/_common/loginProc.php"
QNA_DETAIL_URL = f"{BASE_URL}/page/qnaDetail.php"

KST = timezone(timedelta(hours=9))


class QNACrawler:
    def __init__(self, login_id: str, login_pw: str, gsheet_creds_json: str, sheet_id: str, gid: int):
        self.login_id = login_id
        self.login_pw = login_pw
        self.sheet_id = sheet_id
        self.gid = gid
        self.session = requests.Session()
        self.session.timeout = 30

        # Google Sheets 인증
        # Base64 디코딩 (GitHub Secrets에 Base64로 저장된 경우)
        try:
            creds_dict = json.loads(gsheet_creds_json)
        except json.JSONDecodeError:
            # Base64 인코딩된 경우 디코딩
            decoded = base64.b64decode(gsheet_creds_json).decode('utf-8')
            creds_dict = json.loads(decoded)
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=scopes)
        self.gc = gspread.authorize(creds)
        self.worksheet = None

    def login(self) -> bool:
        """로그인 처리"""
        try:
            logger.info("로그인 시도...")
            payload = {
                "action": "login",
                "userID": self.login_id,
                "userPW": self.login_pw,
                "isRemember": "Y"
            }
            resp = self.session.post(LOGIN_URL, data=payload, timeout=30)

            if resp.status_code == 200:
                logger.info("로그인 성공")
                return True
            else:
                logger.error(f"로그인 실패: {resp.status_code}")
                return False
        except Exception as e:
            logger.error(f"로그인 중 오류: {e}")
            return False

    def fetch_qna(self, qna_id: int) -> Optional[Dict[str, Any]]:
        """문의글 크롤링"""
        try:
            url = f"{QNA_DETAIL_URL}?id={qna_id}"
            resp = self.session.get(url, timeout=30)

            if resp.status_code != 200:
                return None

            soup = BeautifulSoup(resp.text, 'html.parser')

            # 메인 컨테이너 확인
            base_container = soup.select_one("div.baseViewContainer")
            if not base_container:
                return None

            board_detail = base_container.select_one("div.container.boardDetail")
            if not board_detail:
                return None

            # 제목
            title_elem = board_detail.select_one("div.mb-3.ps-3.row.bold.fs-4")
            title = title_elem.get_text(strip=True) if title_elem else ""

            # 내용
            content_elem = board_detail.select_one("div.ck-content")
            content = content_elem.get_text(strip=True) if content_elem else ""

            # 메타 정보 (등록자, 등록일시, 상태)
            meta_container = board_detail.select("div.col-sm-4.row, div.col-sm-8.row")
            author = ""
            created_date = ""
            status = ""

            for container in meta_container:
                labels = container.select("label.col-sm-4.text-end.bold.fs-6")
                values = container.select("div.col-sm-8.fs-6, div.col-sm-10.fs-6")

                for label, value in zip(labels, values):
                    label_text = label.get_text(strip=True)
                    value_text = value.get_text(strip=True)

                    if label_text == "등록자":
                        author = value_text
                    elif label_text == "등록일시":
                        created_date = value_text
                    elif label_text == "상태":
                        status_badge = value.select_one("span.badge")
                        if status_badge:
                            status = status_badge.get_text(strip=True)

            # 댓글 크롤링
            comments = []
            comment_list = base_container.select_one("div.container.commentList")
            if comment_list:
                comment_items = comment_list.select("div.item.bg-white")
                for idx, item in enumerate(comment_items, 1):
                    writer_elem = item.select_one("span.writer")
                    date_elem = item.select_one("span.date")
                    body_elem = item.select_one("div.item-body")

                    if writer_elem and date_elem and body_elem:
                        writer = writer_elem.get_text(strip=True)
                        date = date_elem.get_text(strip=True)
                        text = body_elem.get_text(strip=True)

                        comments.append({
                            "writer": writer,
                            "date": date,
                            "text": text
                        })

            result = {
                "id": qna_id,
                "title": title,
                "content": content,
                "author": author,
                "created_date": created_date,
                "status": status,
                "comment_count": len(comments),
                "comments_json": json.dumps(comments, ensure_ascii=False),
                "collected_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
            }

            logger.info(f"ID {qna_id}: '{title[:30]}...' 크롤링 완료 (댓글 {len(comments)}개)")
            return result

        except Exception as e:
            logger.error(f"ID {qna_id} 크롤링 중 오류: {e}")
            return None

    def init_worksheet(self):
        """워크시트 초기화 및 헤더 설정"""
        try:
            spreadsheet = self.gc.open_by_key(self.sheet_id)

            # gid로 워크시트 찾기
            for ws in spreadsheet.worksheets():
                if ws.id == self.gid:
                    self.worksheet = ws
                    break

            if not self.worksheet:
                raise ValueError(f"GID {self.gid}인 워크시트를 찾을 수 없음")

            # 헤더 확인 및 설정
            headers = [
                "문의글ID",
                "제목",
                "내용",
                "등록자",
                "등록일시",
                "상태",
                "댓글수",
                "댓글_JSON",
                "수집일시"
            ]

            first_row = self.worksheet.row_values(1)
            if not first_row or first_row != headers:
                self.worksheet.insert_row(headers, index=1)
                logger.info("헤더 행 추가됨")

        except Exception as e:
            logger.error(f"워크시트 초기화 중 오류: {e}")
            raise

    def get_last_crawled_id(self) -> int:
        """마지막 크롤링한 id 조회 (기본값: 6, ID 7부터 시작)"""
        try:
            # 마지막 행 찾기 (ID 컬럼이 비어있지 않은 마지막 행)
            all_values = self.worksheet.get_all_values()

            if len(all_values) <= 1:  # 헤더만 있는 경우
                return 6  # ID 7부터 크롤링 시작 (ID 1~6은 테스트 게시물)

            for row in reversed(all_values[1:]):  # 헤더 제외
                if row and row[0].isdigit():
                    return int(row[0])

            return 6  # 데이터 없으면 기본값 6
        except Exception as e:
            logger.error(f"마지막 id 조회 중 오류: {e}")
            return 6

    def save_qna(self, qna_data: Dict[str, Any]):
        """문의글 데이터 시트에 저장"""
        try:
            row = [
                str(qna_data["id"]),
                qna_data["title"],
                qna_data["content"],
                qna_data["author"],
                qna_data["created_date"],
                qna_data["status"],
                str(qna_data["comment_count"]),
                qna_data["comments_json"],
                qna_data["collected_at"]
            ]
            self.worksheet.append_row(row, value_input_option="USER_ENTERED")
            time.sleep(0.5)  # API rate limit 회피
        except Exception as e:
            logger.error(f"ID {qna_data['id']} 저장 중 오류: {e}")

    def crawl_backfill(self, start_id: int = 1, end_id: int = 2088):
        """백필: 전체 문의글 크롤링 (첫 실행)"""
        logger.info(f"백필 모드: ID {start_id}~{end_id} 크롤링 시작")

        for qna_id in range(start_id, end_id + 1):
            qna_data = self.fetch_qna(qna_id)

            if qna_data:
                self.save_qna(qna_data)
            else:
                logger.debug(f"ID {qna_id}: 데이터 없음 (스킵)")

            # 서버 부하 회피
            time.sleep(1)

        logger.info("백필 크롤링 완료")

    def crawl_incremental(self):
        """증분: 마지막 이후 신규 문의글 크롤링"""
        last_id = self.get_last_crawled_id()
        logger.info(f"증분 모드: 마지막 크롤링 ID = {last_id}, {last_id + 1}부터 시작")

        # 최대 200개까지만 시도 (일일 신규 상한 추정)
        max_attempts = 200
        consecutive_empty = 0

        for offset in range(max_attempts):
            qna_id = last_id + 1 + offset
            qna_data = self.fetch_qna(qna_id)

            if qna_data:
                self.save_qna(qna_data)
                consecutive_empty = 0
            else:
                consecutive_empty += 1
                # 연속 10개 스킵하면 종료
                if consecutive_empty >= 10:
                    logger.info(f"연속 {consecutive_empty}개 스킵 → 크롤링 종료")
                    break

            time.sleep(1)

        logger.info("증분 크롤링 완료")


def main():
    # 환경 변수 로드
    login_id = os.getenv("QNA_LOGIN_ID")
    login_pw = os.getenv("QNA_LOGIN_PW")
    gsheet_creds_json = os.getenv("QNA_GCP_SERVICE_ACCOUNT_JSON")
    sheet_id = os.getenv("QNA_SHEET_ID", "1VSS1zHcoOiumySmzxyj-34zy3Qs7ln8Azp_TEZeKaDQ")
    gid = int(os.getenv("QNA_SHEET_GID", "1776222090"))
    mode = os.getenv("QNA_CRAWL_MODE", "incremental").lower()  # backfill or incremental

    if not login_id or not login_pw or not gsheet_creds_json:
        logger.error("필수 환경 변수 누락: QNA_LOGIN_ID, QNA_LOGIN_PW, GCP_SERVICE_ACCOUNT_JSON")
        sys.exit(1)

    try:
        crawler = QNACrawler(login_id, login_pw, gsheet_creds_json, sheet_id, gid)

        # 로그인
        if not crawler.login():
            logger.error("로그인 실패")
            sys.exit(1)

        # 워크시트 초기화
        crawler.init_worksheet()

        # 크롤링 모드 선택
        if mode == "backfill":
            crawler.crawl_backfill()
        else:
            crawler.crawl_incremental()

        logger.info("크롤링 완료")

    except Exception as e:
        logger.error(f"크롤러 실행 중 오류: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
