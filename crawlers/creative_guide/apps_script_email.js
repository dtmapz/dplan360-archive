/**
 * 제작 가이드 변경 감지 메일 발송 — Apps Script
 *
 * 설정 방법:
 * 1. BIGQUERY_MAPPING_SHEET_ID 스프레드시트 열기
 * 2. 확장 프로그램 > Apps Script
 * 3. 이 코드 붙여넣기 → 저장
 * 4. 프로젝트 설정 > 스크립트 속성에 SHEET_ID, NOTIFY_EMAIL 등록
 *    (하드코딩 금지 — 저장소가 Public이므로 코드에 시트 ID를 남기면 안 됨)
 * 5. 트리거 추가: sendCreativeGuideAlert → 시간 기반 → 매일 05:00~06:00
 */

var _PROPS = PropertiesService.getScriptProperties();
var SHEET_ID = _PROPS.getProperty("SHEET_ID");
var NOTIFY_EMAIL = _PROPS.getProperty("NOTIFY_EMAIL");   // 스크립트 속성 필수(하드코딩 금지)
var LOG_TAB = "creative_guide_log";

function sendCreativeGuideAlert() {
  if (!SHEET_ID) throw new Error("스크립트 속성 SHEET_ID 미설정");
  var ss = SpreadsheetApp.openById(SHEET_ID);
  var ws = ss.getSheetByName(LOG_TAB);
  if (!ws) return;

  var data = ws.getDataRange().getValues();
  var header = data[0];
  var colIdx = {
    date: 0, sheet: 1, tab: 2, type: 3,
    item: 4, oldVal: 5, newVal: 6, evidence: 7, tabUrl: 8, sent: 9
  };

  // 알림발송 = "N"인 행만 수집
  var pending = [];
  var pendingRows = [];
  for (var i = 1; i < data.length; i++) {
    if (data[i][colIdx.sent] === "N") {
      pending.push(data[i]);
      pendingRows.push(i + 1); // 시트 행번호 (1-based)
    }
  }

  if (pending.length === 0) return;

  // 시트>탭별 그룹핑 (URL 포함)
  var groups = {};
  var groupUrls = {};
  pending.forEach(function(row) {
    var key = row[colIdx.sheet] + " > " + row[colIdx.tab];
    if (!groups[key]) {
      groups[key] = [];
      groupUrls[key] = row[colIdx.tabUrl] || "";
    }
    groups[key].push(row);
  });

  // HTML 이메일 바디 생성
  var detectDate = pending[0][colIdx.date];
  var html = '<div style="font-family:Pretendard,Apple SD Gothic Neo,sans-serif;max-width:800px;">';
  html += '<h2 style="color:#0B0B0B;margin-bottom:4px;">📋 제작 가이드 변경 감지 리포트</h2>';
  html += '<p style="color:#666;font-size:13px;margin-top:0;">검증 일시: ' + detectDate + ' KST &nbsp;|&nbsp; 감지 건수: <b>' + pending.length + '건</b></p>';
  html += '<hr style="border:none;border-top:1px solid #ddd;margin:16px 0;">';

  var typeEmoji = {"수치 변경": "🔢", "정보 추가": "➕", "정보 삭제": "➖"};

  for (var groupName in groups) {
    var items = groups[groupName];
    var url = groupUrls[groupName];
    var title = url
      ? '<a href="' + url + '" style="color:#0B0B0B;text-decoration:underline;">' + groupName + '</a>'
      : groupName;
    html += '<h3 style="font-size:15px;margin:20px 0 8px;">' + title + ' (' + items.length + '건)</h3>';
    html += '<table style="border-collapse:collapse;width:100%;font-size:13px;">';
    html += '<tr style="background:#f5f5f5;">';
    html += '<th style="padding:8px 10px;border:1px solid #ddd;text-align:left;width:90px;">유형</th>';
    html += '<th style="padding:8px 10px;border:1px solid #ddd;text-align:left;">항목</th>';
    html += '<th style="padding:8px 10px;border:1px solid #ddd;text-align:left;">기존값 (시트)</th>';
    html += '<th style="padding:8px 10px;border:1px solid #ddd;text-align:left;">변경값 (웹)</th>';
    html += '</tr>';

    items.forEach(function(row) {
      var emoji = typeEmoji[row[colIdx.type]] || "";
      html += '<tr>';
      html += '<td style="padding:8px 10px;border:1px solid #ddd;">' + emoji + ' ' + row[colIdx.type] + '</td>';
      html += '<td style="padding:8px 10px;border:1px solid #ddd;font-weight:600;">' + row[colIdx.item] + '</td>';
      html += '<td style="padding:8px 10px;border:1px solid #ddd;color:#999;">' + row[colIdx.oldVal] + '</td>';
      html += '<td style="padding:8px 10px;border:1px solid #ddd;color:#C62828;font-weight:600;">' + row[colIdx.newVal] + '</td>';
      html += '</tr>';
    });

    html += '</table>';
  }

  html += '<hr style="border:none;border-top:1px solid #ddd;margin:20px 0 12px;">';
  html += '<p style="font-size:11px;color:#999;">이 메일은 제작 가이드 자동 검증 시스템에서 발송되었습니다.<br>';
  html += '변경사항을 확인 후 해당 시트를 업데이트해 주세요.</p>';
  html += '</div>';

  // 메일 발송
  var subject = "[제작가이드 검증] 변경 " + pending.length + "건 감지 — " + detectDate;
  GmailApp.sendEmail(NOTIFY_EMAIL, subject, "", {htmlBody: html});

  // 알림발송 → "Y" 업데이트
  pendingRows.forEach(function(rowNum) {
    ws.getRange(rowNum, colIdx.sent + 1).setValue("Y");
  });

  Logger.log("메일 발송 완료: " + pending.length + "건 → " + NOTIFY_EMAIL);
}
