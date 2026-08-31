/**
 * 캘린더 행사 참석 안내 메일 자동 발송 — Apps Script
 *
 * 대상: events 탭에서 requires_check=TRUE인 행사
 *   1) 행사 24시간 전 → 참석 안내 메일
 *   2) 행사 30분 전   → 참석 리마인드 메일
 *
 * 설정 방법:
 * 1. PROMOTION_SHEET_ID 스프레드시트 열기 (events/attendance/event_categories 탭이 있는 시트)
 * 2. 확장 프로그램 > Apps Script
 * 3. 이 코드 붙여넣기 → 저장
 * 4. 프로젝트 설정(⚙️) > 시간대를 "Asia/Seoul (GMT+09:00)"로 설정
 *    (일시 계산이 KST 기준이어야 정확함)
 * 5. 프로젝트 설정 > 스크립트 속성에 등록
 *    SHEET_ID     = PROMOTION_SHEET_ID 값 (하드코딩 금지 — Public repo 원칙)
 *    NOTIFY_EMAIL = all@d-plan360.com  (미설정 시 기본값으로 대체)
 * 6. events 탭 헤더에 컬럼 2개 추가 (K1, L1) — 없으면 최초 실행 시 자동 생성됨
 *    reminder_24h_sent | reminder_30m_sent
 *    ⚠️ 기존 A~J 컬럼 순서/내용은 절대 건드리지 말 것 (Python 쪽 utils/sheets.py가
 *    A~J 범위만 갱신하므로 K/L 컬럼은 이 스크립트 전용으로 안전하게 분리됨)
 * 7. 트리거 추가: runEventReminders → 시간 기반 → 분 단위 타이머 → 10분마다
 */

var _PROPS = PropertiesService.getScriptProperties();
var SHEET_ID = _PROPS.getProperty("SHEET_ID");
var NOTIFY_EMAIL = _PROPS.getProperty("NOTIFY_EMAIL") || "all@d-plan360.com";
var EVENTS_TAB = "events";
var CALENDAR_URL = "https://dplan360-media.streamlit.app/EventCalendar";

var COL_24H = "reminder_24h_sent";
var COL_30M = "reminder_30m_sent";

// 10분 간격 트리거 기준 안전 마진 (±10분)
var WINDOW_24H_MIN = 24 * 60 - 10; // 1430
var WINDOW_24H_MAX = 24 * 60 + 10; // 1450
var WINDOW_30M_MIN = 20;
var WINDOW_30M_MAX = 40;

function runEventReminders() {
  if (!SHEET_ID) throw new Error("스크립트 속성 SHEET_ID 미설정");
  var ss = SpreadsheetApp.openById(SHEET_ID);
  var ws = ss.getSheetByName(EVENTS_TAB);
  if (!ws) return;

  var headerRow = ws.getRange(1, 1, 1, ws.getLastColumn()).getValues()[0];
  var colIdx = _ensureReminderColumns(ws, headerRow);

  var data = ws.getDataRange().getValues();
  var now = new Date();

  for (var i = 1; i < data.length; i++) {
    var row = data[i];
    var rowNum = i + 1;

    if (!_isTrue(row[colIdx.requires_check])) continue;
    if (!row[colIdx.id]) continue;

    var eventDt = _parseEventDateTime(row[colIdx.event_date], row[colIdx.start_time]);
    if (!eventDt) continue;

    var diffMin = (eventDt.getTime() - now.getTime()) / 60000;

    if (diffMin >= WINDOW_24H_MIN && diffMin <= WINDOW_24H_MAX
        && !_isTrue(row[colIdx.reminder_24h_sent])) {
      _sendReminder("24h", row, colIdx, eventDt);
      ws.getRange(rowNum, colIdx.reminder_24h_sent + 1).setValue("TRUE");
    }

    if (diffMin >= WINDOW_30M_MIN && diffMin <= WINDOW_30M_MAX
        && !_isTrue(row[colIdx.reminder_30m_sent])) {
      _sendReminder("30m", row, colIdx, eventDt);
      ws.getRange(rowNum, colIdx.reminder_30m_sent + 1).setValue("TRUE");
    }
  }
}

