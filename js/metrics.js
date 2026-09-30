/**
 * 打字速度指標。每個語言有當地慣用的算法，呼叫端也可以切換成別的。
 *
 * 這是 Python 版 `typingnorm.metrics` 的對應實作，兩邊必須給出相同數字。
 * repo 根的 vectors.json 有共用的測試案例，任一邊走鐘 CI 就會失敗。
 *
 * 分數永遠不該儲存，只從原始事件現算。存了分數，之後換算法就得重收資料。
 * `authoritative` 為 false 的指標，介面上不得出現「合格」「專業級」這類字眼，
 * 因為那個語言根本沒有可以合格的標準。
 */

/** 韓文字母。타수 是按字母鍵計數（한 = ㅎ+ㅏ+ㄴ 三打），只能從擊鍵流算。 */
const HANGUL_JAMO = /[ㄱ-ㅣ]/;

const chars = (s) => [...s];

let last = { prompt: null, typed: null, result: null };

/**
 * [正確字數, 錯誤數]。以最少的錯打、多打、漏打把輸入對齊到題目。
 *
 * 逐位置比對的話，中間漏打一個字，後面每個字都會算錯。錯誤數相同的對齊有很多種，
 * 取正確字最多的那個，與 Python 端的 _diff() 同一個規則，兩邊的數字才會一樣。
 * 一次算分會對同一組字串問好幾次，所以記住上一次的結果。
 */
function diff(prompt, typed) {
  if (last.prompt === prompt && last.typed === typed) return last.result;
  const a = chars(prompt);
  const b = chars(typed);
  const n = Math.min(a.length, b.length);
  let head = 0;
  while (head < n && a[head] === b[head]) head++;
  let tail = 0;
  while (tail < n - head && a[a.length - 1 - tail] === b[b.length - 1 - tail]) tail++;
  const code = (c) => c.codePointAt(0);
  const x = Int32Array.from(a.slice(head, a.length - tail), code);
  const y = Int32Array.from(b.slice(head, b.length - tail), code);

  // 每格是 (錯誤數, 正確字數)：先求錯誤最少，再求正確最多。
  // 網站在打字過程中每次重繪都會算分，所以用型別陣列，650 字的段落也只要幾毫秒。
  const w = y.length + 1;
  let pe = new Int32Array(w).map((_, j) => j);
  let pm = new Int32Array(w);
  let ce = new Int32Array(w);
  let cm = new Int32Array(w);
  for (let i = 1; i <= x.length; i++) {
    ce[0] = i;
    cm[0] = 0;
    for (let j = 1; j <= y.length; j++) {
      const same = x[i - 1] === y[j - 1];
      let e = pe[j - 1] + (same ? 0 : 1);
      let m = pm[j - 1] + (same ? 1 : 0);
      if (pe[j] + 1 < e || (pe[j] + 1 === e && pm[j] > m)) {
        e = pe[j] + 1;
        m = pm[j];
      }
      if (ce[j - 1] + 1 < e || (ce[j - 1] + 1 === e && cm[j - 1] > m)) {
        e = ce[j - 1] + 1;
        m = cm[j - 1];
      }
      ce[j] = e;
      cm[j] = m;
    }
    [pe, ce] = [ce, pe];
    [pm, cm] = [cm, pm];
  }
  last = { prompt, typed, result: [head + tail + pm[y.length], pe[y.length]] };
  return last.result;
}

const correct = (sample) => diff(sample.prompt, sample.typed)[0];
const errors = (sample) => diff(sample.prompt, sample.typed)[1];

const minutes = (sample) => Math.max(sample.seconds, 1e-9) / 60;

const jamoKeys = (sample) => {
  if (typeof sample.jamoKeys === "number") return sample.jamoKeys;
  const ev = sample.events ?? [];
  return ev.filter((e) => e[1] === "D" && e[3] && HANGUL_JAMO.test(e[3][0])).length;
};

