export type Verdict = "human-consistent" | "synthetic-signals" | "insufficient-data";
export type RuleId = "same_key_overlap" | "constant_dwell" | "zero_rollover";

/** (毫秒, 按下或放開, 實體鍵碼, 可省略的 event.key) */
export type KeyEvent = [number, "D" | "U", string, string?];

export interface Rule {
  id: RuleId;
  what: string;
  /** 在 Aalto 136M Keystrokes 的 2,245 位受試者上量到的誤判率 */
  falsePositive: number;
}

export interface Measures {
  wpm?: number;
  iki_median_ms?: number | null;
  dwell_median_ms?: number | null;
  dwell_cv?: number | null;
  rollover_pct?: number;
  same_key_overlaps?: number;
}

export interface Report {
  verdict: Verdict;
  flags: RuleId[];
  measures: Measures;
  nKeystrokes: number;
  note: string;
  /** 觸發的判準當中最高的誤判率，呼叫端據此決定要不要採信 */
  falsePositiveBudget: number;
}

export declare const RULES: Record<RuleId, Rule>;
export declare const MIN_KEYSTROKES: number;
export declare const ROLLOVER_MIN_WPM: number;
export declare const MIN_HUMAN_DWELL_MS: number;

export declare function check(
  events: KeyEvent[],
  options?: { minKeystrokes?: number },
): Report;
