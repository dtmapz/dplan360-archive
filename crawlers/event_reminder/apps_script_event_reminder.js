/**
 * 캘린더 행사 참석 안내 메일 자동 발송 — Apps Script
 *
 * 대상: events 탭에서 requires_check=TRUE인 행사
 *   1) 사전 안내  — 영업일 14:30에 "다음 영업일까지의 행사"를 한 통으로 발송
 *   2) 당일 안내  — 영업일 10:30에 "오늘 행사"를 한 통으로 발송
 *
 * 발송 원칙 (2026-09-05 개편)
 *   · 하루에 행사가 여러 건이어도 **한 통**으로 묶어 보낸다 (기존: 행사마다 1통)
 *   · 발송 시각을 고정한다. "정확히 24시간/3시간 전"이 아니어도 무방
 *   · **비영업일에는 발송하지 않는다.** 따라서 월요일 행사는 전주 금요일 14:30에 안내된다
 *   · 금요일 사전 안내는 토·일·월을 한 번에 커버한다 (주말 행사도 누락되지 않음)
 *
 * 설정 방법:
 * 1. PROMOTION_SHEET_ID 스프레드시트 열기 (events/attendance/event_categories 탭이 있는 시트)
 * 2. 확장 프로그램 > Apps Script
 * 3. 이 코드 붙여넣기 → 저장
 * 4. 프로젝트 설정(⚙️) > 시간대를 "Asia/Seoul (GMT+09:00)"로 설정
 *    (일시 계산이 KST 기준이어야 정확함)
 * 5. 프로젝트 설정 > 스크립트 속성에 등록
 *    SHEET_ID     = PROMOTION_SHEET_ID 값 (하드코딩 금지 — Public repo 원칙)
 *    NOTIFY_EMAIL = 알림 수신 이메일 (필수 — 하드코딩 금지, Public repo 원칙)
 *    HOLIDAYS     = (선택) 공휴일 보조 목록, yyyy-MM-dd 콤마 구분.
 *                   공휴일은 아래 "공휴일" 탭으로 관리하는 것이 기본이며,
 *                   이 속성은 시트를 쓸 수 없을 때의 보조 수단이다
 * 5-1. 공휴일 관리 — 같은 스프레드시트의 **"공휴일" 탭**
 *    A열 날짜(yyyy-MM-dd) | B열 명칭, 1행은 헤더
 *    담당자가 스크립트를 열지 않고 시트에서 직접 추가·삭제할 수 있다.
 *    탭이 없거나 비어 있으면 주말(토·일)만 비영업일로 간주한다
 * 6. events 탭 헤더에 컬럼 2개 추가 (K1, L1) — 없으면 최초 실행 시 자동 생성됨
 *    reminder_24h_sent | reminder_30m_sent
 *    ⚠️ 컬럼명은 하위 호환을 위해 유지하되 의미가 바뀌었다:
 *       reminder_24h_sent → 사전 안내(14:30) 발송 완료
 *       reminder_30m_sent → 당일 안내(10:30) 발송 완료
 *    ⚠️ 기존 A~J 컬럼 순서/내용은 절대 건드리지 말 것 (Python 쪽 utils/sheets.py가
 *    A~J 범위만 갱신하므로 K/L 컬럼은 이 스크립트 전용으로 안전하게 분리됨)
 * 7. 트리거 추가: runEventReminders → 시간 기반 → 분 단위 타이머 → 10분마다
 *    (고정 시각을 쓰지만, Apps Script 일일 트리거는 ±15분 오차가 있어
 *     10분 타이머 + 시각 게이트 방식이 더 정확하다. 실행이 한 번 실패해도
 *     다음 tick에서 자동으로 따라잡는다)
 */

