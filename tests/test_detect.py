"""偵測判準的測試。

關鍵不只是「機器人要被抓到」，更是「真人不能被誤判」，後者才是這套方法會不會
害到人的地方。所以每條判準都同時測正例與反例，而真人的樣本直接用模擬器產生，
因為模擬器的輸出分佈是對照過真實資料集的。
"""
import random

import pytest

from typingnorm import check
from typingnorm.detect import MIN_KEYSTROKES
from typingnorm.simulate import Clock, HumanTypist, NullMouse, RecordKeyboard


TEXT = ("In this project I evaluated the primary model output carefully. "
        "The response provides accurate facts and follows all instructions. ") * 3


def human_events(wpm=60, seed=0):
    """用模擬器產生一段真人樣本。它的分佈已對照 KeyRecs 校準過。"""
    random.seed(seed)
    clock = Clock(real=False)
    kb = RecordKeyboard(clock)
    HumanTypist(kb, NullMouse(), clock, wpm).type_text(TEXT)
    return [(t * 1000, kind, str(key), "") for t, kind, key in kb.events]


def robot_events(n=400, iki=120.0, dwell=80.0):
    """最常見的自動化寫法：固定間隔、固定停留、零重疊。"""
    out = []
    for i in range(n):
        t = i * iki
        out.append((t, "D", f"Key{chr(65 + i % 26)}", ""))
        out.append((t + dwell, "U", f"Key{chr(65 + i % 26)}", ""))
    return out


# ---- 真人不該被誤判 -------------------------------------------------------

@pytest.mark.parametrize("wpm", [30, 40, 50, 60, 70, 80])
@pytest.mark.parametrize("seed", [0, 1, 2])
def test_simulated_human_not_flagged(wpm, seed):
    r = check(human_events(wpm, seed))
    assert r.verdict != "synthetic-signals", (
        f"{wpm} WPM seed={seed} 的模擬真人被誤判：{r.flags} {r.measures}")


def test_slow_typist_with_zero_rollover_is_not_flagged():
    """慢速真人本來就可能完全沒有重疊，這條判準對他們必須不套用。

    實測 Aalto 2,245 人裡零重疊的有 7 位，速度全部在 39 WPM 以下。
    """
    ev = []
    for i in range(300):
        t = i * 420.0            # 約 28 WPM
        ev += [(t, "D", "KeyA", ""), (t + 90, "U", "KeyA", "")]
    r = check(ev)
    assert "zero_rollover" not in r.flags
    assert r.measures["wpm"] < 35


# ---- 合成輸入該被抓到 -----------------------------------------------------

def test_constant_dwell_is_flagged():
    r = check(robot_events())
    assert r.verdict == "synthetic-signals"
    assert "constant_dwell" in r.flags


def test_zero_rollover_is_flagged_at_speed():
    r = check(robot_events())
    assert "zero_rollover" in r.flags
    assert r.measures["rollover_pct"] == 0.0


def test_same_key_overlap_is_flagged():
    """手指無法在放開前再次按下同一個實體鍵。"""
    ev = robot_events()
    ev += [(60000.0, "D", "KeyZ", ""), (60050.0, "D", "KeyZ", ""),
           (60100.0, "U", "KeyZ", ""), (60150.0, "U", "KeyZ", "")]
    r = check(ev)
    assert "same_key_overlap" in r.flags


def test_modifier_double_press_is_not_overlap():
    """左右 Shift 常被正規化成同一個鍵名，那會製造假的同鍵重疊。

    實測 Aalto 2,245 人裡有 15 人因此被誤判，所以修飾鍵必須排除。
    """
    ev = human_events(60, 0)
    ev += [(90000.0, "D", "ShiftLeft", ""), (90040.0, "D", "ShiftLeft", ""),
           (90200.0, "U", "ShiftLeft", "")]
    r = check(ev)
    assert "same_key_overlap" not in r.flags


# ---- 樣本不足要棄權 -------------------------------------------------------

def test_short_sample_abstains():
    r = check(robot_events(n=20))
    assert r.verdict == "insufficient-data"
    assert r.flags == []
    assert r.n_keystrokes < MIN_KEYSTROKES


def test_navigation_keys_do_not_count_as_keystrokes():
    """方向鍵與 Enter 是選字用的，不是產生文字的擊鍵。"""
    ev = [(i * 200.0, k, "ArrowLeft", "") for i in range(300) for k in ("D", "U")]
    r = check(ev)
    assert r.verdict == "insufficient-data"


# ---- 事件順序 -------------------------------------------------------------

def test_events_are_sorted_by_timestamp():
    """瀏覽器的派送順序與時間戳不一致，實測看過較早的 keyup 較晚送達。"""
    ev = robot_events()
    shuffled = ev[::-1]
    assert check(ev).measures == check(shuffled).measures


def test_bad_event_kind_raises():
    with pytest.raises(ValueError):
        check([(0.0, "X", "KeyA", "")])


def test_zero_dwell_is_flagged():
    """按下與放開同時發生是最退化的合成輸入。

    變異係數在 dwell 全為零時無定義，只靠變異係數會讓這種輸入整條溜過去。
    """
    ev = [(i * 120.0, k, "KeyA", "") for i in range(400) for k in ("D", "U")]
    r = check(ev)
    assert "constant_dwell" in r.flags
    assert r.measures["dwell_median_ms"] == 0.0
