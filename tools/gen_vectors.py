#!/usr/bin/env python3
"""產生 vectors.json：Python 與 JS 兩邊共用的測試向量。

兩份實作必須對同一組輸入給出完全相同的輸出，數值逐位相同、說明文字逐字相同。
任一邊改壞，CI 就會失敗。Python 端是規範來源，這個腳本從它產生向量；`--check`
用來驗證檔案是不是最新的。

樣本刻意做小，靠 min_keystrokes 覆寫門檻，這樣 vectors.json 才不會膨脹成幾百 KB。
"""
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from typingnorm import (DEFAULT_METRIC, METRICS, RULES, Session, accuracy,  # noqa: E402
                        all_scores, check, parse_session, tqc_grade)
from typingnorm.detect import (MIN_HUMAN_DWELL_MS, MIN_KEYSTROKES,  # noqa: E402
                               ROLLOVER_MIN_WPM, SAME_KEY_GAP_MS)
from typingnorm.simulate import Clock, HumanTypist, NullMouse, RecordKeyboard  # noqa: E402

MIN = 20   # 向量用的擊鍵門檻，讓案例保持精簡

# 模擬器內部用的鍵物件（可能是 pynput 的列舉，也可能是未安裝時的字串 fallback）
# 必須轉成瀏覽器的實體鍵碼，理由有二：偵測 API 的合約要求實體鍵碼；而且直接
# str() 的結果會隨 pynput 有沒有安裝而變，向量就不再可重現。
_SPECIAL = {
    "space": "Space", "shift": "ShiftLeft", "backspace": "Backspace",
    "enter": "Enter", "ctrl": "ControlLeft", "alt": "AltLeft",
}


def _code(key):
    name = str(key)
    for word, code in _SPECIAL.items():
        if word in name.lower():
            return code
    if len(name) == 1:
        if name.isalpha():
            return f"Key{name.upper()}"
        if name.isdigit():
            return f"Digit{name}"
        return {" ": "Space", ".": "Period", ",": "Comma"}.get(name, "Unidentified")
    return "Unidentified"


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
    ev = [(round(t * 1000, 1), kind, _code(key), "") for t, kind, key in kb.events]
    return ev[:keep]


def paced(n, iki, dwells, rollover_at=None):
    """固定間隔、按住時間輪流取 dwells 的序列；rollover_at 那一鍵按住到下一鍵之後。"""
    ev = []
    for i in range(n):
        t = i * iki
        code = f"Key{chr(65 + i % 26)}"
        dwell = iki + 50.0 if i == rollover_at else dwells[i % len(dwells)]
        ev += [(t, "D", code, ""), (t + dwell, "U", code, "")]
    return ev


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
                "note": r.note,
            },
        })

    add("robot_constant",
        "最常見的自動化寫法：固定間隔、固定停留、零重疊",
        robot())

    add("robot_zero_dwell",
        "按下與放開同時發生。變異係數在此無定義，只靠它會整條溜過去",
        [(i * 120.0, k, "KeyA", "") for i in range(40) for k in ("D", "U")])

    add("same_key_overlap",
        "同一個實體鍵在放開前又緊接著被按下，手指做不到",
        robot() + [(9000.0, "D", "KeyZ", ""), (9050.0, "D", "KeyZ", ""),
                   (9100.0, "U", "KeyZ", ""), (9150.0, "U", "KeyZ", "")])

    add("modifier_double_press_is_not_overlap",
        "左右 Shift 常被正規化成同一個鍵名，實測 2245 人裡有 15 人因此被誤判",
        human() + [(9000.0, "D", "ShiftLeft", ""), (9040.0, "D", "ShiftLeft", ""),
                   (9200.0, "U", "ShiftLeft", "")])

    add("lost_keyup_is_not_overlap",
        "keyup 遺失不是手指還按著：中間隔了別的鍵、或隔了超過 2 秒才再按同一鍵，"
        "都不算重疊。不這樣限定，Aalto 的 2,500 人裡有 25 人會被誤判",
        human() + [(9000.0, "D", "KeyQ", ""),
                   (9200.0, "D", "KeyW", ""), (9280.0, "U", "KeyW", ""),
                   (9400.0, "D", "KeyQ", ""), (9480.0, "U", "KeyQ", ""),
                   (10000.0, "D", "KeyP", ""),
                   (12600.0, "D", "KeyP", ""), (12680.0, "U", "KeyP", "")])

    add("key_bounce_is_not_overlap",
        "20ms 內的重複 keydown 是按鍵彈跳或記錄重複，不是第二次按鍵",
        human() + [(9000.0, "D", "KeyK", ""), (9008.0, "D", "KeyK", ""),
                   (9090.0, "U", "KeyK", "")])

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

    add("measures_round_half_up",
        "32 個間隔裡 1 次重疊是 3.125%，兩邊都要進位成 3.13。"
        "Python 內建的 round() 會給 3.12",
        paced(33, 300.0, (90.0, 110.0, 100.0, 120.0), rollover_at=10))

    add("note_speed_rounds_half_up",
        "平均間隔 960ms 是 12.5 WPM，說明文字裡兩邊都要寫 13",
        paced(21, 960.0, (90.0, 110.0, 100.0, 120.0)))

    return {
        "note": "Python 與 JS 兩份實作的共用測試向量。由 tools/gen_vectors.py 產生。",
        "constants": {
            "min_keystrokes": MIN_KEYSTROKES,
            "rollover_min_wpm": ROLLOVER_MIN_WPM,
            "min_human_dwell_ms": MIN_HUMAN_DWELL_MS,
            "same_key_gap_ms": list(SAME_KEY_GAP_MS),
        },
        "rules": {r.id: {"what": r.what, "false_positive": r.false_positive}
                  for r in RULES.values()},
        "metrics": [{"id": k, "unit": v[1], "authoritative": v[2], "note": v[3]}
                    for k, v in METRICS.items()],
        "default_metric": DEFAULT_METRIC,
        "cases": cases,
        "metric_cases": metric_cases(),
        "tqc_grades": [[v, tqc_grade(v)] for v in (100, 80, 79.9, 30, 29.9, 15, 14.9, 0)],
        "session_cases": session_cases(),
    }


