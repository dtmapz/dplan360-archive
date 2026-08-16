/**
 * budget_history 월간 자동 동기화 — Apps Script
 *
 * 목표: 매월 12일, 전월 대행사 발행월 기준 신규 캠페인 이력을 dplan360.emato.net 플랫폼에서 수집해
 *      budget_history 시트에 append. 신규 광고주/브랜드는 budget_adv에 append. 완료 이메일 발송.
 *
 * 설정:
 * 1. BIGQUERY_MAPPING_SHEET_ID 스프레드시트 열기
 * 2. 확장 프로그램 > Apps Script
 * 3. 이 파일 붙여넣기 → 저장
 * 4. 프로젝트 설정 > 스크립트 속성:
 *    - SHEET_ID           : 시트 ID (1VSS1zHc...)
 *    - LOGIN_ID           : 플랫폼 로그인 ID
 *    - LOGIN_PW           : 플랫폼 로그인 PW
 *    - NOTIFY_EMAIL       : mj.park@d-plan360.com (미설정 시 기본값 사용)
 * 5. 프로젝트 설정 > 시간대: (GMT+09:00) 서울 확인
 * 6. 첫 실행: testJuly2026() 를 dry-run으로 검증
 * 7. 정상 확인 후 setupMonthlyTrigger() 실행 → 매월 12일 05시 자동 트리거 등록
 *
 * 하드코딩 금지 원칙: 시크릿과 시트 ID는 스크립트 속성으로만 관리 (레포가 Public).
 */

var _PROPS = PropertiesService.getScriptProperties();
var SHEET_ID = _PROPS.getProperty("SHEET_ID");
var LOGIN_ID = _PROPS.getProperty("LOGIN_ID");
var LOGIN_PW = _PROPS.getProperty("LOGIN_PW");
var NOTIFY_EMAIL = _PROPS.getProperty("NOTIFY_EMAIL") || "mj.park@d-plan360.com";

var HISTORY_GID = 1008030082;   // budget_history
var ADV_GID = 528569663;        // budget_adv

var BASE = "https://dplan360.emato.net";
var LOGIN_URL = BASE + "/_common/loginProc.php";
var LIST_API = BASE + "/ajax/ajax.inquire.php";
var DETAIL_API = BASE + "/ajax/ajax.campaign.php";

var MAX_RUN_MS = 4.5 * 60 * 1000;    // 4.5분 넘으면 checkpoint 저장 후 종료
var CONTINUE_HANDLER = "continueSync"; // 재개용 트리거 핸들러
var STATE_KEY = "SYNC_STATE";          // Script Properties key

// ============================================================
// 진입점
// ============================================================

/** 매월 12일 05시 트리거가 호출. 전월 데이터 수집. */
function runMonthlySync() {
  var now = new Date();
  var prev = new Date(now.getFullYear(), now.getMonth() - 1, 1);
  runSyncForMonth_(prev.getFullYear(), prev.getMonth() + 1, /* dryRun */ false);
}

/** 26년 7월 데이터로 dry-run 테스트 (시트 미변경). 로그 확인 후 실행. */
function testJuly2026DryRun() {
  runSyncForMonth_(2026, 7, /* dryRun */ true);
}

/** 26년 7월 데이터 실제 append. dry-run 검증 후 이 함수를 실행. */
function testJuly2026Live() {
  runSyncForMonth_(2026, 7, /* dryRun */ false);
}

// ============================================================
// 메인 로직
// ============================================================

