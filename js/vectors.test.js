/**
 * 跨語言一致性測試。
 *
 * vectors.json 由 Python 端產生（規範來源），這裡驗證 JS 實作對同一組輸入給出
 * 逐位相同的輸出。兩份實作只要走鐘，這個測試就會失敗。
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import test from "node:test";
import assert from "node:assert/strict";

import {
  DEFAULT_METRIC, METRICS, METRIC_IDS, MIN_HUMAN_DWELL_MS, MIN_KEYSTROKES,
  ROLLOVER_MIN_WPM, RULES, SAME_KEY_GAP_MS, accuracy, allScores, check, toSample,
  tqcGrade,
} from "./index.js";

const here = dirname(fileURLToPath(import.meta.url));
const V = JSON.parse(readFileSync(join(here, "..", "vectors.json"), "utf8"));

// 數值用 === 比對，不留容差：兩邊的捨入規則與浮點運算順序都已對齊，差一位就該失敗
const same = (got, want, what) =>
  assert.ok(got === want, `${what}: JS ${got} vs Python ${want}`);

const scores = (sample, lang) =>
  Object.fromEntries(allScores(sample, lang).map((s) => [s.metric, s.value]));

test("vectors.json 有案例可跑", () => {
  assert.ok(V.cases.length >= 8, `只有 ${V.cases.length} 個判定案例`);
  assert.ok(V.metric_cases.length >= 7, `只有 ${V.metric_cases.length} 個指標案例`);
  assert.ok(V.session_cases.length >= 1, "沒有 session 案例");
});

test("常數與判準說明與 Python 相同", () => {
  const c = V.constants;
  same(MIN_KEYSTROKES, c.min_keystrokes, "min_keystrokes");
  same(ROLLOVER_MIN_WPM, c.rollover_min_wpm, "rollover_min_wpm");
  same(MIN_HUMAN_DWELL_MS, c.min_human_dwell_ms, "min_human_dwell_ms");
  assert.deepEqual(SAME_KEY_GAP_MS, c.same_key_gap_ms);
  assert.deepEqual(Object.keys(RULES), Object.keys(V.rules));
  for (const [id, r] of Object.entries(V.rules)) {
    assert.equal(RULES[id].what, r.what, id);
    same(RULES[id].falsePositive, r.false_positive, `${id}.falsePositive`);
  }
});

test("指標的順序、單位與說明與 Python 相同", () => {
  assert.deepEqual(METRIC_IDS, V.metrics.map((m) => m.id));
  for (const { id, unit, authoritative, note } of V.metrics) {
    const m = METRICS[id];
    assert.deepEqual([m.unit, m.authoritative, m.note], [unit, authoritative, note], id);
  }
  assert.deepEqual(DEFAULT_METRIC, V.default_metric);
});

for (const c of V.cases) {
  test(`向量：${c.name}`, () => {
    const r = check(c.events, { minKeystrokes: c.min_keystrokes });
    assert.equal(r.verdict, c.expect.verdict, c.why);
    assert.deepEqual(r.flags, c.expect.flags, c.why);
    assert.equal(r.nKeystrokes, c.expect.n_keystrokes);
    assert.deepEqual(Object.keys(r.measures), Object.keys(c.expect.measures));
    for (const [k, want] of Object.entries(c.expect.measures)) {
      same(r.measures[k], want, `${c.name}.${k}`);
    }
    assert.equal(r.note, c.expect.note);
  });
}

for (const c of V.metric_cases) {
  test(`指標向量：${c.name}`, () => {
    const got = scores(c.sample, c.lang);
    for (const [id, want] of Object.entries(c.expect.scores)) {
      same(got[id], want, `${c.name}.${id}（${c.why}）`);
    }
    same(accuracy(c.sample), c.expect.accuracy, `${c.name}.accuracy`);
  });
}

test("TQC 級別與 Python 相同", () => {
  for (const [cpm, grade] of V.tqc_grades) assert.equal(tqcGrade(cpm), grade, `${cpm}`);
});

for (const c of V.session_cases) {
  test(`session 向量：${c.name}`, () => {
    const s = toSample(c.session);
    same(s.seconds, c.expect.seconds, `${c.name}.seconds（${c.why}）`);
    same(s.keystrokes, c.expect.keystrokes, `${c.name}.keystrokes（${c.why}）`);
    const got = scores(s, c.session.locale.language);
    for (const [id, want] of Object.entries(c.expect.scores)) {
      same(got[id], want, `${c.name}.${id}`);
    }
    same(accuracy(s), c.expect.accuracy, `${c.name}.accuracy`);
  });
}