var _PROPS = PropertiesService.getScriptProperties();
var SHEET_ID = _PROPS.getProperty("SHEET_ID");
var NOTIFY_EMAIL = _PROPS.getProperty("NOTIFY_EMAIL");   // 스크립트 속성 필수(하드코딩 금지)
var EVENTS_TAB = "events";
var HOLIDAY_TAB = "공휴일";
var CALENDAR_URL = "https://dplan360-media.streamlit.app/EventCalendar";
var TZ = "Asia/Seoul";

var COL_ADVANCE = "reminder_24h_sent"; // 사전 안내(14:30) 발송 완료 — 컬럼명은 하위 호환 유지
var COL_SAMEDAY = "reminder_30m_sent"; // 당일 안내(10:30) 발송 완료 — 컬럼명은 하위 호환 유지

// 고정 발송 시각 (분 단위). 이 시각 "이후" 첫 tick에서 발송된다.
var SEND_AT_ADVANCE = 14 * 60 + 30; // 14:30 — 다음 영업일까지의 행사
var SEND_AT_SAMEDAY = 10 * 60 + 30; // 10:30 — 오늘 행사

var WEEKDAYS = ["일", "월", "화", "수", "목", "금", "토"];


function runEventReminders() {
  if (!SHEET_ID) throw new Error("스크립트 속성 SHEET_ID 미설정");
  var ss = SpreadsheetApp.openById(SHEET_ID);
  var ws = ss.getSheetByName(EVENTS_TAB);
  if (!ws) return;

  var now = new Date();

  // 비영업일에는 어떤 메일도 보내지 않는다.
  // 월요일 행사가 전주 금요일에 안내되는 것도 이 규칙에서 파생된다.
  if (!_isBusinessDay(now)) {
    Logger.log("비영업일(" + _ymd(now) + ") — 발송 건너뜀");
    return;
  }

  var headerRow = ws.getRange(1, 1, 1, ws.getLastColumn()).getValues()[0];
  var colIdx = _ensureReminderColumns(ws, headerRow);
  var data = ws.getDataRange().getValues();
  var minutesNow = now.getHours() * 60 + now.getMinutes();

  // ── 당일 안내 (10:30) — 오늘 행사 ──
  if (minutesNow >= SEND_AT_SAMEDAY) {
    var todayOnly = {};
    todayOnly[_ymd(now)] = true;
    var sameday = _collectEvents(data, colIdx, todayOnly, colIdx.sameday_sent);
    if (sameday.length) {
      _sendDigest("sameday", sameday, now);
      _markSent(ws, sameday, colIdx.sameday_sent);
    }
  }

  // ── 사전 안내 (14:30) — 내일부터 다음 영업일까지 ──
  if (minutesNow >= SEND_AT_ADVANCE) {
    var upcoming = _collectEvents(data, colIdx, _coverageDates(now), colIdx.advance_sent);
    if (upcoming.length) {
      _sendDigest("advance", upcoming, now);
      _markSent(ws, upcoming, colIdx.advance_sent);
    }
  }
}


/**
 * 수동 테스트용 — 지금 당장 발송해 본다.
 *
 * runEventReminders()와 달리 영업일 판정과 발송 시각(10:30/14:30) 게이트를 무시한다.
 * **발송 완료 표시(K/L 컬럼)를 남기지 않으므로** 몇 번을 돌려도 실제 운영에 영향이 없고,
 * 정규 발송 시각이 되면 정상적으로 다시 발송된다.
 *
 * 사용법: 에디터 상단 함수 선택에서 testSendNow 선택 → 실행 → 하단 "실행 로그" 확인
 */