def _expect(s):
    return {"scores": {r["metric"]: r["value"] for r in all_scores(s)},
            "accuracy": accuracy(s)}


def metric_cases():
    """指標的共用案例。有官方標準的對照認證機構的公開門檻，其餘驗證算法本身。"""
    out = []

    def add(name, why, lang, prompt, typed=None, seconds=60, keystrokes=None, events=()):
        s = Session(lang, "", "", "", prompt, typed if typed is not None else prompt,
                    seconds, keystrokes if keystrokes is not None else len(prompt),
                    list(events))
        out.append({
            "name": name, "why": why, "lang": lang,
            "sample": {"prompt": s.prompt, "typed": s.typed, "seconds": s.seconds,
                       "keystrokes": s.keystrokes,
                       "events": [list(e) for e in s.events]},
            "expect": _expect(s),
        })

    pangram = "the quick brown fox jumps over the lazy dog"
    add("ssc_english_35wpm", "SSC CHSL 英文 35 WPM 的正式單位是 10,500 KDPH",
        "en", "x" * 175)
    add("ssc_hindi_30wpm", "印地文 30 WPM 等於 9,000 KDPH", "hi", "x" * 150)
    add("tqc_professional", "TQC 專業級是每分鐘 80 字", "zh-TW", "字" * 80, keystrokes=320)
    add("tqc_error_deduction", "每錯一次扣該列 0.5 字：76 正確、4 錯 → 74",
        "zh-TW", "字" * 80, typed="字" * 76 + "錯" * 4, keystrokes=320)
    add("tqc_invalid_at_10pct", "錯誤率達 10% 該次成績不予計算",
        "zh-TW", "字" * 80, typed="字" * 72 + "錯" * 8, keystrokes=320)
    add("tqc_rounds_half_up", "(75 − 0.5) / 2 分鐘 = 37.25，兩邊都要進位成 37.3",
        "zh-TW", "字" * 76, typed="字" * 75 + "錯", seconds=120, keystrokes=300)
    add("zensho_net_chars", "全商的純字数是総字数減エラー数，錯字只扣一次：100 − 3 = 97",
        "ja", "あ" * 100, typed="あ" * 97 + "い" * 3, keystrokes=250)
    add("korean_tasu_counts_jamo", "한 = ㅎ+ㅏ+ㄴ 三打，只能從擊鍵流算",
        "ko", "한" * 20, keystrokes=60,
        events=[(i * 100.0, "D", "KeyR", c) for i, c in enumerate("ㅎㅏㄴ" * 20)])
    add("tasu_without_key_field", "事件沒有 key 欄位時退回用擊鍵數，不得出錯",
        "ko", "한" * 20, keystrokes=60,
        events=[(i * 100.0, "D", "KeyR") for i in range(60)])
    add("thai_divides_by_four", "泰文一個詞是四個字元，不是英文慣例的五個",
        "th", "ก" * 140)
    add("omission_counts_once", "中間漏打一個字只算一次錯誤，逐位置比對會讓後面全錯",
        "en", pangram, typed=pangram.replace("brown", "brwn"))
    add("insertion_counts_once", "多打一個字只算一次錯誤",
        "en", pangram, typed=pangram.replace("fox", "foxx"))
    add("transposition_counts_twice", "兩字互換算兩次錯誤，其中一個字仍算正確",
        "en", pangram, typed=pangram.replace("lazy", "lzay"))
    add("typed_past_the_end", "打超過題目的部分是多打", "en", "abc" * 10,
        typed="abc" * 10 + "abc")
    return out


