/** JS 端自己的單元測試。跨語言一致性另見 vectors.test.js。 */
import { readFileSync } from "node:fs";
import test from "node:test";
import assert from "node:assert/strict";

import * as typingnorm from "./index.js";
import { MIN_KEYSTROKES, RULES, check } from "./index.js";

const robot = (n = 400, iki = 120, dwell = 80) => {
  const ev = [];
  for (let i = 0; i < n; i++) {
    const code = `Key${String.fromCharCode(65 + (i % 26))}`;
    ev.push([i * iki, "D", code, ""], [i * iki + dwell, "U", code, ""]);
  }
  return ev;
};

test("固定延遲的自動化會被標記", () => {
  const r = check(robot());
  assert.equal(r.verdict, "synthetic-signals");
  assert.ok(r.flags.includes("constant_dwell"));
  assert.ok(r.flags.includes("zero_rollover"));
});

test("樣本不足時棄權而不是猜", () => {
  const r = check(robot(10));
  assert.equal(r.verdict, "insufficient-data");
  assert.deepEqual(r.flags, []);
  assert.ok(r.nKeystrokes < MIN_KEYSTROKES);
});

test("方向鍵不算產生文字的擊鍵", () => {
  const ev = [];
  for (let i = 0; i < 300; i++) ev.push([i * 200, "D", "ArrowLeft", ""], [i * 200 + 60, "U", "ArrowLeft", ""]);
  assert.equal(check(ev).verdict, "insufficient-data");
});

test("事件順序打亂結果相同", () => {
  const ev = robot();
  assert.deepEqual(check(ev).measures, check([...ev].reverse()).measures);
});

test("事件類型錯誤要丟例外", () => {
  assert.throws(() => check([[0, "X", "KeyA", ""]]), TypeError);
});

test("誤判預算取觸發判準中的最高值", () => {
  const r = check(robot());
  assert.equal(r.falsePositiveBudget, RULES.zero_rollover.falsePositive);
});

test("每條判準都帶著實測的誤判率", () => {
  for (const rule of Object.values(RULES)) {
    assert.equal(typeof rule.falsePositive, "number");
    assert.ok(rule.falsePositive >= 0 && rule.falsePositive < 0.05);
  }
});

test("index.d.ts 宣告了每一個匯出，也沒有宣告不存在的東西", () => {
  const dts = readFileSync(new URL("./index.d.ts", import.meta.url), "utf8");
  const declared = [...dts.matchAll(/export declare (?:const|function) (\w+)/g)].map((m) => m[1]);
  assert.deepEqual(declared.sort(), Object.keys(typingnorm).sort());
});