function runSyncForMonth_(year, month, dryRun) {
  if (!SHEET_ID || !LOGIN_ID || !LOGIN_PW) {
    throw new Error("스크립트 속성 SHEET_ID / LOGIN_ID / LOGIN_PW 필요");
  }
  var t0 = new Date().getTime();
  var monthStr = year + "." + pad2_(month);

  // 저장된 진행 상태 확인 (경량: remainingIdx + 카운터만 저장)
  var state = loadState_();
  var isResume = false;
  if (state && state.monthStr === monthStr && state.dryRun === dryRun) {
    isResume = true;
    Logger.log("=== " + monthStr + " 재개 (남은 idx=" + state.remainingIdx.length + ") ===");
  } else {
    if (state) Logger.log("이전 미완료 상태 폐기 (" + state.monthStr + " → " + monthStr + ")");
    state = {
      monthStr: monthStr, year: year, month: month, dryRun: dryRun,
      remainingIdx: null, apiRows: 0, totalCampaigns: 0,
      newLines: 0,
    };
  }

  var cookie = login_();
  var rawRows = fetchSalesList_(cookie, year, month);

  // 대행사 발행월(agTaxIssueDateYm) 기준 후처리 필터 — API의 salesMonth 필터가 belongSalesDateYm 기준이라 불일치 방지
  var salesRows = rawRows.filter(function(r) {
    return String(r.agTaxIssueDateYm || "") === monthStr;
  });

  if (!isResume) {
    Logger.log("=== " + monthStr + " 동기화 시작 (dryRun=" + dryRun + ") ===");
    Logger.log("목록 API: " + rawRows.length + "건 → 대행사발행월(" + monthStr + ") 필터 후 " + salesRows.length + "건");
    state.apiRows = salesRows.length;
    var allIdx = uniq_(salesRows.map(function(r) { return String(r.idx || ""); }).filter(String));
    Logger.log("고유 캠페인 idx: " + allIdx.length + "개");
    state.totalCampaigns = allIdx.length;
    state.remainingIdx = allIdx;
  }

  // 시트 로드 + 월 단위 재실행 방지 체크
  var ss = SpreadsheetApp.openById(SHEET_ID);
  var hSheet = getSheetByGid_(ss, HISTORY_GID);
  if (!isResume && !dryRun && monthHasData_(hSheet, monthStr)) {
    Logger.log("스킵: " + monthStr + " 데이터가 이미 존재. 재실행 원하면 해당 월 행 삭제 후 재시도");
    clearState_();
    cleanupContinueTriggers_();
    return;
  }

  // 캠페인idx → 해당 idx의 salesRows 매핑 (메모리 상, 저장 안 함)
  var salesByIdx = {};
  for (var i = 0; i < salesRows.length; i++) {
    var idxKey = String(salesRows[i].idx || "");
    if (!salesByIdx[idxKey]) salesByIdx[idxKey] = [];
    salesByIdx[idxKey].push(salesRows[i]);
  }

  // 상세 API를 캠페인 단위로 처리 + 즉시 시트 append (dryRun이면 로그만)
  var processedNow = 0;
  var dryRunPreview = [];
  while (state.remainingIdx.length > 0) {
    if (new Date().getTime() - t0 > MAX_RUN_MS) {
      saveState_(state);
      scheduleContinue_();
      Logger.log("시간 한도 근접 — checkpoint. 남은 " + state.remainingIdx.length + "개 다음 실행 이어서");
      Logger.log("이번 실행 처리: " + processedNow + "개, 누적 신규 라인: " + state.newLines);
      return;
    }
    var idx = state.remainingIdx.shift();
    var items = fetchCampaignMediaList_(cookie, idx);
    // 상세 API 응답을 pool(가변 배열)로 관리 — 매칭될 때마다 제거해 다중 라인 정확히 배분
    var detailPool = items.slice();

    var pendingRows = [];
    var rowsForIdx = salesByIdx[idx] || [];
    for (var k = 0; k < rowsForIdx.length; k++) {
      var r = rowsForIdx[k];
      var memo = pickAndConsumeMemo_(detailPool, r);
      pendingRows.push([
        r.campaignName || "",
        r.advertiserName || "",
        "", // C 브랜드: 사용자 수동
        r.agencyName || "",
        r.mediaName || "",
        r.totalAdPrice || "",
        r.agTaxIssueDateYm || "",
        memo,
      ]);
    }

    if (pendingRows.length > 0) {
      if (dryRun) {
        for (var pv = 0; pv < pendingRows.length && dryRunPreview.length < 5; pv++) {
          dryRunPreview.push(pendingRows[pv]);
        }
      } else {
        var start = hSheet.getLastRow() + 1;
        hSheet.getRange(start, 1, pendingRows.length, 8).setValues(pendingRows);
      }
      state.newLines += pendingRows.length;
    }

    processedNow++;
    Utilities.sleep(50);
  }

  Logger.log("상세 처리 완료 — 신규 라인 " + state.newLines + "건");
  if (dryRun && dryRunPreview.length > 0) {
    Logger.log("[DRY-RUN] 상위 " + dryRunPreview.length + "건 미리보기:");
    for (var pv2 = 0; pv2 < dryRunPreview.length; pv2++) {
      Logger.log("  " + JSON.stringify(dryRunPreview[pv2]));
    }
  }

  // budget_adv 신규 조합 (전체 budget_history 재스캔)
  var advSheet = getSheetByGid_(ss, ADV_GID);
  var advAppendRows = collectNewAdvRows_(hSheet, advSheet, []);
  Logger.log("신규 광고주/브랜드 조합: " + advAppendRows.length + "건");

  if (!dryRun && advAppendRows.length > 0) {
    var s2 = advSheet.getLastRow() + 1;
    advSheet.getRange(s2, 1, advAppendRows.length, 4).setValues(advAppendRows);
  }

  var dur = Math.round((new Date().getTime() - t0) / 1000);
  sendReport_({
    year: year, month: month, monthStr: monthStr, dryRun: dryRun,
    apiRows: state.apiRows,
    campaigns: state.totalCampaigns,
    newLines: state.newLines,
    newAdv: advAppendRows.length,
    duration: dur,
    apiCalls: 1 + state.totalCampaigns,
  });
  clearState_();
  cleanupContinueTriggers_();
  Logger.log("=== 완료 (" + dur + "s) ===");
}

