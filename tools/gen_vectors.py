#!/usr/bin/env python3
"""產生 vectors.json：Python 與 JS 兩邊共用的測試向量。

兩份實作必須對同一組輸入給出完全相同的判定。任一邊改壞，CI 就會失敗。
Python 端是規範來源，這個腳本從它產生向量；`--check` 用來驗證檔案是不是最新的。

樣本刻意做小，靠 min_keystrokes 覆寫門檻，這樣 vectors.json 才不會膨脹成幾百 KB。
"""
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from typingnorm import check  # noqa: E402
from typingnorm.simulate import Clock, HumanTypist, NullMouse, RecordKeyboard  # noqa: E402

MIN = 20   # 向量用的擊鍵門檻，讓案例保持精簡


def robot(n=40, iki=120.0, dwell=80.0):
    ev = []
    for i in range(n):
        t = i * iki
        code = f"Key{chr(65 + i % 26)}"
        ev += [(t, "D", code, ""), (t + dwell, "U", code, "")]
    return ev


def human(wpm=60, seed=7, keep=60):
    random.seed(seed)
    clock = Clock(real=False)
    kb = RecordKeyboard(clock)
    HumanTypist(kb, NullMouse(), clock, wpm).type_text(
        "In this project I evaluated the primary model output carefully."
    )
    ev = [(round(t * 1000, 1), kind, str(key), "") for t, kind, key in kb.events]
    return ev[:keep]


def build():
    cases = []

    def add(name, why, events, min_keystrokes=MIN):
        r = check(events, min_keystrokes=min_keystrokes)
        cases.append({
            "name": name,
            "why": why,
            "min_keystrokes": min_keystrokes,
            "events": [list(e) for e in events],
            "expect": {
                "verdict": r.verdict,
                "flags": r.flags,
                "measures": r.measures,
                "n_keystrokes": r.n_keystrokes,
            },
        })

    add("robot_constant",
        "最常見的自動化寫法：固定間隔、固定停留、零重疊",
        robot())

    add("robot_zero_dwell",
        "按下與放開同時發生。變異係數在此無定義，只靠它會整條溜過去",
        [(i * 120.0, k, "KeyA", "") for i in range(40) for k in ("D", "U")])

    add("same_key_overlap",
        "同一個實體鍵在放開前又被按下，手指做不到",
        robot() + [(9000.0, "D", "KeyZ", ""), (9050.0, "D", "KeyZ", ""),
                   (9100.0, "U", "KeyZ", ""), (9150.0, "U", "KeyZ", "")])

    add("modifier_double_press_is_not_overlap",
        "左右 Shift 常被正規化成同一個鍵名，實測 2245 人裡有 15 人因此被誤判",
        human() + [(9000.0, "D", "ShiftLeft", ""), (9040.0, "D", "ShiftLeft", ""),
                   (9200.0, "U", "ShiftLeft", "")])

    # 慢速真人：間隔與按住時間都要有真實的變異，否則會踩到 constant_dwell 而
    # 失去這個案例的意義。用固定種子讓向量可重現。
    rng = random.Random(11)
    slow, t = [], 0.0
    for i in range(30):
        code = f"Key{chr(65 + i % 26)}"
        dwell = round(rng.uniform(70, 130), 1)
        slow += [(round(t, 1), "D", code, ""), (round(t + dwell, 1), "U", code, "")]
        t += rng.uniform(360, 520)        # 約 25 到 33 WPM，且從不重疊
    add("slow_typist_zero_rollover_not_flagged",
        "慢速真人本來就可能零重疊。實測零重疊的 7 位真人速度全在 39 WPM 以下，"
        "所以這條判準在 35 WPM 以下不套用",
        slow)

    add("simulated_human_not_flagged",
        "模擬器的輸出分佈對照過 KeyRecs，不得被判成合成",
        human())

    add("shuffled_event_order",
        "瀏覽器派送順序與時間戳不一致，打亂順序結果必須相同",
        list(reversed(robot())))

    add("too_short_abstains",
        "樣本不足要棄權而不是猜",
        robot(n=5))

    return {
        "note": "Python 與 JS 兩份實作的共用測試向量。由 tools/gen_vectors.py 產生。",
        "cases": cases,
    }


def main():
    out = ROOT / "vectors.json"
    data = build()
    text = json.dumps(data, ensure_ascii=False, indent=1) + "\n"

    if "--check" in sys.argv:
        current = out.read_text(encoding="utf-8") if out.exists() else ""
        if current != text:
            print("vectors.json 與 Python 實作不同步，請跑 python3 tools/gen_vectors.py")
            return 1
        print(f"vectors.json 是最新的（{len(data['cases'])} 個案例）")
        return 0

    out.write_text(text, encoding="utf-8")
    print(f"寫出 {out.name}：{len(data['cases'])} 個案例，{out.stat().st_size // 1024} KB")
    for c in data["cases"]:
        print(f"  {c['name']:42s} {c['expect']['verdict']:20s} {c['expect']['flags']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
