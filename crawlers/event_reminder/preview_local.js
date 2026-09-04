/**
 * 리마인더 메일 로컬 미리보기 생성기.
 *
 * apps_script_event_reminder.js를 **그대로 로드**해서 실제 렌더 함수로 HTML을 뽑는다.
 * (미리보기용으로 마크업을 따로 베끼면 실물과 어긋나므로 원본을 직접 실행한다)
 *
 *   node crawlers/event_reminder/preview_local.js
 *   → crawlers/event_reminder/preview_out.html 생성
 */

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const SRC = path.join(__dirname, "apps_script_event_reminder.js");
const OUT = path.join(__dirname, "preview_out.html");

const WEEK = ["일", "월", "화", "수", "목", "금", "토"];

function pad(n) { return String(n).padStart(2, "0"); }

// Apps Script 전역 API 스텁 — 렌더링에 필요한 최소 범위만.
const sandbox = {
  PropertiesService: {
    getScriptProperties: () => ({
      getProperty: (k) => (k === "SHEET_ID" ? "dummy" : ""),
    }),
  },
  Utilities: {
    // Apps Script의 formatDate 중 이 스크립트가 쓰는 토큰만 지원.
    // 긴 토큰(yyyy/MM/dd/HH/mm)을 먼저 소비해야 M·d 단일 토큰과 충돌하지 않는다.
    formatDate(d, _tz, fmt) {
      const map = {
        yyyy: String(d.getFullYear()),
        MM: pad(d.getMonth() + 1),
        dd: pad(d.getDate()),
        HH: pad(d.getHours()),
        mm: pad(d.getMinutes()),
        M: String(d.getMonth() + 1),
        d: String(d.getDate()),
      };
      return fmt.replace(/yyyy|MM|dd|HH|mm|M|d/g, (t) => map[t]);
    },
  },
  SpreadsheetApp: {},
  Logger: { log: () => {} },
  GmailApp: { sendEmail: () => {} },
  ScriptApp: {},
  console,
};

vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(SRC, "utf8"), sandbox);

// 발송을 가로채 subject/html만 회수한다.
let captured = [];
sandbox.GmailApp.sendEmail = (to, subject, _body, opts) => {
  captured.push({ to, subject, html: opts.htmlBody });
};

function evt(dateStr, start, end, title, category, venue, memo) {
  const dt = new Date(dateStr + "T" + start + ":00");
  return {
    rowNum: 0, dt, title, category, venue, memo,
    startTime: start, endTime: end,
  };
}

// ── 시나리오 ──
// 2026-09-04(금) 실행 가정 → 사전 안내는 토·일·월을 함께 커버한다.
const FRI = new Date("2026-09-04T14:30:00");
const MON = new Date("2026-09-07T10:30:00");

const scenarios = [
  {
    label: "사전 안내 · 1건 (월~목 14:30, 내일 행사 1건)",
    note: "기존과 동일한 단일 카드. 제목·문구도 종전 형태를 유지합니다.",
    run: () => sandbox._sendDigest("advance", [
      evt("2026-09-08", "10:00", "11:30", "9월 정기 세미나", "세미나", "본사 대회의실", ""),
    ], new Date("2026-09-07T14:30:00")),
  },
  {
    label: "사전 안내 · 같은 날 2건 (14:30, 내일 행사 2건)",
    note: "하루에 여러 건이면 카드만 반복되고 인사말·버튼·푸터는 한 번만 나옵니다.",
    run: () => sandbox._sendDigest("advance", [
      evt("2026-09-08", "10:00", "11:30", "9월 정기 세미나", "세미나", "본사 대회의실", ""),
      evt("2026-09-08", "15:00", "17:00", "미디어 실무 워크샵", "워크샵", "3층 교육장", "노트북 지참"),
    ], new Date("2026-09-07T14:30:00")),
  },
  {
    label: "사전 안내 · 금요일 발송 (토·일·월 3건 커버)",
    note: "비영업일에는 보내지 않으므로 금요일 14:30에 월요일까지 한 번에 안내합니다. 날짜가 섞이면 각 카드에 '일시'로 날짜를 함께 표기합니다.",
    run: () => sandbox._sendDigest("advance", [
      evt("2026-09-05", "14:00", "16:00", "주말 특별 교육", "교육", "온라인", ""),
      evt("2026-09-07", "10:00", "11:30", "월간 전체 회의", "회의", "대강당", ""),
      evt("2026-09-07", "18:30", "20:30", "3분기 회식", "회식", "강남 본점", "참석 여부 사전 회신"),
    ], FRI),
  },
  {
    label: "당일 안내 · 1건 (10:30, 오늘 행사)",
    note: "앰버 톤 유지. 시작까지 남은 시간이 아니라 '오늘' 기준 문구로 통일했습니다.",
    run: () => sandbox._sendDigest("sameday", [
      evt("2026-09-07", "13:30", "15:00", "브랜드검색 리포팅 교육", "교육", "3층 교육장", ""),
    ], MON),
  },
  {
    label: "당일 안내 · 2건 (10:30, 오늘 행사 2건)",
    note: "당일 안내도 같은 방식으로 한 통에 묶입니다.",
    run: () => sandbox._sendDigest("sameday", [
      evt("2026-09-07", "13:30", "15:00", "브랜드검색 리포팅 교육", "교육", "3층 교육장", ""),
      evt("2026-09-07", "18:30", "20:30", "3분기 회식", "회식", "강남 본점", "참석 여부 사전 회신"),
    ], MON),
  },
];