function testSendNow() {
  if (!SHEET_ID) throw new Error("스크립트 속성 SHEET_ID 미설정");
  var ws = SpreadsheetApp.openById(SHEET_ID).getSheetByName(EVENTS_TAB);
  if (!ws) throw new Error("events 탭을 찾을 수 없음");

  var now = new Date();
  var headerRow = ws.getRange(1, 1, 1, ws.getLastColumn()).getValues()[0];
  var colIdx = _ensureReminderColumns(ws, headerRow);
  var data = ws.getDataRange().getValues();

  Logger.log("=== 테스트 발송 (K/L 표시 남기지 않음) ===");
  var hol = Object.keys(_getHolidays()).sort();
  Logger.log("공휴일 " + hol.length + "건 인식: " + (hol.join(", ") || "(없음 — 주말만 비영업일)"));
  Logger.log("오늘: " + _ymd(now) + " (" + WEEKDAYS[now.getDay()] + ") / 영업일 여부: " + _isBusinessDay(now));
  Logger.log("사전 안내 커버 날짜: " + Object.keys(_coverageDates(now)).join(", "));

  var todayOnly = {};
  todayOnly[_ymd(now)] = true;
  var sameday = _collectEvents(data, colIdx, todayOnly, colIdx.sameday_sent);
  Logger.log("당일 안내 대상: " + sameday.length + "건");
  if (sameday.length) _sendDigest("sameday", sameday, now);

  var upcoming = _collectEvents(data, colIdx, _coverageDates(now), colIdx.advance_sent);
  Logger.log("사전 안내 대상: " + upcoming.length + "건");
  if (upcoming.length) _sendDigest("advance", upcoming, now);

  if (!sameday.length && !upcoming.length) {
    Logger.log("발송할 행사가 없습니다. events 탭에서 requires_check=TRUE 이고");
    Logger.log("날짜가 오늘/커버 범위에 있으며 K·L열이 비어 있는 행이 필요합니다.");
  }
  Logger.log("수신자: " + NOTIFY_EMAIL);
}


/**
 * 사전 안내가 커버할 날짜 집합 (yyyy-MM-dd → true).
 * 내일부터 시작해 "다음 영업일"에 도달할 때까지 포함한다.
 *   월~목 실행 → 내일 하루
 *   금요일 실행 → 토·일·월 (주말 행사 누락 방지 + 월요일 행사 사전 안내)
 */
function _coverageDates(now) {
  var dates = {};
  var d = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);
  for (var guard = 0; guard < 14; guard++) {
    dates[_ymd(d)] = true;
    if (_isBusinessDay(d)) break;
    d = new Date(d.getFullYear(), d.getMonth(), d.getDate() + 1);
  }
  return dates;
}


/** 주말이거나 공휴일이면 비영업일 */
function _isBusinessDay(d) {
  var dow = d.getDay();
  if (dow === 0 || dow === 6) return false;
  return !_getHolidays()[_ymd(d)];
}


/**
 * 공휴일 목록을 { "yyyy-MM-dd": true } 형태로 반환한다.
 *
 * 주 관리 수단은 **같은 스프레드시트의 "공휴일" 탭**이다 (A열 날짜 / B열 명칭, 1행은 헤더).
 * 담당자가 스크립트를 열지 않고 시트에서 직접 추가·삭제할 수 있다.
 * 스크립트 속성 HOLIDAYS(콤마 구분)를 함께 쓰면 양쪽을 합쳐서 인식한다(선택).
 *
 * 실행 1회당 한 번만 읽어 캐시한다.
 */
var _holidayCache = null;
function _getHolidays() {
  if (_holidayCache) return _holidayCache;
  var set = {};

  // (선택) 스크립트 속성 — 시트를 쓸 수 없는 상황용 보조 수단
  (_PROPS.getProperty("HOLIDAYS") || "").split(",").forEach(function (s) {
    var k = _normalizeYmd(s);
    if (k) set[k] = true;
  });

  // (주) 시트의 공휴일 탭
  try {
    var ws = SpreadsheetApp.openById(SHEET_ID).getSheetByName(HOLIDAY_TAB);
    if (ws) {
      var lastRow = ws.getLastRow();
      if (lastRow >= 2) {
        ws.getRange(2, 1, lastRow - 1, 1).getValues().forEach(function (r) {
          var k = _normalizeYmd(r[0]);
          if (k) set[k] = true;
        });
      }
    } else {
      Logger.log('"' + HOLIDAY_TAB + '" 탭이 없어 주말만 비영업일로 처리합니다.');
    }
  } catch (e) {
    // 탭을 못 읽어도 발송 자체는 계속되어야 하므로 주말 기준으로 폴백한다.
    Logger.log("공휴일 탭 읽기 실패 — 주말 기준으로 폴백: " + e);
  }

  _holidayCache = set;
  return set;
}


