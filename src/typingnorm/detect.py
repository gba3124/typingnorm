"""判斷一段擊鍵輸入是否具有合成的跡象。

設計原則有三條，都是被資料逼出來的，不是選來好看的。

**只用速度不變的判準。** 打字快與慢的人，rollover、間隔、dwell 全都差很多。任何
「離人類平均多遠」的判準都會系統性誤判速度極端的人，那恰好是最不該被誤判的族群。

**優先用物理上不可能，而不是統計上罕見。** 同一個實體鍵不可能在放開前再次按下；
每個鍵按住的時間不可能完全一樣。這類判準跟打字快慢無關。

**回報訊號，不回報布林值。** 一個回傳 is_human 的函式會誘導呼叫端拿它當閘門，而
這種方法只擋得住不用心的自動化。刻意模仿的程式可以通過全部判準。

每條判準的誤判率都拿 check() 本身在 Aalto 136M Keystrokes 的 2,500 位受試者上量過，
見 METHOD.md 第 7.3 節，可用 validate/aalto_holdout.py 重跑。誤判率寫在 RULES 裡，
呼叫端據此決定要不要採信。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Iterable, Literal, Sequence

# 選字、確認、切換輸入法的鍵不是產生文字的擊鍵，一律排除
NAV_PREFIXES = ("Arrow", "Meta", "Shift", "Control", "Alt", "Tab", "Escape",
                "Enter", "Page", "Home", "End", "CapsLock", "Fn", "OS")
# 修飾鍵左右手同碼名的問題：左右 Shift 若被正規化成同一個名字，會產生假的同鍵重疊
MODIFIERS = ("Shift", "Control", "Alt", "Meta", "OS", "CapsLock", "Fn")

MIN_KEYSTROKES = 150      # 低於此樣本數不下任何結論
ROLLOVER_MIN_WPM = 35.0   # 慢速真人本來就接近零重疊，這條判準不適用
MIN_HUMAN_DWELL_MS = 5.0  # 真人 dwell 中位數約 91ms，低於這個值是物理上不可能
# 同鍵重疊只看「緊接著」的重按，且間隔要落在擬合時的擊鍵間隔窗口（METHOD 3.2）。
# 短於 20ms 是按鍵彈跳或記錄重複；長於 2 秒是 keyup 遺失，不是手指還按著。
# 不限定的話，一次遺失的 keyup 會讓之後任何一次按同一鍵都被當成重疊（METHOD 7.3）。
SAME_KEY_GAP_MS = (20.0, 2000.0)

Verdict = Literal["human-consistent", "synthetic-signals", "insufficient-data"]


@dataclass(frozen=True)
class Rule:
    id: str
    what: str
    false_positive: float | None   # check() 在 2,500 位真人上的誤判率，None 表示未量測


RULES = {
    "same_key_overlap": Rule(
        "same_key_overlap",
        "同一個實體鍵在放開前又緊接著被按下（間隔 20ms 到 2 秒）。手指做不到，"
        "作業系統的行為也未定義。",
        0.0004,
    ),
    "constant_dwell": Rule(
        "constant_dwell",
        "按住時間不像真的：每個鍵按住的時間幾乎完全一樣，或短到物理上不可能。"
        "真人的 dwell 變異係數沒有低於 0.05 的，中位數也沒有低於 20ms 的。",
        0.0000,
    ),
    "zero_rollover": Rule(
        "zero_rollover",
        "完全沒有按鍵重疊。只在 35 WPM 以上套用，因為慢速真人本來就接近零。",
        0.0016,
    ),
}


@dataclass
class Report:
    verdict: Verdict
    flags: list[str] = field(default_factory=list)
    measures: dict[str, float | None] = field(default_factory=dict)
    n_keystrokes: int = 0
    note: str = ""

    @property
    def false_positive_budget(self) -> float:
        """觸發的判準當中最高的誤判率。呼叫端用它決定要不要採信這次判定。"""
        rates = [RULES[f].false_positive for f in self.flags
                 if RULES[f].false_positive is not None]
        return max(rates) if rates else 0.0

    def as_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "flags": [{"rule": f, "what": RULES[f].what,
                       "false_positive": RULES[f].false_positive} for f in self.flags],
            "measures": self.measures,
            "n_keystrokes": self.n_keystrokes,
            "note": self.note,
            "false_positive_budget": self.false_positive_budget,
        }


def _round(x: float, digits: int) -> float:
    """與 JS 的 Math.round(x * 10**d) / 10**d 逐位元相同：.5 一律往上進位。

    內建 round() 是銀行家捨入，而且看的是十進位值，兩邊會在 0.625、37.25 這類
    值上差一位，同一場練習在網站與分析端就會是兩個分數。
    """
    f = 10 ** digits
    y = x * f
    if not math.isfinite(y):
        return x
    return math.floor(Fraction(y) + Fraction(1, 2)) / f


def _is_nav(code: str) -> bool:
    return code.startswith(NAV_PREFIXES)


def _is_modifier(code: str) -> bool:
    return code.startswith(MODIFIERS)


def _pair(events: Sequence[tuple]) -> tuple[list[tuple[float, float, str]], int]:
    """把事件配成 (按下, 放開, 鍵碼)。回傳配對結果與同鍵重疊的次數。

    事件一律先按時間戳排序：瀏覽器的派送順序與時間戳不一致，實測看過時間戳較早的
    keyup 在較晚的事件之後才送達。
    """
    ordered = sorted(events, key=lambda e: e[0])
    down: dict[str, float] = {}
    presses: list[tuple[float, float, str]] = []
    overlaps = 0
    last = None   # 上一個非修飾鍵的 keydown

    for t, kind, code, *_ in ordered:
        if kind not in ("D", "U"):
            raise ValueError(f"事件類型必須是 'D' 或 'U'，收到 {kind!r}")
        if kind == "D":
            # 修飾鍵排除在外，因為左右 Shift 常被正規化成同一個名字，
            # 那會製造假的重疊。實測 2,245 人裡有 15 人因此被誤判。
            if (code in down and code == last
                    and SAME_KEY_GAP_MS[0] <= t - down[code] <= SAME_KEY_GAP_MS[1]):
                overlaps += 1
            down[code] = t
            if not _is_modifier(code):
                last = code
        else:
            start = down.pop(code, None)
            if start is not None:
                presses.append((start, t, code))

    presses.sort()
    return presses, overlaps


def _sum(xs: Iterable[float]) -> float:
    """逐項相加，與 JS 的 reduce 相同。Python 3.12 起 sum() 改用補償加法，會差最後一位。"""
    total = 0.0
    for x in xs:
        total += x
    return total


def _cv(xs: Sequence[float]) -> float | None:
    if len(xs) < 2:
        return None
    m = _sum(xs) / len(xs)
    if m <= 0:
        return None
    return math.sqrt(_sum((x - m) * (x - m) for x in xs) / len(xs)) / m


def check(events: Iterable[tuple], min_keystrokes: int = MIN_KEYSTROKES) -> Report:
    """檢查一段擊鍵事件。

    events 是 (時間毫秒, 'D' 或 'U', 實體鍵碼, 可省略的 key) 的序列。**鍵碼必須是
    實體鍵**（瀏覽器的 event.code），不是字元，否則同鍵重疊那條判準會失準。
    按住不放產生的自動重複（event.repeat 為真的 keydown）不是擊鍵，收集時就要丟掉。

    回傳的是訊號不是判決。verdict 為 human-consistent 只代表沒有觸發任何判準，
    不代表對方一定是人：刻意模仿真人時序的程式可以全部通過。
    """
    presses, overlaps = _pair(events)
    text = [p for p in presses if not _is_nav(p[2])]

    if len(text) < min_keystrokes:
        return Report(
            verdict="insufficient-data",
            n_keystrokes=len(text),
            note=f"只有 {len(text)} 次擊鍵，低於 {min_keystrokes} 的門檻。"
                 f"樣本不足時所有統計都不可靠，不應據此下任何結論。",
        )

    dwell = [(u - d) for d, u, _ in text]
    iki = [text[i + 1][0] - text[i][0] for i in range(len(text) - 1)]
    rollover = sum(1 for i in range(len(text) - 1) if text[i + 1][0] < text[i][1])
    mean_iki = _sum(iki) / len(iki) if iki else 0.0
    wpm = 12000.0 / mean_iki if mean_iki > 0 else 0.0
    roll_pct = rollover / len(iki) * 100 if iki else 0.0
    dwell_cv = _cv(dwell)

    flags: list[str] = []
    if overlaps > 0:
        flags.append("same_key_overlap")
    dwell_median = sorted(dwell)[len(dwell) // 2] if dwell else 0.0
    # 變異係數在 dwell 全為零時無定義，而全為零正是最退化的合成輸入，
    # 所以要另外擋。只看變異係數會讓這種輸入整條溜過去。
    if dwell_median < MIN_HUMAN_DWELL_MS or (dwell_cv is not None and dwell_cv < 0.05):
        flags.append("constant_dwell")
    if rollover == 0 and wpm >= ROLLOVER_MIN_WPM:
        flags.append("zero_rollover")

    note = ("觸發的判準只證明這串輸入不像手打的。沒有觸發也不證明是人，"
            "刻意模仿真人時序的程式可以通過全部判準。")
    if not flags and wpm < ROLLOVER_MIN_WPM:
        note += (f" 另外此次速度 {_round(wpm, 0):.0f} WPM 低於 {ROLLOVER_MIN_WPM:.0f}，"
                 f"零重疊判準未套用。")

    return Report(
        verdict="synthetic-signals" if flags else "human-consistent",
        flags=flags,
        measures={
            "wpm": _round(wpm, 1),
            "iki_median_ms": _round(sorted(iki)[len(iki) // 2], 1) if iki else None,
            "dwell_median_ms": _round(dwell_median, 1) if dwell else None,
            "dwell_cv": _round(dwell_cv, 4) if dwell_cv is not None else None,
            "rollover_pct": _round(roll_pct, 2),
            "same_key_overlaps": overlaps,
        },
        n_keystrokes=len(text),
        note=note,
    )