// ── 영업일 로직 검증 ──
const bizChecks = [
  ["2026-09-04", "금"], ["2026-09-05", "토"], ["2026-09-06", "일"], ["2026-09-07", "월"],
];
const bizRows = bizChecks.map(([ymd, dow]) => {
  const d = new Date(ymd + "T12:00:00");
  const isBiz = sandbox._isBusinessDay(d);
  const cov = Object.keys(sandbox._coverageDates(d)).join(", ");
  return `<tr>
    <td>${ymd} (${dow})</td>
    <td class="${isBiz ? "ok" : "no"}">${isBiz ? "영업일 · 발송함" : "비영업일 · 발송 안 함"}</td>
    <td>${isBiz ? cov : "—"}</td>
  </tr>`;
}).join("");

// ── 출력 ──
const blocks = scenarios.map((s) => {
  captured = [];
  s.run();
  const m = captured[0];
  return `<section>
    <h2>${s.label}</h2>
    <p class="note">${s.note}</p>
    <div class="subject"><span>제목</span>${m.subject}</div>
    <div class="frame">${m.html}</div>
  </section>`;
}).join("");

fs.writeFileSync(OUT, `<!doctype html><html lang="ko"><head><meta charset="utf-8">
<title>리마인더 메일 미리보기</title>
<style>
  body{margin:0;background:#F2F1ED;font-family:Pretendard,-apple-system,'Apple SD Gothic Neo',sans-serif;color:#1C1B18;}
  .wrap{max-width:760px;margin:0 auto;padding:32px 20px 64px;}
  h1{font-size:22px;margin:0 0 4px;}
  .lead{color:#57544C;font-size:13.5px;margin:0 0 26px;}
  section{margin-bottom:34px;}
  h2{font-size:14px;margin:0 0 5px;padding-bottom:8px;border-bottom:2px solid #1C1B18;}
  .note{font-size:12.5px;color:#57544C;margin:0 0 12px;line-height:1.6;}
  .subject{background:#fff;border:1px solid #E3E0D7;border-radius:8px;padding:10px 14px;
    font-size:12.5px;font-weight:600;margin-bottom:12px;display:flex;gap:10px;align-items:baseline;}
  .subject span{font-size:10px;font-weight:700;letter-spacing:.08em;color:#8B877D;flex:none;}
  .frame{background:#fff;border:1px solid #E3E0D7;border-radius:10px;padding:20px;}
  table{width:100%;border-collapse:collapse;background:#fff;border:1px solid #E3E0D7;border-radius:8px;overflow:hidden;font-size:12.5px;}
  th,td{text-align:left;padding:9px 12px;border-bottom:1px solid #EFEDE6;}
  th{background:#FBFAF7;font-size:11px;letter-spacing:.06em;color:#57544C;}
  tr:last-child td{border-bottom:none;}
  td.ok{color:#2F7A5B;font-weight:600;} td.no{color:#C4462F;font-weight:600;}
</style></head><body><div class="wrap">
<h1>캘린더 리마인더 메일 — 로컬 미리보기</h1>
<p class="lead">apps_script_event_reminder.js의 실제 렌더 함수로 생성한 결과입니다.</p>
<section>
  <h2>영업일 판정 · 사전 안내 커버 범위</h2>
  <p class="note">비영업일에는 발송하지 않고, 금요일 발송분이 토·일·월을 함께 커버합니다.</p>
  <table><tr><th>실행일</th><th>발송 여부</th><th>사전 안내 커버 날짜</th></tr>${bizRows}</table>
</section>
${blocks}
</div></body></html>`);

console.log("생성 완료 →", OUT);
console.log("시나리오", scenarios.length, "건");
