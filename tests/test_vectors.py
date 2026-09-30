"""用 vectors.json 驗證 Python 實作。

同一份向量也被 js/vectors.test.js 吃，兩邊必須給出逐位相同的輸出。這個測試抓的是
「改了 Python 卻沒重新產生向量」，CI 另有 gen_vectors.py --check 抓反向的情況。
"""
import json
from pathlib import Path

import pytest

from typingnorm import (DEFAULT_METRIC, METRICS, RULES, Session, accuracy, all_scores,
                        check, parse_session, tqc_grade)
from typingnorm.detect import (MIN_HUMAN_DWELL_MS, MIN_KEYSTROKES, ROLLOVER_MIN_WPM,
                               SAME_KEY_GAP_MS)

VECTORS = json.loads((Path(__file__).resolve().parents[1] / "vectors.json")
                     .read_text(encoding="utf-8"))


def _scores(s):
    return {r["metric"]: r["value"] for r in all_scores(s)}


def test_constants_and_metadata():
    c = VECTORS["constants"]
    assert (MIN_KEYSTROKES, ROLLOVER_MIN_WPM, MIN_HUMAN_DWELL_MS, list(SAME_KEY_GAP_MS)) == (
        c["min_keystrokes"], c["rollover_min_wpm"], c["min_human_dwell_ms"], c["same_key_gap_ms"])
    assert VECTORS["rules"] == {r.id: {"what": r.what, "false_positive": r.false_positive}
                                for r in RULES.values()}
    assert VECTORS["metrics"] == [{"id": k, "unit": v[1], "authoritative": v[2], "note": v[3]}
                                  for k, v in METRICS.items()]
    assert VECTORS["default_metric"] == DEFAULT_METRIC


@pytest.mark.parametrize("case", VECTORS["cases"], ids=lambda c: c["name"])
def test_vector(case):
    events = [tuple(e) for e in case["events"]]
    r = check(events, min_keystrokes=case["min_keystrokes"])
    want = case["expect"]
    assert r.verdict == want["verdict"], case["why"]
    assert r.flags == want["flags"], case["why"]
    assert r.n_keystrokes == want["n_keystrokes"]
    assert r.measures == want["measures"], case["why"]
    assert r.note == want["note"]


@pytest.mark.parametrize("case", VECTORS["metric_cases"], ids=lambda c: c["name"])
def test_metric_vector(case):
    d = case["sample"]
    s = Session(case["lang"], "", "", "", d["prompt"], d["typed"], d["seconds"],
                d["keystrokes"], [tuple(e) for e in d["events"]])
    assert _scores(s) == case["expect"]["scores"], case["why"]
    assert accuracy(s) == case["expect"]["accuracy"]


def test_tqc_grades():
    assert [[v, tqc_grade(v)] for v, _ in VECTORS["tqc_grades"]] == VECTORS["tqc_grades"]


@pytest.mark.parametrize("case", VECTORS["session_cases"], ids=lambda c: c["name"])
def test_session_vector(case):
    s = parse_session(case["session"])
    want = case["expect"]
    assert (s.seconds, s.keystrokes) == (want["seconds"], want["keystrokes"]), case["why"]
    assert _scores(s) == want["scores"]
    assert accuracy(s) == want["accuracy"]