// ============================================================
// 플랫폼 API
// ============================================================

function login_() {
  var resp = UrlFetchApp.fetch(LOGIN_URL, {
    method: "post",
    payload: { action: "login", userID: LOGIN_ID, userPW: LOGIN_PW, isRemember: "Y" },
    followRedirects: false,
    muteHttpExceptions: true,
  });
  var headers = resp.getAllHeaders();
  var setCookie = headers["Set-Cookie"] || headers["set-cookie"];
  var arr = Array.isArray(setCookie) ? setCookie : [setCookie || ""];
  var phpsessid = null;
  for (var i = 0; i < arr.length; i++) {
    var m = String(arr[i]).match(/PHPSESSID=([^;]+)/);
    if (m) { phpsessid = m[1]; break; }
  }
  if (!phpsessid) throw new Error("로그인 실패: PHPSESSID 헤더 없음. 응답: " + resp.getContentText().substring(0, 200));
  var body = resp.getContentText();
  if (body.indexOf("top.location.href") === -1) {
    Logger.log("경고: 로그인 응답 본문에 리다이렉트 스크립트 없음. 진행하되 확인 필요.");
  }
  return "PHPSESSID=" + phpsessid;
}

function fetchSalesList_(cookie, year, month) {
  // dateType=agIssueMonth: 대행사 발행월 기준 필터 (agTaxIssueDateYm 컬럼과 매핑)
  // dateSelType=monthly + monthlySelArr[]=N: 특정 월만 지정
  var quarter = Math.ceil(month / 3);
  var parts = [
    kv_("action", "getSalesList"),
    kv_("teamIdx", ""), kv_("advertiserIdx", ""), kv_("agencyIdx", ""), kv_("mediaIdx", ""),
    kv_("campaignStatus", ""), kv_("campaignConfirm", ""),
    kv_("dateType", "agIssueMonth"), kv_("dateY", String(year)), kv_("dateSelType", "monthly"),
    "quarterSelArr%5B%5D=" + quarter,
    "monthlySelArr%5B%5D=" + month,
    kv_("search", ""), kv_("sort", ""), kv_("order", ""),
    kv_("offset", "0"), kv_("limit", "10000"),
  ];
  var resp = UrlFetchApp.fetch(LIST_API, {
    method: "post",
    contentType: "application/x-www-form-urlencoded; charset=UTF-8",
    headers: { "Cookie": cookie, "X-Requested-With": "XMLHttpRequest", "Referer": BASE + "/page/inquireList.php" },
    payload: parts.join("&"),
    muteHttpExceptions: true,
  });
  var data = JSON.parse(resp.getContentText());
  return data.rows || [];
}