/** 날짜 셀(Date 또는 문자열)을 yyyy-MM-dd로 정규화. 인식 불가면 빈 문자열 */
function _normalizeYmd(v) {
  if (!v) return "";
  if (v instanceof Date) return _ymd(v);
  var s = String(v).trim();
  if (!s) return "";
  // "2026-09-24" / "2026.09.24" / "2026/9/24" 모두 허용
  var m = s.match(/^(\d{4})[-./](\d{1,2})[-./](\d{1,2})$/);
  if (m) {
    return m[1] + "-" + ("0" + m[2]).slice(-2) + "-" + ("0" + m[3]).slice(-2);
  }
  var d = new Date(s);
  return isNaN(d.getTime()) ? "" : _ymd(d);
}


/** 대상 날짜에 걸린 미발송 행사를 시작 시각 오름차순으로 수집 */
function _collectEvents(data, colIdx, targetDates, sentCol) {
  var out = [];
  for (var i = 1; i < data.length; i++) {
    var row = data[i];
    if (!row[colIdx.id]) continue;
    if (!_isTrue(row[colIdx.requires_check])) continue;
    if (_isTrue(row[sentCol])) continue;

    var eventDt = _parseEventDateTime(row[colIdx.event_date], row[colIdx.start_time]);
    if (!eventDt) continue;
    if (!targetDates[_ymd(eventDt)]) continue;

    out.push({
      rowNum: i + 1,
      dt: eventDt,
      title: row[colIdx.title],
      category: row[colIdx.category],
      venue: row[colIdx.venue],
      memo: row[colIdx.memo],
      startTime: _fmtHHmm(row[colIdx.start_time]),
      endTime: _fmtHHmm(row[colIdx.end_time]),
    });
  }
  out.sort(function (a, b) { return a.dt.getTime() - b.dt.getTime(); });
  return out;
}


function _markSent(ws, events, sentColIdx) {
  events.forEach(function (e) {
    ws.getRange(e.rowNum, sentColIdx + 1).setValue("TRUE");
  });
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
    advance_sent: headerRow.indexOf(COL_ADVANCE),
    sameday_sent: headerRow.indexOf(COL_SAMEDAY),
  };

  var lastCol = headerRow.length;
  if (idx.advance_sent === -1) {
    lastCol += 1;
    ws.getRange(1, lastCol).setValue(COL_ADVANCE);
    idx.advance_sent = lastCol - 1;
  }
  if (idx.sameday_sent === -1) {
    lastCol += 1;
    ws.getRange(1, lastCol).setValue(COL_SAMEDAY);
    idx.sameday_sent = lastCol - 1;
  }
  return idx;
}


function _isTrue(v) {
  return String(v).trim().toUpperCase() === "TRUE";
}


function _parseEventDateTime(dateVal, timeVal) {
  var d = dateVal instanceof Date ? new Date(dateVal) : new Date(String(dateVal));
  if (isNaN(d.getTime())) return null;
  var hhmm = _fmtHHmm(timeVal).split(":");
  if (hhmm.length < 2) return null;
  d.setHours(Number(hhmm[0]), Number(hhmm[1]), 0, 0);
  return d;
}


function _ymd(d) {
  return Utilities.formatDate(d, TZ, "yyyy-MM-dd");
}


