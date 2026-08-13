"""速度指標的測試。

每個語言的指標都對照該國認證機構公開的門檻驗算。公式改壞了，這裡就會失敗，
而不是等到有人拿去考試才發現數字不對。門檻的出處見 METHOD.md。
"""
import pytest

from typingnorm import METRICS, Session, all_scores, score


def sess(lang, script, im, layout, prompt, typed=None, seconds=60, keys=None, events=()):
    return Session(lang, script, im, layout, prompt, typed if typed is not None else prompt,
                   seconds, keys if keys is not None else len(prompt), list(events))


def test_ssc_english_35_wpm_equals_10500_kdph():
    """SSC CHSL：英文 35 WPM 的正式單位是每小時 10,500 次按鍵。"""
    s = sess("en", "latin", "direct", "qwerty", "x" * 175)
    assert score(s, "wpm_net_5")["value"] == pytest.approx(35.0, abs=0.01)
    assert score(s, "kdph_ssc")["value"] == pytest.approx(10500.0, abs=1)


def test_ssc_hindi_30_wpm_equals_9000_kdph():
    s = sess("hi", "devanagari", "inscript", "inscript", "x" * 150)
    r = score(s)
    assert r["metric"] == "kdph_ssc"
    assert r["value"] == pytest.approx(9000.0, abs=1)
    assert r["authoritative"] is True


def test_tqc_professional_grade():
    """TQC 專業級是每分鐘 80 字。"""
    s = sess("zh-TW", "han-trad", "zhuyin", "dachen", "字" * 80, keys=320)
    assert score(s)["value"] == pytest.approx(80.0, abs=0.01)


def test_tqc_deducts_half_char_per_error():
    """每錯一次扣該列 0.5 字：76 正確、4 錯 → 76 - 2 = 74。"""
    s = sess("zh-TW", "han-trad", "zhuyin", "dachen", "字" * 80,
             typed="字" * 76 + "錯" * 4, keys=320)
    assert score(s)["value"] == pytest.approx(74.0, abs=0.01)


def test_tqc_invalidates_at_ten_percent_errors():
    """錯誤率達 10% 該次成績不予計算。"""
    s = sess("zh-TW", "han-trad", "zhuyin", "dachen", "字" * 80,
             typed="字" * 72 + "錯" * 8, keys=320)
    assert score(s)["value"] == 0.0


def test_korean_tasu_counts_jamo_not_syllables():
    """한 = ㅎ+ㅏ+ㄴ 三打。這個指標只能從擊鍵流算，從輸出文字算不出來。"""
    ev = [(i * 100.0, "D", "KeyR", c) for i, c in enumerate("ㅎㅏㄴ" * 20)]
    s = sess("ko", "hangul", "direct", "dubeolsik", "한" * 20, keys=60, events=ev)
    r = score(s)
    assert r["metric"] == "tasu"
    assert r["value"] == pytest.approx(60.0, abs=0.01)


def test_thai_divides_by_four_not_five():
    """泰文的一個詞是四個字元，不是英文慣例的五個。"""
    s = sess("th", "thai", "direct", "kedmanee", "ก" * 140)
    assert score(s)["metric"] == "wpm_4"
    assert score(s, "wpm_4")["value"] == pytest.approx(35.0, abs=0.01)
    assert score(s, "wpm_net_5")["value"] == pytest.approx(28.0, abs=0.01)


def test_switching_metric_does_not_touch_raw_data():
    """同一份原始資料換指標就換一個數字，這是分數不落地儲存的前提。"""
    s = sess("zh-TW", "han-trad", "zhuyin", "dachen", "字" * 80, keys=320)
    results = all_scores(s)
    assert len({r["metric"] for r in results}) == len(METRICS)
    assert s.typed == "字" * 80


def test_non_authoritative_metrics_are_marked():
    """沒有官方標準的語言不得宣稱合格，介面靠這個旗標把關。"""
    assert METRICS["wpm_4"][2] is False
    assert METRICS["kpm"][2] is False
    assert METRICS["cpm_tqc"][2] is True


def test_example_session_round_trips():
    """網站產出的 session 檔要能直接被分析端吃進去。"""
    from pathlib import Path

    from typingnorm import load_session

    p = Path(__file__).resolve().parents[1] / "examples" / "zh-TW-zhuyin.json"
    s = load_session(str(p))
    assert s.language == "zh-TW"
    assert s.keystrokes / len(s.prompt) == pytest.approx(4.0, abs=0.1)