function fetchCampaignMediaList_(cookie, campaignIdx) {
  var parts = [
    kv_("action", "getCampaignMediaList"),
    kv_("campaignIdx", campaignIdx),
    kv_("search", ""), kv_("sort", ""), kv_("order", ""),
  ];
  var resp = UrlFetchApp.fetch(DETAIL_API, {
    method: "post",
    contentType: "application/x-www-form-urlencoded; charset=UTF-8",
    headers: { "Cookie": cookie, "X-Requested-With": "XMLHttpRequest", "Referer": BASE + "/page/campaignRegister.php?id=" + campaignIdx },
    payload: parts.join("&"),
    muteHttpExceptions: true,
  });
  try {
    var data = JSON.parse(resp.getContentText());
    return data.rows || [];
  } catch (e) {
    Logger.log("상세 API 파싱 실패 idx=" + campaignIdx + " err=" + e);
    return [];
  }
}

// ============================================================
// 시트 처리
// ============================================================

function getSheetByGid_(ss, gid) {
  var sheets = ss.getSheets();
  for (var i = 0; i < sheets.length; i++) {
    if (sheets[i].getSheetId() === gid) return sheets[i];
  }
  throw new Error("gid=" + gid + " 시트 없음");
}

/** 해당 월 데이터가 시트에 이미 있는지 (G열=대행사 발행월). */
function monthHasData_(sheet, monthStr) {
  var lastRow = sheet.getLastRow();
  if (lastRow < 2) return false;
  var values = sheet.getRange(2, 7, lastRow - 1, 1).getValues();
  for (var i = 0; i < values.length; i++) {
    if (String(values[i][0] || "").trim() === monthStr) return true;
  }
  return false;
}

/**
 * detailPool에서 salesRow에 대응하는 memo를 찾아 반환. 매칭된 라인은 pool에서 제거.
 * 우선순위: (media, price, commissionMedia) → (media, price)
 * 이유: 같은 매체·가격 라인이 여러 건이어도 commissionMedia가 라인마다 다르면 정확히 매칭됨.
 */
function pickAndConsumeMemo_(detailPool, salesRow) {
  var media = normStr_(salesRow.mediaName);
  var price = normPrice_(salesRow.totalAdPrice);
  var commMedia = normPrice_(salesRow.commissionMedia);
  // 1차: 3-키 정확 매칭
  for (var i = 0; i < detailPool.length; i++) {
    var it = detailPool[i];
    if (normStr_(it.mediaName) === media
        && normPrice_(it.adPrice) === price
        && normPrice_(it.commissionMedia) === commMedia) {
      detailPool.splice(i, 1);
      return cleanMemo_(it.memo || "");
    }
  }
  // 2차: 2-키 fallback (commissionMedia 표기 차이 대비)
  for (var j = 0; j < detailPool.length; j++) {
    var it2 = detailPool[j];
    if (normStr_(it2.mediaName) === media && normPrice_(it2.adPrice) === price) {
      detailPool.splice(j, 1);
      return cleanMemo_(it2.memo || "");
    }
  }
  return "";
}

function getExistingHistoryKeys_(sheet) {
  var values = sheet.getDataRange().getValues();
  var set = {};
  for (var i = 1; i < values.length; i++) {
    var row = values[i];
    // A캠페인명, B광고주, D대행사, E매체사, F광고수주액, G발행월 (C 브랜드는 매칭 제외)
    var key = makeKey_(row[0], row[1], row[3], row[4], row[5], row[6]);
    set[key] = true;
  }
  return set;
}

