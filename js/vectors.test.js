/**
 * 跨語言一致性測試。
 *
 * vectors.json 由 Python 端產生（規範來源），這裡驗證 JS 實作對同一組輸入給出
 * 相同的判定。兩份實作只要走鐘，這個測試就會失敗。
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import test from "node:test";
import assert from "node:assert/strict";

import { check, score } from "./index.js";

const here = dirname(fileURLToPath(import.meta.url));
const { cases } = JSON.parse(readFileSync(join(here, "..", "vectors.json"), "utf8"));

test("vectors.json 有案例可跑", () => {
  assert.ok(cases.length >= 8, `只有 ${cases.length} 個案例`);
});

for (const c of cases) {
  test(`向量：${c.name}`, () => {
    const r = check(c.events, { minKeystrokes: c.min_keystrokes });

    assert.equal(r.verdict, c.expect.verdict, c.why);
    assert.deepEqual(r.flags, c.expect.flags, c.why);
    assert.equal(r.nKeystrokes, c.expect.n_keystrokes);

    // 數值容許極小的浮點與捨入差異，判定本身則必須完全一致
    for (const [k, want] of Object.entries(c.expect.measures)) {
      const got = r.measures[k];
      if (want === null) {
        assert.equal(got, null, `${c.name}.${k}`);
      } else {
        assert.ok(
          Math.abs(got - want) <= Math.max(0.05, Math.abs(want) * 1e-6),
          `${c.name}.${k}: JS ${got} vs Python ${want}`,
        );
      }
    }
  });
}

// 指標：兩邊對同一個樣本必須算出相同數字
const metricCases = JSON.parse(
  readFileSync(join(here, "..", "vectors.json"), "utf8"),
).metric_cases ?? [];

test("vectors.json 有指標案例", () => {
  assert.ok(metricCases.length >= 7, `只有 ${metricCases.length} 個`);
});

for (const c of metricCases) {
  test(`指標向量：${c.name}`, () => {
    for (const [metric, want] of Object.entries(c.expect)) {
      const got = score(c.sample, c.lang, metric).value;
      assert.ok(
        Math.abs(got - want) <= 0.05,
        `${c.name}.${metric}: JS ${got} vs Python ${want}（${c.why}）`,
      );
    }
  });
}
