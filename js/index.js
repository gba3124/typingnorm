/**
 * typingnorm — 判斷一段擊鍵輸入是否具有合成的跡象。
 *
 * 這是 Python 版 `typingnorm.detect` 的對應實作，兩邊必須產生完全相同的判定。
 * repo 根的 vectors.json 是共用的測試向量，任一邊走鐘 CI 就會失敗。
 *
 * 設計原則有三條，都是被資料逼出來的：
 *
 * 只用速度不變的判準。打字快與慢的人，重疊率、間隔、按住時間全都差很多，任何
 * 「離人類平均多遠」的判準都會系統性誤判速度極端的人，而那恰好是最不該被誤傷
 * 的族群：密碼管理器、語音輸入、切換式存取的使用者在時序上都長得像機器人。
 *
 * 優先用物理上不可能，而不是統計上罕見。
 *
 * 回報訊號，不回報布林值。刻意模仿真人時序的程式可以通過全部判準。
 *
 * 每條判準的誤判率都拿 check() 在 Aalto 136M Keystrokes 的 2,500 位受試者上量過，
 * 見 METHOD.md 第 7.3 節。
 */

/** 選字、確認、切換輸入法的鍵不是產生文字的擊鍵。 */
const NAV_PREFIXES = [
  "Arrow", "Meta", "Shift", "Control", "Alt", "Tab", "Escape",
  "Enter", "Page", "Home", "End", "CapsLock", "Fn", "OS",
];

/** 左右 Shift 常被正規化成同一個鍵名，那會製造假的同鍵重疊。 */
const MODIFIERS = ["Shift", "Control", "Alt", "Meta", "OS", "CapsLock", "Fn"];

export const MIN_KEYSTROKES = 150;
export const ROLLOVER_MIN_WPM = 35.0;
export const MIN_HUMAN_DWELL_MS = 5.0;
/**
 * 同鍵重疊只看「緊接著」的重按，且間隔要落在擬合時的擊鍵間隔窗口（METHOD 3.2）。
 * 短於 20ms 是按鍵彈跳或記錄重複；長於 2 秒是 keyup 遺失，不是手指還按著。
 * 不限定的話，一次遺失的 keyup 會讓之後任何一次按同一鍵都被當成重疊（METHOD 7.3）。
 */
export const SAME_KEY_GAP_MS = [20.0, 2000.0];

export const RULES = {
  same_key_overlap: {
    id: "same_key_overlap",
    what:
      "同一個實體鍵在放開前又緊接著被按下（間隔 20ms 到 2 秒）。手指做不到，" +
      "作業系統的行為也未定義。",
    falsePositive: 0.0004,
  },
  constant_dwell: {
    id: "constant_dwell",
    what:
      "按住時間不像真的：每個鍵按住的時間幾乎完全一樣，或短到物理上不可能。" +
      "真人的 dwell 變異係數沒有低於 0.05 的，中位數也沒有低於 20ms 的。",
    falsePositive: 0.0,
  },
  zero_rollover: {
    id: "zero_rollover",
    what: "完全沒有按鍵重疊。只在 35 WPM 以上套用，因為慢速真人本來就接近零。",
    falsePositive: 0.0016,
  },
};

const startsWithAny = (s, prefixes) => prefixes.some((p) => s.startsWith(p));
const isNav = (code) => startsWithAny(code, NAV_PREFIXES);
const isModifier = (code) => startsWithAny(code, MODIFIERS);

function median(xs) {
  if (xs.length === 0) return 0;
  const s = [...xs].sort((a, b) => a - b);
  return s[Math.floor(s.length / 2)];
}

function cv(xs) {
  if (xs.length < 2) return null;
  const m = xs.reduce((a, b) => a + b, 0) / xs.length;
  if (m <= 0) return null;
  const v = xs.reduce((a, b) => a + (b - m) * (b - m), 0) / xs.length;
  return Math.sqrt(v) / m;
}

const round = (x, d) => {
  const f = 10 ** d;
  return Math.round(x * f) / f;
};

/**
 * 把事件配成按下與放開的區間，並數出同鍵重疊。
 *
 * 事件一律先按時間戳排序：瀏覽器的派送順序與時間戳不一致，實測看過時間戳較早的
 * keyup 在較晚的事件之後才送達。
 */
function pair(events) {
  const ordered = [...events].sort((a, b) => a[0] - b[0]);
  const down = new Map();
  const presses = [];
  let overlaps = 0;
  let last = null; // 上一個非修飾鍵的 keydown

  for (const [t, kind, code] of ordered) {
    if (kind !== "D" && kind !== "U") {
      throw new TypeError(`事件類型必須是 'D' 或 'U'，收到 ${JSON.stringify(kind)}`);
    }
    if (kind === "D") {
      // 修飾鍵排除在外：左右 Shift 常被正規化成同一個名字，那會製造假的重疊
      if (down.has(code) && code === last) {
        const gap = t - down.get(code);
        if (gap >= SAME_KEY_GAP_MS[0] && gap <= SAME_KEY_GAP_MS[1]) overlaps += 1;
      }
      down.set(code, t);
      if (!isModifier(code)) last = code;
    } else {
      const start = down.get(code);
      if (start !== undefined) {
        down.delete(code);
        presses.push([start, t, code]);
      }
    }
  }

  presses.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  return { presses, overlaps };
}