function collectNewAdvRows_(hSheet, advSheet, pendingNewRows) {
  var advValues = advSheet.getDataRange().getValues();
  var existing = {};
  for (var i = 1; i < advValues.length; i++) {
    var a = String(advValues[i][0] || "").trim();
    var b = String(advValues[i][1] || "").trim();
    if (a || b) existing[a + "||" + b] = true;
  }

  var seen = {};
  var newRows = [];

  // 기존 시트 스캔 (사용자가 C브랜드 수동 채운 것 포함)
  var hValues = hSheet.getDataRange().getValues();
  for (var j = 1; j < hValues.length; j++) {
    var adv = String(hValues[j][1] || "").trim();
    var brand = String(hValues[j][2] || "").trim();
    if (!adv && !brand) continue;
    var key = adv + "||" + brand;
    if (seen[key]) continue;
    seen[key] = true;
    if (!existing[key]) newRows.push([adv, brand, "", ""]);
  }

  // 이번 실행에서 새로 append될 라인들도 검사 (dryRun 대응)
  for (var k = 0; k < pendingNewRows.length; k++) {
    var adv2 = String(pendingNewRows[k][1] || "").trim();
    var brand2 = String(pendingNewRows[k][2] || "").trim();
    if (!adv2 && !brand2) continue;
    var key2 = adv2 + "||" + brand2;
    if (seen[key2]) continue;
    seen[key2] = true;
    if (!existing[key2]) newRows.push([adv2, brand2, "", ""]);
  }
  return newRows;
}

// ============================================================
// 이메일
// ============================================================

function sendReport_(ctx) {
  var subject = "[D-PLAN360] " + ctx.monthStr + " 캠페인 이력 " + (ctx.dryRun ? "(DRY-RUN) " : "") + "업데이트 완료";
  var sheetUrl = "https://docs.google.com/spreadsheets/d/" + SHEET_ID + "/edit";
  var lines = [
    "전월(" + ctx.monthStr + ") 대행사 발행월 기준 데이터가 budget_history에 " + (ctx.dryRun ? "반영 예정" : "반영되었습니다") + ".",
    "",
    "■ 수집 결과",
    "- 플랫폼 응답 라인: " + ctx.apiRows + "건",
    "- 신규 캠페인 idx: " + ctx.campaigns + "개",
    "- 신규 매체 라인: " + ctx.newLines + "건 " + (ctx.dryRun ? "(dry-run, 시트 미반영)" : "(시트 반영 완료)"),
    "- 신규 광고주/브랜드 조합: " + ctx.newAdv + "건 " + (ctx.dryRun ? "(dry-run)" : "(budget_adv 추가됨)"),
    "",
    "■ 사용자 확인 요청",
    "- budget_history: C열(브랜드) · I열(상품) 사용자 판단 입력",
    "- budget_adv: 신규 " + ctx.newAdv + "행의 C·D열(대업종·소업종) 사용자 입력",
    "",
    "■ 링크",
    "- 시트: " + sheetUrl,
    "",
    "■ 실행 정보",
    "- 실행 시각: " + Utilities.formatDate(new Date(), "Asia/Seoul", "yyyy-MM-dd HH:mm:ss") + " KST",
    "- 소요 시간: " + ctx.duration + "초",
    "- API 호출: 목록 1회 + 상세 " + ctx.campaigns + "회",
  ];
  MailApp.sendEmail({ to: NOTIFY_EMAIL, subject: subject, body: lines.join("\n") });
}

// ============================================================
// 트리거 관리
// ============================================================

/** 매월 12일 05시(KST) 트리거 등록. 기존 동일 핸들러는 삭제 후 재등록. */
function setupMonthlyTrigger() {
  var triggers = ScriptApp.getProjectTriggers();
  for (var i = 0; i < triggers.length; i++) {
    if (triggers[i].getHandlerFunction() === "runMonthlySync") {
      ScriptApp.deleteTrigger(triggers[i]);
    }
  }
  ScriptApp.newTrigger("runMonthlySync")
    .timeBased()
    .onMonthDay(12)
    .atHour(5)
    .create();
  Logger.log("트리거 등록 완료: 매월 12일 05시(KST) runMonthlySync");
}

/** 트리거 해제 (테스트/유지보수용). */
function removeMonthlyTrigger() {
  var triggers = ScriptApp.getProjectTriggers();
  for (var i = 0; i < triggers.length; i++) {
    if (triggers[i].getHandlerFunction() === "runMonthlySync") {
      ScriptApp.deleteTrigger(triggers[i]);
    }
  }
  Logger.log("트리거 해제 완료");
}

// ============================================================
// 유틸
// ============================================================

