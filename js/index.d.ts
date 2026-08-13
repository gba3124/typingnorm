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

export interface Sample {
  prompt: string;
  typed: string;
  seconds: number;
  keystrokes: number;
  events?: KeyEvent[];
  jamoKeys?: number;
}

export type MetricId =
  | "cpm_tqc" | "cpm_jp" | "tasu" | "kdph_ssc"
  | "wpm_net_5" | "wpm_4" | "kpm" | "cpm_raw";

export interface Score {
  metric: MetricId;
  value: number;
  unit: string;
  /** true 表示出自國家級認證機構，介面才可以顯示「合格」「專業級」 */
  authoritative: boolean;
  note: string;
}

export declare const METRICS: Record<MetricId, {
  unit: string; authoritative: boolean; note: string;
  fn: (s: Sample) => number;
}>;
export declare const METRIC_IDS: MetricId[];
export declare const DEFAULT_METRIC: Record<string, MetricId>;
export declare function score(sample: Sample, lang: string, metric?: MetricId): Score;
export declare function allScores(sample: Sample, lang: string): Score[];
export declare function accuracy(sample: Sample): number;
export declare function tqcGrade(cpm: number): string | null;
