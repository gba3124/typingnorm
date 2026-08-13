"""用 vectors.json 驗證 Python 實作。

同一份向量也被 js/vectors.test.js 吃，兩邊必須給出相同判定。這個測試抓的是
「改了 Python 卻沒重新產生向量」，CI 另有 gen_vectors.py --check 抓反向的情況。
"""
import json
from pathlib import Path

import pytest

from typingnorm import check

VECTORS = json.loads((Path(__file__).resolve().parents[1] / "vectors.json")
                     .read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", VECTORS["cases"], ids=lambda c: c["name"])
def test_vector(case):
    events = [tuple(e) for e in case["events"]]
    r = check(events, min_keystrokes=case["min_keystrokes"])
    assert r.verdict == case["expect"]["verdict"], case["why"]
    assert r.flags == case["expect"]["flags"], case["why"]
    assert r.n_keystrokes == case["expect"]["n_keystrokes"]
    assert r.measures == case["expect"]["measures"]


@pytest.mark.parametrize("case", VECTORS["metric_cases"], ids=lambda c: c["name"])
def test_metric_vector(case):
    from typingnorm import Session, score

    d = case["sample"]
    s = Session(case["lang"], "", "", "", d["prompt"], d["typed"], d["seconds"],
                d["keystrokes"], [tuple(e) for e in d["events"]])
    for metric, want in case["expect"].items():
        assert score(s, metric)["value"] == pytest.approx(want, abs=0.05), case["why"]
