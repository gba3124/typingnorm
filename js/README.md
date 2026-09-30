# typingnorm

Tell whether keystrokes came from a human, and score typing speed with each locale's
own standard. Three detection rules, each with a false-positive rate measured on 2,500
real typists. Zero dependencies, works in the browser.

```bash
npm install typingnorm
```

```js
import { check } from "typingnorm";

// events: [milliseconds, "D" | "U", physical key code, optional event.key]
const report = check(events);

report.verdict              // "human-consistent" | "synthetic-signals" | "insufficient-data"
report.flags                // ["zero_rollover"]
report.measures             // { wpm, rollover_pct, dwell_cv, ... }
report.falsePositiveBudget  // 0.0016
```

Collect events straight from the DOM. Use `event.code`, not `event.key`: the rules
depend on the physical key, and `event.key` changes with the input method. Skip
auto-repeat (`event.repeat`): a held key is one keystroke, not many.

```js
const events = [];
input.addEventListener("keydown", (e) => {
  if (!e.repeat) events.push([e.timeStamp, "D", e.code, e.key]);
});
input.addEventListener("keyup", (e) => events.push([e.timeStamp, "U", e.code, e.key]));
```

## The rules

| Rule | What it catches | False positives on 2,500 humans |
|---|---|---|
| `same_key_overlap` | A physical key pressed again right away, before it was released | 0.04% |
| `constant_dwell` | Every key held for the same time, or too short to be real | 0.00% |
| `zero_rollover` | No key overlap at all (only applied above 35 WPM) | 0.16% |

The rates come from running `check()` itself on 2,500 typists from the Aalto 136M
Keystrokes dataset (METHOD.md section 7.3). A lost `keyup` is not a held key: the
overlap rule only counts a re-press that immediately follows the same key, 20 ms to
2 s later.

Every rule is speed-invariant on purpose. Fast and slow typists differ enormously in
rollover, interval, and hold time, so any "how far from the human average" rule
systematically misjudges people at the extremes. Those are exactly the people you
should not misjudge: password managers, dictation, switch access, and on-screen
keyboards all look robotic in the time domain.

Hand alternation looked like a strong feature and was cut: the effect reverses for
slow typists, so using it as a hard rule misjudges 15.46% of real humans.

## What this does and does not do

It catches careless automation. It does not catch a program that deliberately
imitates human timing, including this project's own simulator.

`check()` returns signals, not a verdict on a person, and deliberately offers no
`isHuman` boolean, because that invites callers to use it as a gate. Treat it as one
input to a risk score, never as identity verification.

Below 150 keystrokes it returns `insufficient-data` rather than guessing. A login
form gives you twenty or thirty keystrokes, which is not enough for any conclusion.

## Speed metrics

The same raw events can be scored with each locale's own unit. Scores are computed on
display and never stored, so switching metrics never requires retyping.

```js
import { accuracy, allScores, score, toSample, tqcGrade } from "typingnorm";

// session: { prompt, typed, events } as described in session_schema.json
const sample = toSample(session);   // seconds and keystrokes derived from the events
score(sample, "zh-TW");             // { metric: "cpm_tqc", value: 74, unit: "字/分", ... }
score(sample, "zh-TW", "kpm");      // any metric, regardless of language
allScores(sample, "zh-TW");         // every metric, for a switcher
accuracy(sample);                   // 0.95
tqcGrade(74);                       // "進階級"
```

| Metric | Unit | Standard | Official |
|---|---|---|---|
| `cpm_tqc` | 字/分 | TQC Chinese input (Taiwan), professional grade 80 | yes |
| `cpm_jp` | 字/分 | Zensho business document exam (Japan), grade 1 is 70 | yes |
| `tasu` | 타수 | Korean convention, counted per jamo key | no |
| `kdph_ssc` | KDPH | SSC exams (India), 10,500 = 35 WPM | yes |
| `wpm_net_5` | WPM | English convention, five characters per word | no |
| `wpm_4` | คำ/นาที | Thai convention, four characters per word | no |
| `kpm` | 打鍵/分 | Keystrokes per minute, the cross-language denominator | no |
| `cpm_raw` | 字元/分 | Neutral default where no local standard exists | no |

Do not show "pass" or grade labels for metrics whose `authoritative` flag is false:
those languages have no standard to pass. Wrong, extra, and missing characters each
count as one error after aligning the typed text to the prompt, so one skipped
character does not shift everything after it. Recompute scores on the server with
`toSample()` instead of trusting a client-sent number.

## Parity with the Python package

This is a port of `typingnorm` on PyPI. Both implementations run the same test
vectors from `vectors.json` in CI and must agree to the last digit, including
rounding and every message string, so they cannot drift apart.

Method, data sources, and the measured false-positive rates:
[METHOD.md](https://github.com/gba3124/typingnorm/blob/main/METHOD.md).

MIT.