function kv_(k, v) { return encodeURIComponent(k) + "=" + encodeURIComponent(v); }
function pad2_(n) { return (n < 10 ? "0" : "") + n; }
function normStr_(s) { return String(s || "").trim(); }
function normPrice_(s) { return String(s || "").replace(/[,\s]/g, ""); }
function cleanMemo_(html) {
  if (!html) return "";
  return String(html)
    .replace(/<[^>]+>/g, "")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/[ \t]+/g, " ")
    .replace(/\n\s*\n+/g, "\n")
    .trim();
}
function makeKey_(campaign, advertiser, agency, media, price, month) {
  return [normStr_(campaign), normStr_(advertiser), normStr_(agency), normStr_(media), normPrice_(price), normStr_(month)].join("|");
}
function uniq_(arr) {
  var seen = {}, out = [];
  for (var i = 0; i < arr.length; i++) if (!seen[arr[i]]) { seen[arr[i]] = 1; out.push(arr[i]); }
  return out;
}

// ============================================================
// 상태 저장 / 재개 트리거
// ============================================================

/** 재개 트리거가 호출. 저장된 진행 상태를 이어서 처리. */
function continueSync() {
  var state = loadState_();
  if (!state) {
    Logger.log("continueSync: 저장된 상태 없음, 종료");
    cleanupContinueTriggers_();
    return;
  }
  runSyncForMonth_(state.year, state.month, state.dryRun);
}

function loadState_() {
  var raw = _PROPS.getProperty(STATE_KEY);
  if (!raw) return null;
  try { return JSON.parse(raw); } catch (e) { return null; }
}
function saveState_(state) {
  _PROPS.setProperty(STATE_KEY, JSON.stringify(state));
}
function clearState_() {
  _PROPS.deleteProperty(STATE_KEY);
}
function scheduleContinue_() {
  cleanupContinueTriggers_();
  ScriptApp.newTrigger(CONTINUE_HANDLER)
    .timeBased()
    .after(60 * 1000)  // 1분 후
    .create();
}
function cleanupContinueTriggers_() {
  var triggers = ScriptApp.getProjectTriggers();
  for (var i = 0; i < triggers.length; i++) {
    if (triggers[i].getHandlerFunction() === CONTINUE_HANDLER) {
      ScriptApp.deleteTrigger(triggers[i]);
    }
  }
}

/** 임의 idx의 memo 매칭 검증 (내부용). */
function verifyIdxMemo_(idxStr) {
  var cookie = login_();
  var salesRows = fetchSalesList_(cookie, 2026, 7).filter(function(r) {
    return String(r.idx) === idxStr;
  });
  var items = fetchCampaignMediaList_(cookie, idxStr);
  var detailPool = items.slice();
  Logger.log("[idx=" + idxStr + "] salesRows: " + salesRows.length + "건 / detail: " + items.length + "건");
  Logger.log("--- 상세 API 원본 memo ---");
  for (var d = 0; d < items.length; d++) {
    var it = items[d];
    Logger.log("  detail no=" + it.no + " media=" + it.mediaName + " price=" + it.adPrice
      + " commissionMedia=" + it.commissionMedia + " memo=" + JSON.stringify(cleanMemo_(it.memo || "")));
  }
  Logger.log("--- 매칭 결과 ---");
  for (var k = 0; k < salesRows.length; k++) {
    var r = salesRows[k];
    var memo = pickAndConsumeMemo_(detailPool, r);
    Logger.log("  sales no=" + r.no + " media=" + r.mediaName + " price=" + r.totalAdPrice
      + " commissionMedia=" + r.commissionMedia + " → memo=" + JSON.stringify(memo));
  }
}

/** 동화약품 idx=4944 검증. */
function verifyDonghwaMemo() { verifyIdxMemo_("4944"); }

/** 당근(idx=5216) 캠페인 memo가 제대로 매칭되는지 검증. */
function verifyDangunMemo() { verifyIdxMemo_("5216"); }

/** 수동 초기화: 진행 상태와 재개 트리거 모두 삭제 (테스트 재시작용). */
function resetSync() {
  clearState_();
  cleanupContinueTriggers_();
  Logger.log("상태·재개 트리거 초기화 완료");
}