def session_cases():
    """session → 樣本的換算。前端、伺服器、分析端都必須從同一份事件流得到同一組數字。"""
    out = []

    def add(name, why, session):
        s = parse_session(session)
        out.append({"name": name, "why": why, "session": session,
                    "expect": {"seconds": s.seconds, "keystrokes": s.keystrokes, **_expect(s)}})

    def session(lang, script, prompt, typed, events):
        return {"schema": 1, "session_id": "vector", "locale": {
                    "language": lang, "script": script, "input_method": "direct",
                    "layout": "qwerty"},
                "prompt": prompt, "typed": typed, "events": events}

    ev = [[0.0, "D", "ShiftLeft", "Shift"], [40.0, "D", "KeyH", "H"], [95.0, "U", "KeyH", "H"],
          [120.0, "U", "ShiftLeft", "Shift"], [210.0, "D", "KeyI", "i"],
          [260.0, "U", "KeyI", "i"], [400.0, "D", "KeyX", "x"], [470.0, "U", "KeyX", "x"],
          [650.0, "D", "Backspace", "Backspace"], [720.0, "U", "Backspace", "Backspace"],
          [900.0, "D", "ArrowLeft", "ArrowLeft"], [950.0, "U", "ArrowLeft", "ArrowLeft"],
          [1100.0, "D", "Enter", "Enter"], [1480.0, "U", "Enter", "Enter"]]
    add("nav_keys_excluded_and_sorted",
        "Shift、方向鍵、Enter 不算擊鍵，退格算；秒數是第一次到最後一次按下，"
        "不含最後一次放開；事件順序打亂也一樣",
        session("en", "latin", "Hi", "Hi", ev[::-1]))

    ev = [[i * 150.0 + d, k, "KeyG", c] for i, c in enumerate("ㅎㅏㄴㄱㅡㄹ")
          for d, k in ((0.0, "D"), (80.0, "U"))]
    add("korean_jamo_from_events", "타수 從事件流的 key 欄位數字母鍵",
        session("ko", "hangul", "한글", "한글", ev))

    example = json.loads((ROOT / "examples" / "zh-TW-zhuyin.json").read_text("utf-8"))
    add("example_zh_tw_zhuyin", "examples/ 裡的注音範例，網站產出的就是這個格式", example)
    return out


def main():
    out = ROOT / "vectors.json"
    data = build()
    text = json.dumps(data, ensure_ascii=False, indent=1) + "\n"

    if "--check" in sys.argv:
        current = out.read_text(encoding="utf-8") if out.exists() else ""
        if current != text:
            print("vectors.json 與 Python 實作不同步，請跑 python3 tools/gen_vectors.py")
            return 1
        print(f"vectors.json 是最新的（{len(data['cases'])} 個判定案例、"
              f"{len(data['metric_cases'])} 個指標案例、{len(data['session_cases'])} 個 session 案例）")
        return 0

    out.write_text(text, encoding="utf-8")
    print(f"寫出 {out.name}：{out.stat().st_size // 1024} KB")
    for c in data["cases"]:
        print(f"  {c['name']:42s} {c['expect']['verdict']:20s} {c['expect']['flags']}")
    for c in data["metric_cases"] + data["session_cases"]:
        print(f"  {c['name']:42s} {c['expect']['scores']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