/** 한 통에 여러 행사를 담아 발송 */
function _sendDigest(type, events, now) {
  var sameday = type === "sameday";
  var n = events.length;
  var first = events[0];

  // 발송 대상이 하루인지 여러 날인지 (금요일 사전 안내는 토·일·월이 섞일 수 있음)
  var dayKeys = {};
  events.forEach(function (e) { dayKeys[_ymd(e.dt)] = true; });
  var singleDay = Object.keys(dayKeys).length === 1;

  var tomorrowYmd = _ymd(new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1));
  var isTomorrow = singleDay && _ymd(first.dt) === tomorrowYmd;

  var dayLabel = _fmtDayLabel(first.dt);           // "9월 8일(월)"
  var whenWord = sameday ? "오늘" : (isTomorrow ? "내일" : dayLabel);

  // ── 제목 ──
  // 형식: [SP] {기간} 행사 참석 안내 - {꼬리}
  //   기간 : 하루면 "9/7(월)", 날짜가 걸치면 "9/5(토)~9/7(월)", 당일 안내는 "오늘(9/7)"
  //   꼬리 : 1건이면 행사명(더 유용), 여러 건이면 "총 N건"
  var whenPart = sameday
    ? "오늘(" + Utilities.formatDate(first.dt, TZ, "M/d") + ")"
    : singleDay
      ? _fmtDayShort(first.dt)
      : _fmtDayShort(first.dt) + "~" + _fmtDayShort(events[n - 1].dt);
  var tailPart = n === 1 ? first.title : "총 " + n + "건";
  var subject = "[SP] " + whenPart + " 행사 참석 안내 - " + tailPart;

  // ── 인사말 ──
  var greeting = "안녕하세요, SP팀입니다.<br>"
    + whenWord + " 예정된 행사 " + (n === 1 ? "정보를" : "<b>" + n + "건</b>을")
    + " 안내드리오니 많은 참여 부탁드립니다.";

  // ── 행사 카드 ──
  var cards = events.map(function (e) {
    var facts = [];
    if (sameday || singleDay) {
      facts.push(["시간", e.startTime + " ~ " + e.endTime]);
    } else {
      facts.push(["일시", _fmtDayLabel(e.dt) + " " + e.startTime + " ~ " + e.endTime]);
    }
    facts.push(["장소", e.venue]);
    if (e.memo) facts.push(["메모", e.memo]);
    return { title: e.title, category: e.category, factRows: facts };
  });

  var badgeLabel = sameday
    ? (n > 1 ? "⏰ 오늘 진행 · " + n + "건" : "⏰ 오늘 진행")
    : (n > 1 ? "행사 안내 · " + n + "건" : "행사 안내");

  var html = _renderReminderHtml(type, {
    greeting: greeting,
    badgeLabel: badgeLabel,
    dateHeading: sameday || singleDay ? _fmtDayLabel(first.dt) : "",
    cards: cards,
    ctaLabel: sameday ? "참석 여부 체크하러 가기 →" : "디플랜360 캘린더에서 체크하기 →",
    footerText: sameday
      ? "교육 참석 후 캘린더에서 참석 여부를 체크해 주세요."
      : "이 메일은 참석 설정된 행사에 대해 자동 발송됩니다.",
  });

  GmailApp.sendEmail(NOTIFY_EMAIL, subject, "", { htmlBody: html });
  Logger.log("[" + type + "] " + n + "건 발송 → " + NOTIFY_EMAIL + " / " + subject);
}