function _ensureReminderColumns(ws, headerRow) {
  var idx = {
    id: headerRow.indexOf("id"),
    title: headerRow.indexOf("title"),
    event_date: headerRow.indexOf("event_date"),
    start_time: headerRow.indexOf("start_time"),
    end_time: headerRow.indexOf("end_time"),
    category: headerRow.indexOf("category"),
    venue: headerRow.indexOf("venue"),
    memo: headerRow.indexOf("memo"),
    requires_check: headerRow.indexOf("requires_check"),
  };

  var col24 = headerRow.indexOf(COL_24H);
  var col30 = headerRow.indexOf(COL_30M);
  var lastCol = ws.getLastColumn();

  if (col24 === -1) {
    lastCol += 1;
    ws.getRange(1, lastCol).setValue(COL_24H);
    col24 = lastCol - 1;
  }
  if (col30 === -1) {
    lastCol += 1;
    ws.getRange(1, lastCol).setValue(COL_30M);
    col30 = lastCol - 1;
  }

  idx.reminder_24h_sent = col24;
  idx.reminder_30m_sent = col30;
  return idx;
}

function _isTrue(v) {
  return v === true || String(v).trim().toUpperCase() === "TRUE";
}

function _parseEventDateTime(dateVal, timeVal) {
  var dateStr = dateVal instanceof Date
    ? Utilities.formatDate(dateVal, "Asia/Seoul", "yyyy-MM-dd")
    : String(dateVal).trim();
  var timeStr = timeVal instanceof Date
    ? Utilities.formatDate(timeVal, "Asia/Seoul", "HH:mm:ss")
    : String(timeVal).trim();

  var dParts = dateStr.split("-");
  var tParts = timeStr.split(":");
  if (dParts.length < 3 || tParts.length < 2) return null;

  return new Date(
    parseInt(dParts[0], 10), parseInt(dParts[1], 10) - 1, parseInt(dParts[2], 10),
    parseInt(tParts[0], 10), parseInt(tParts[1], 10), 0
  );
}

function _sendReminder(type, row, colIdx, eventDt) {
  var title = row[colIdx.title];
  var category = row[colIdx.category];
  var venue = row[colIdx.venue];
  var memo = row[colIdx.memo];
  var startTime = _fmtHHmm(row[colIdx.start_time]);
  var endTime = _fmtHHmm(row[colIdx.end_time]);
  var weekdays = ["일", "월", "화", "수", "목", "금", "토"];
  var dateOnlyLabel = Utilities.formatDate(eventDt, "Asia/Seoul", "M월 d일");

  var subject = type === "24h"
    ? "[SP] " + title + " 안내 - " + dateOnlyLabel + " " + startTime + " @ " + venue
    : "[SP] " + title + " - " + startTime + " " + venue + " 참석 안내";

  var greeting = type === "24h"
    ? "안녕하세요, SP팀입니다.<br>내일 예정된 행사 정보를 안내드리오니 많은 참여 부탁드립니다."
    : "안녕하세요, SP팀입니다.<br>30분 후 " + title + " 시작 예정에 있어, 많은 참여 부탁드립니다.";

  var factRows = type === "24h"
    ? [["일시", Utilities.formatDate(eventDt, "Asia/Seoul", "yyyy-MM-dd") + " (" + weekdays[eventDt.getDay()] + ") " + startTime + " ~ " + endTime], ["장소", venue]]
    : [["시간", startTime + " ~ " + endTime], ["장소", venue]];
  if (memo) factRows.push(["메모", memo]);

  var ctaLabel = type === "24h" ? "디플랜360 캘린더에서 체크하기 →" : "참석 여부 체크하러 가기 →";
  var footerText = type === "24h"
    ? "이 메일은 참석 설정된 행사에 대해 자동 발송됩니다."
    : "교육 참석 후 캘린더에서 참석 여부를 체크해 주세요.";

  var html = _renderReminderHtml(type, {
    greeting: greeting,
    title: title,
    category: category,
    factRows: factRows,
    ctaLabel: ctaLabel,
    footerText: footerText,
  });

  GmailApp.sendEmail(NOTIFY_EMAIL, subject, "", {htmlBody: html});
  Logger.log("[" + type + "] 발송: " + title + " → " + NOTIFY_EMAIL);
}

