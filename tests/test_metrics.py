"""速度指標的測試。

每個語言的指標都對照該國認證機構公開的門檻驗算。公式改壞了，這裡就會失敗，
而不是等到有人拿去考試才發現數字不對。門檻的出處見 METHOD.md。
"""
import json
from pathlib import Path

import pytest

from typingnorm import METRICS, Session, all_scores, parse_session, score

ROOT = Path(__file__).resolve().parents[1]


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
    """沒有官方標準的語言不得宣稱合格，介面靠這個旗標把關。

    韓文的 타수 是通行單位，但워드프로세서 考的是文書編輯，沒有打字速度門檻。
    """
    assert METRICS["wpm_4"][2] is False
    assert METRICS["kpm"][2] is False
    assert METRICS["tasu"][2] is False
    assert METRICS["cpm_tqc"][2] is True


def test_omission_does_not_shift_the_rest():
    """中間漏打一個字只是一次錯誤。逐位置比對會讓後面每個字都錯，TQC 直接歸零。"""
    s = sess("zh-TW", "han-trad", "zhuyin", "dachen", "今天天氣很好我想出去走走" * 5,
             typed="今天氣很好我想出去走走" + "今天天氣很好我想出去走走" * 4, keys=240)
    assert (s.correct_chars(), s.errors()) == (59, 1)
    assert score(s)["value"] == pytest.approx(58.5, abs=0.01)


def test_example_session_round_trips():
    """網站產出的 session 檔要能直接被分析端吃進去。"""
    from typingnorm import load_session

    s = load_session(str(ROOT / "examples" / "zh-TW-zhuyin.json"))
    assert s.language == "zh-TW"
    assert s.keystrokes / len(s.prompt) == pytest.approx(4.0, abs=0.1)


def test_session_missing_field_fails_early():
    with pytest.raises(ValueError, match="events"):
        parse_session({"schema": 1, "session_id": "x", "locale": {}, "prompt": "", "typed": ""})


def test_example_session_matches_schema():
    """網站產出的格式就是 session_schema.json。範例不合格，代表兩者之一過時了。"""
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((ROOT / "session_schema.json").read_text(encoding="utf-8"))
    example = json.loads((ROOT / "examples" / "zh-TW-zhuyin.json").read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    validator.validate(example)
    with pytest.raises(jsonschema.ValidationError):   # 分數永遠不落地
        validator.validate({**example, "score": 80.0})