// 승인된 시안(사전 안내=차분한 블랙 톤 / 당일 안내=긴급 앰버 톤) 그대로 인라인 스타일로 반영.
// 이메일 클라이언트는 <style> 블록을 신뢰할 수 없어 전부 인라인으로 작성.
// 2026-09-05: 행사 여러 건을 카드로 반복 렌더링하도록 확장.
function _renderReminderHtml(type, data) {
  var urgent = type === "sameday";
  var stripBg = urgent
    ? "background:linear-gradient(90deg,#F2A93B,#E8971C);"
    : "background:#0B0B0B;";
  var badgeStyle = urgent
    ? "background:#FFF1D6;color:#8A5A0A;"
    : "background:#F1F0EC;color:#45433C;";
  var ctaStyle = urgent
    ? "background:#F2A93B;color:#1C1200;"
    : "background:#0B0B0B;color:#ffffff;";

  var cardsHtml = data.cards.map(function (c) {
    var factsHtml = c.factRows.map(function (r) {
      return '<tr>'
        + '<td style="color:#96928A;font-size:13.5px;padding:4px 10px 4px 0;width:44px;vertical-align:top;white-space:nowrap;">' + r[0] + '</td>'
        + '<td style="color:#1C1B18;font-size:13.5px;padding:4px 0;">' + r[1] + '</td>'
        + '</tr>';
    }).join('');

    return '<div style="background:#FBFAF7;border:1px solid #ECE9E0;border-radius:12px;padding:18px 20px;margin:0 0 12px;">'
      + '<div style="margin:0 0 14px;">'
      + '<span style="font-size:16px;font-weight:700;color:#0B0B0B;">' + c.title + '</span>'
      + (c.category
        ? '<span style="font-size:11px;font-weight:600;padding:3px 9px;border-radius:4px;background:#0B0B0B;color:#ffffff;margin-left:8px;">' + c.category + '</span>'
        : '')
      + '</div>'
      + '<table style="width:100%;border-collapse:collapse;">' + factsHtml + '</table>'
      + '</div>';
  }).join('');

  var dateHeadingHtml = data.dateHeading
    ? '<div style="font-size:12px;font-weight:700;color:#8B877D;letter-spacing:0.04em;margin:0 0 10px;">' + data.dateHeading + '</div>'
    : '';

  return ''
    + '<div style="max-width:560px;margin:0 auto;font-family:Pretendard,-apple-system,\'Apple SD Gothic Neo\',\'Malgun Gothic\',sans-serif;">'
    + '<div style="height:5px;border-radius:10px 10px 0 0;' + stripBg + '"></div>'
    + '<div style="border:1px solid #E7E4DC;border-top:none;border-radius:0 0 10px 10px;padding:28px 30px 30px;background:#ffffff;">'

    + '<p style="margin:0 0 18px;font-size:14px;line-height:1.7;color:#1C1B18;">' + data.greeting + '</p>'

    + '<div style="margin:0 0 18px;">'
    + '<span style="display:inline-block;font-size:12px;font-weight:700;letter-spacing:0.02em;padding:5px 11px;border-radius:100px;' + badgeStyle + '">' + data.badgeLabel + '</span>'
    + '</div>'

    + dateHeadingHtml
    + cardsHtml

    + '<div style="text-align:center;margin:24px 0 20px;">'
    + '<a href="' + CALENDAR_URL + '" style="display:inline-block;padding:12px 26px;border-radius:8px;font-size:14px;font-weight:700;text-decoration:none;' + ctaStyle + '">' + data.ctaLabel + '</a>'
    + '</div>'

    + '<p style="margin:22px 0 0;color:#6B6862;font-size:13px;">감사합니다.</p>'

    + '<div style="margin-top:18px;padding-top:14px;border-top:1px solid #EFEDE6;font-size:11px;color:#A7A398;">' + data.footerText + '</div>'
    + '</div>'
    + '</div>';
}


/** 본문용 — "9월 7일(월)" */
function _fmtDayLabel(d) {
  return Utilities.formatDate(d, TZ, "M월 d일") + "(" + WEEKDAYS[d.getDay()] + ")";
}


/** 제목용 축약형 — "9/7(월)" */
function _fmtDayShort(d) {
  return Utilities.formatDate(d, TZ, "M/d") + "(" + WEEKDAYS[d.getDay()] + ")";
}


function _fmtHHmm(v) {
  if (v instanceof Date) return Utilities.formatDate(v, TZ, "HH:mm");
  // Sheets 시간 서식이 앞자리 0을 없애는 경우 보정 (예: "3:00" → "03:00")
  var parts = String(v).trim().slice(0, 5).split(":");
  if (parts.length < 2) return String(v).trim();
  return (parts[0].length === 1 ? "0" + parts[0] : parts[0]) + ":" + parts[1];
}