// 승인된 시안(24h=차분한 블랙 톤 / 30m=긴급 앰버 톤) 그대로 인라인 스타일로 반영.
// 이메일 클라이언트는 <style> 블록을 신뢰할 수 없어 전부 인라인으로 작성.
function _renderReminderHtml(type, data) {
  var urgent = type === "30m";
  var stripBg = urgent
    ? "background:linear-gradient(90deg,#F2A93B,#E8971C);"
    : "background:#0B0B0B;";
  var badgeLabel = urgent ? "⏰ 곧 시작" : "행사 안내";
  var badgeStyle = urgent
    ? "background:#FFF1D6;color:#8A5A0A;"
    : "background:#F1F0EC;color:#45433C;";
  var ctaStyle = urgent
    ? "background:#F2A93B;color:#1C1200;"
    : "background:#0B0B0B;color:#ffffff;";

  var factsHtml = data.factRows.map(function(r) {
    return '<tr>'
      + '<td style="color:#96928A;font-size:13.5px;padding:4px 10px 4px 0;width:44px;vertical-align:top;white-space:nowrap;">' + r[0] + '</td>'
      + '<td style="color:#1C1B18;font-size:13.5px;padding:4px 0;">' + r[1] + '</td>'
      + '</tr>';
  }).join('');

  return ''
    + '<div style="max-width:560px;margin:0 auto;font-family:Pretendard,-apple-system,\'Apple SD Gothic Neo\',\'Malgun Gothic\',sans-serif;">'
    + '<div style="height:5px;border-radius:10px 10px 0 0;' + stripBg + '"></div>'
    + '<div style="border:1px solid #E7E4DC;border-top:none;border-radius:0 0 10px 10px;padding:28px 30px 30px;background:#ffffff;">'

    + '<p style="margin:0 0 18px;font-size:14px;line-height:1.7;color:#1C1B18;">' + data.greeting + '</p>'

    + '<div style="margin:0 0 18px;">'
    + '<span style="display:inline-block;font-size:12px;font-weight:700;letter-spacing:0.02em;padding:5px 11px;border-radius:100px;' + badgeStyle + '">' + badgeLabel + '</span>'
    + '</div>'

    + '<div style="background:#FBFAF7;border:1px solid #ECE9E0;border-radius:12px;padding:18px 20px;margin:0 0 20px;">'
    + '<div style="margin:0 0 14px;">'
    + '<span style="font-size:16px;font-weight:700;color:#0B0B0B;">' + data.title + '</span>'
    + '<span style="font-size:11px;font-weight:600;padding:3px 9px;border-radius:4px;background:#0B0B0B;color:#ffffff;margin-left:8px;">' + data.category + '</span>'
    + '</div>'
    + '<table style="width:100%;border-collapse:collapse;">' + factsHtml + '</table>'
    + '</div>'

    + '<div style="text-align:center;margin:24px 0 20px;">'
    + '<a href="' + CALENDAR_URL + '" style="display:inline-block;padding:12px 26px;border-radius:8px;font-size:14px;font-weight:700;text-decoration:none;' + ctaStyle + '">' + data.ctaLabel + '</a>'
    + '</div>'

    + '<p style="margin:22px 0 0;color:#6B6862;font-size:13px;">감사합니다.</p>'

    + '<div style="margin-top:18px;padding-top:14px;border-top:1px solid #EFEDE6;font-size:11px;color:#A7A398;">' + data.footerText + '</div>'
    + '</div>'
    + '</div>';
}

function _fmtHHmm(v) {
  if (v instanceof Date) return Utilities.formatDate(v, "Asia/Seoul", "HH:mm");
  // Sheets 시간 서식이 앞자리 0을 없애는 경우 보정 (예: "3:00" → "03:00")
  var parts = String(v).trim().slice(0, 5).split(":");
  if (parts.length < 2) return String(v).trim();
  return (parts[0].length === 1 ? "0" + parts[0] : parts[0]) + ":" + parts[1];
}