/**
 * 檢查一段擊鍵事件。
 *
 * @param {Array<[number, "D"|"U", string, string?]>} events
 *   (毫秒, 按下或放開, 實體鍵碼, 可省略的 key)。**鍵碼必須是實體鍵**
 *   （瀏覽器的 event.code），不是字元，否則同鍵重疊那條判準會失準。
 *   按住不放產生的自動重複（event.repeat 為真的 keydown）不是擊鍵，收集時就要丟掉。
 * @param {{ minKeystrokes?: number }} [options]
 * @returns {Report}
 */
export function check(events, options = {}) {
  const minKeystrokes = options.minKeystrokes ?? MIN_KEYSTROKES;
  const { presses, overlaps } = pair(events);
  const text = presses.filter((p) => !isNav(p[2]));

  if (text.length < minKeystrokes) {
    return {
      verdict: "insufficient-data",
      flags: [],
      measures: {},
      nKeystrokes: text.length,
      note:
        `只有 ${text.length} 次擊鍵，低於 ${minKeystrokes} 的門檻。` +
        `樣本不足時所有統計都不可靠，不應據此下任何結論。`,
      falsePositiveBudget: 0,
    };
  }

  const dwell = text.map(([d, u]) => u - d);
  const iki = text.slice(1).map((p, i) => p[0] - text[i][0]);
  const rollover = text.slice(1).filter((p, i) => p[0] < text[i][1]).length;
  const meanIki = iki.length ? iki.reduce((a, b) => a + b, 0) / iki.length : 0;
  const wpm = meanIki > 0 ? 12000 / meanIki : 0;
  const dwellCv = cv(dwell);
  const dwellMedian = median(dwell);

  const flags = [];
  if (overlaps > 0) flags.push("same_key_overlap");
  // 變異係數在 dwell 全為零時無定義，而全為零正是最退化的合成輸入，所以要另外擋。
  if (dwellMedian < MIN_HUMAN_DWELL_MS || (dwellCv !== null && dwellCv < 0.05)) {
    flags.push("constant_dwell");
  }
  if (rollover === 0 && wpm >= ROLLOVER_MIN_WPM) flags.push("zero_rollover");

  let note =
    "觸發的判準只證明這串輸入不像手打的。沒有觸發也不證明是人，" +
    "刻意模仿真人時序的程式可以通過全部判準。";
  if (flags.length === 0 && wpm < ROLLOVER_MIN_WPM) {
    note += ` 另外此次速度 ${round(wpm, 0)} WPM 低於 ${ROLLOVER_MIN_WPM}，零重疊判準未套用。`;
  }

  return {
    verdict: flags.length ? "synthetic-signals" : "human-consistent",
    flags,
    measures: {
      wpm: round(wpm, 1),
      iki_median_ms: iki.length ? round(median(iki), 1) : null,
      dwell_median_ms: dwell.length ? round(dwellMedian, 1) : null,
      dwell_cv: dwellCv === null ? null : round(dwellCv, 4),
      rollover_pct: iki.length ? round((rollover / iki.length) * 100, 2) : 0,
      same_key_overlaps: overlaps,
    },
    nKeystrokes: text.length,
    note,
    falsePositiveBudget: flags.length
      ? Math.max(...flags.map((f) => RULES[f].falsePositive))
      : 0,
  };
}

/**
 * 把一筆 session（格式見 session_schema.json）轉成 score() 吃的樣本。
 *
 * 秒數與擊鍵數一律從事件流現算，規則與 Python 端的 parse_session() 相同：秒數是
 * 第一次到最後一次按下，擊鍵數只算產生文字的鍵。前端顯示與伺服器重算都該走這裡，
 * 各自再寫一份的話，同一場練習就會有兩個分數。
 *
 * @param {{prompt: string, typed: string, events: Array}} session
 */
export function toSample(session) {
  const events = [...session.events].sort((a, b) => a[0] - b[0]);
  const downs = events.filter((e) => e[1] === "D");
  return {
    prompt: session.prompt,
    typed: session.typed,
    seconds: downs.length > 1 ? (downs[downs.length - 1][0] - downs[0][0]) / 1000 : 0,
    keystrokes: downs.filter((e) => !isNav(e[2])).length,
    events,
  };
}

export {
  METRICS, METRIC_IDS, DEFAULT_METRIC, score, allScores, accuracy, tqcGrade,
} from "./metrics.js";