export const METRICS = {
  cpm_tqc: {
    unit: "字/分", authoritative: true, note: "TQC 中文輸入，專業級 80",
    // 淨字數，每錯一次扣 0.5 字；錯誤率達 10% 該次成績不予計算
    fn: (s) =>
      errors(s) / Math.max(chars(s.prompt).length, 1) >= 0.1
        ? 0
        : Math.max(0, correct(s) - 0.5 * errors(s)) / minutes(s),
  },
  cpm_jp: {
    unit: "字/分", authoritative: true, note: "全商速度部門，1 級 70",
    // 純字数 = 総字数 − エラー数：誤字、脱字、余分字各扣一字，錯字不會被扣兩次
    fn: (s) => Math.max(0, chars(s.prompt).length - errors(s)) / minutes(s),
  },
  tasu: {
    // 韓國通行的單位，但沒有認證機構訂門檻：워드프로세서 考文書編輯，不考打字速度
    unit: "타수", authoritative: false, note: "韓文慣用單位，按字母鍵計數",
    fn: (s) => (jamoKeys(s) || s.keystrokes) / minutes(s),
  },
  kdph_ssc: {
    unit: "KDPH", authoritative: true, note: "SSC 公職考試，10500 = 35 WPM",
    fn: (s) => (s.keystrokes * 3600) / Math.max(s.seconds, 1e-9),
  },
  wpm_net_5: {
    unit: "WPM", authoritative: false, note: "英文慣例，五字元一詞",
    fn: (s) => (correct(s) / 5 - errors(s) / 5) / minutes(s),
  },
  wpm_4: {
    unit: "คำ/นาที", authoritative: false, note: "泰文社群慣例，四字元一詞",
    fn: (s) => (correct(s) / 4 - errors(s) / 4) / minutes(s),
  },
  kpm: {
    unit: "打鍵/分", authoritative: false, note: "跨語言比較用的共同分母",
    fn: (s) => s.keystrokes / minutes(s),
  },
  cpm_raw: {
    unit: "字元/分", authoritative: false, note: "沒有當地標準時的中性預設",
    fn: (s) => correct(s) / minutes(s),
  },
};

export const METRIC_IDS = Object.keys(METRICS);

/** 語言的慣用指標。呼叫端可以覆寫成 METRICS 裡的任何一個。 */
export const DEFAULT_METRIC = {
  "zh-TW": "cpm_tqc", "zh-HK": "cpm_tqc", "zh-CN": "cpm_raw",
  ja: "cpm_jp", ko: "tasu", hi: "kdph_ssc",
  en: "wpm_net_5", ar: "wpm_net_5", th: "wpm_4", vi: "kpm",
};

/**
 * 算分。不指定 metric 就用該語言的慣用指標。
 *
 * @param {{prompt: string, typed: string, seconds: number, keystrokes: number,
 *          events?: Array, jamoKeys?: number}} sample
 * @param {string} lang
 * @param {string} [metric]
 */
export function score(sample, lang, metric) {
  const id = metric ?? DEFAULT_METRIC[lang] ?? "cpm_raw";
  const m = METRICS[id];
  if (!m) throw new RangeError(`未知的指標 ${id}`);
  return {
    metric: id,
    value: Math.round(m.fn(sample) * 10) / 10,
    unit: m.unit,
    authoritative: m.authoritative,
    note: m.note,
  };
}

/** 全部算一遍，給介面切換用。切換只是換一個已算好的值，不用重打。 */
export const allScores = (sample, lang) =>
  METRIC_IDS.map((id) => score(sample, lang, id));

/** 正確率：1 − 錯誤數 / 題目字數，最低為 0。 */
export const accuracy = (sample) =>
  Math.max(0, 1 - errors(sample) / Math.max(chars(sample.prompt).length, 1));

/** TQC 的級別。只有 authoritative 的指標才給得出級別。 */
export function tqcGrade(cpm) {
  if (cpm >= 80) return "專業級";
  if (cpm >= 30) return "進階級";
  if (cpm >= 15) return "實用級";
  return null;
}
