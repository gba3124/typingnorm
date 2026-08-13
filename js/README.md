# typingnorm

Tell whether keystrokes came from a human. Three rules, each with a false-positive
rate measured on 2,245 real typists. Zero dependencies, works in the browser.

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
report.falsePositiveBudget  // 0.0031
```

Collect events straight from the DOM. Use `event.code`, not `event.key`: the rules
depend on the physical key, and `event.key` changes with the input method.

```js
const events = [];
input.addEventListener("keydown", (e) => {
  if (!e.repeat) events.push([e.timeStamp, "D", e.code, e.key]);
});
input.addEventListener("keyup", (e) => events.push([e.timeStamp, "U", e.code, e.key]));
```

## The rules

| Rule | What it catches | False positives on 2,245 humans |
|---|---|---|
| `same_key_overlap` | A physical key pressed again before release | 0.00% |
| `constant_dwell` | Every key held for the same time, or too short to be real | 0.00% |
| `zero_rollover` | No key overlap at all (only applied above 35 WPM) | 0.31% |

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

## Parity with the Python package

This is a port of `typingnorm` on PyPI. Both implementations run the same test
vectors from `vectors.json` in CI, so they cannot drift apart.

Method, data sources, and the measured false-positive rates:
[METHOD.md](https://github.com/gba3124/typingnorm/blob/main/METHOD.md).

MIT.
