#!/usr/bin/env python3
"""從 KeyRecs (CC BY 4.0) 擬合出 profile.json。

速度的定義：WPM = 12 / mean(IKI)。因為打 N 個字元耗時 N*mean(IKI) 秒，
字數 = N/5，所以 WPM = 60/(5*mean_IKI) = 12/mean_IKI。用平均數而不是中位數，
模型才能在給定 WPM 時算出正確的 mu，讓 --wpm 這個旋鈕是準的。
"""
import csv
import json
import math
import statistics
from collections import defaultdict

SRC = 'keyrecs-free.csv'
OUT = 'profile.json'

FINGER_MAP = {
    'q': 'L1', 'a': 'L1', 'z': 'L1', '1': 'L1',
    'w': 'L2', 's': 'L2', 'x': 'L2', '2': 'L2',
    'e': 'L3', 'd': 'L3', 'c': 'L3', '3': 'L3',
    'r': 'L4', 'f': 'L4', 'v': 'L4', 't': 'L4', 'g': 'L4', 'b': 'L4', '4': 'L4', '5': 'L4',
    'y': 'R4', 'h': 'R4', 'n': 'R4', 'u': 'R4', 'j': 'R4', 'm': 'R4', '6': 'R4', '7': 'R4',
    'i': 'R3', 'k': 'R3', ',': 'R3', '8': 'R3',
    'o': 'R2', 'l': 'R2', '.': 'R2', '9': 'R2',
    'p': 'R1', ';': 'R1', "'": 'R1', '/': 'R1', '0': 'R1', '-': 'R1', '=': 'R1',
}

COMMON_WORDS = frozenset("""
the be to of and a in that have i it for not on with he as you do at this but his
by from they we say her she or an will my one all would there their what so up out
if about who get which go me when make can like time no just him know take people
into year your good some could them see other than then now look only come its over
think also back after use two how our work first well way even new want because any
these give day most us is are was were been has had did does said made get got
""".split())

IKI_LO, IKI_HI = 0.02, 2.0        # 排除量測雜訊與長時間離開鍵盤
DWELL_LO, DWELL_HI = 0.02, 0.6


def load():
    """回傳 {(participant, session): [(key, dwell, dd, ud), ...]}，順序即打字順序。"""
    seqs = defaultdict(list)
    with open(SRC) as f:
        for r in csv.DictReader(f):
            try:
                seqs[(r['participant'], r['session'])].append((
                    r['key1'], r['key2'],
                    float(r['DU.key1.key1']),
                    float(r['DD.key1.key2']),
                    float(r['UD.key1.key2']),
                ))
            except (ValueError, TypeError, KeyError):
                continue
    return seqs


def pctile(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(len(xs) * q))]


def main():
    seqs = load()
    n_rows = sum(len(v) for v in seqs.values())

    # ---- 每位受試者的速度 ----
    per_p = defaultdict(list)
    for (p, _), rows in seqs.items():
        per_p[p].extend(dd for _, _, _, dd, _ in rows if IKI_LO <= dd <= IKI_HI)
    wpm_of = {p: 12.0 / statistics.mean(v) for p, v in per_p.items() if len(v) > 200}

    chars_of, bksp_of = defaultdict(int), defaultdict(int)
    dwell = defaultdict(list)
    iki_band, roll_band = defaultdict(list), defaultdict(list)
    trans = defaultdict(list)
    lex, pos = defaultdict(list), defaultdict(list)

    for (p, _), rows in seqs.items():
        if p not in wpm_of:
            continue
        band = 10 * round(wpm_of[p] / 10)

        for k1, k2, du, dd, ud in rows:
            if k1 == 'Backspace':
                bksp_of[p] += 1
            elif len(k1) == 1 or k1 == 'Space':
                chars_of[p] += 1
            if DWELL_LO <= du <= DWELL_HI:
                if len(k1) == 1:
                    dwell['letter'].append(du)
                    dwell['_letter_band_%d' % band].append(du)
                elif k1 in ('Space', 'Shift', 'Backspace'):
                    dwell[k1.lower()].append(du)
            if not (IKI_LO <= dd <= IKI_HI):
                continue
            iki_band[band].append(dd)
            if -0.3 <= ud <= IKI_HI:
                roll_band[band].append(ud)
            if len(k1) == 1 and len(k2) == 1:
                f1, f2 = FINGER_MAP.get(k1.lower()), FINGER_MAP.get(k2.lower())
                if f1 and f2:
                    cls = ('same_finger' if f1 == f2 else
                           'alternate_hand' if f1[0] != f2[0] else 'same_hand')
                    trans[cls].append(dd)

        # ---- 還原單字，量字詞層級效應 ----
        word, gaps, ok = [], [], True
        for k1, k2, du, dd, ud in rows:
            if k1 == 'Space':
                w = ''.join(word).lower()
                if ok and w.isalpha() and 3 <= len(w) <= 14 and len(gaps) == len(word) - 1:
                    cls = 'common_word' if w in COMMON_WORDS else 'rare_word'
                    lex[cls].extend(gaps)
                    for j, g in enumerate(gaps):
                        pos['word_edge' if j in (0, len(gaps) - 1) else 'word_middle'].append(g)
                word, gaps, ok = [], [], True
                continue
            if len(k1) != 1:            # Shift / Backspace / 方向鍵，整個字作廢
                ok = False
                continue
            word.append(k1)
            if len(k2) == 1 and IKI_LO <= dd <= IKI_HI:
                gaps.append(dd)
            elif k2 != 'Space':
                ok = False

    # ---- 倍率正規化：讓頻率加權平均等於 1，這樣乘上去不會改變整體速度 ----
    def normalized(groups):
        med = {k: statistics.median(v) for k, v in groups.items()}
        total = sum(len(v) for v in groups.values())
        wmean = sum(med[k] * len(v) for k, v in groups.items()) / total
        return {k: round(med[k] / wmean, 4) for k in med}, total

    _er = sorted(bksp_of[k] / chars_of[k] for k in chars_of if chars_of[k] > 300)
    trans_mult, trans_n = normalized(trans)
    lex_mult, lex_n = normalized(lex)
    pos_mult, pos_n = normalized(pos)

    # ---- 各速度級距 ----
    bands = {}
    for b in sorted(iki_band):
        v = iki_band[b]
        if len(v) < 20000:      # 樣本太少的級距不進 profile，雜訊會蓋過訊號
            continue
        logs = [math.log(x) for x in v]
        mean = statistics.mean(v)
        d = dwell.get('_letter_band_%d' % b, [])
        ud = roll_band[b]
        bands[str(b)] = {
            'sigma': round(statistics.pstdev(logs), 4),
            'iki_median': round(statistics.median(v), 4),
            'dwell_letter': round(statistics.median(d), 4) if len(d) > 500 else None,
            'cv': round(statistics.pstdev(v) / mean, 3),
            'rollover_pct': round(sum(1 for x in ud if x < 0) / len(ud) * 100, 1),
            'n': len(v),
        }

    # dwell 缺值用鄰近級距補
    known = [(int(k), v['dwell_letter']) for k, v in bands.items() if v['dwell_letter']]
    for k, v in bands.items():
        if v['dwell_letter'] is None:
            v['dwell_letter'] = min(known, key=lambda kv: abs(kv[0] - int(k)))[1]

    profile = {
        'schema': 1,
        'source': {
            'name': 'KeyRecs: A keystroke dynamics and typing pattern recognition dataset',
            'authors': 'Dias, Vitorino, Maia, Sousa, Praça',
            'venue': 'Data in Brief, 2023',
            'doi': '10.1016/j.dib.2023.109509',
            'url': 'https://zenodo.org/records/7886743',
            'license': 'CC BY 4.0',
            'commercial_use': True,
        },
        'sample': {
            'participants': len(wpm_of),
            'digraphs': n_rows,
            'wpm_median': round(statistics.median(wpm_of.values()), 1),
        },
        'speed_definition': (
            '級距以受試者的吞吐量指派：WPM = 12 / mean(IKI)。模型取該級距的 '
            'iki_median 當對數常態的中位數（mu = ln(iki_median)），長尾由停頓層補上，'
            '因為真實 IKI 分佈比對數常態更尖峰厚尾。'
        ),
        'bands': bands,
        'dwell': {
            'letter_sigma': round(statistics.pstdev([math.log(x) for x in dwell['letter']]), 4),
            'space': [round(statistics.median(dwell['space']), 4),
                      round(statistics.pstdev([math.log(x) for x in dwell['space']]), 4)],
            'shift': [round(statistics.median(dwell['shift']), 4),
                      round(statistics.pstdev([math.log(x) for x in dwell['shift']]), 4)],
            'backspace': [round(statistics.median(dwell['backspace']), 4),
                          round(statistics.pstdev([math.log(x) for x in dwell['backspace']]), 4)],
        },
        'error': {
            'backspaces_per_char': [
                round(statistics.median(_er), 4),
                round(_er[len(_er) // 4], 4),
                round(_er[3 * len(_er) // 4], 4),
            ],
            'note': '中位數 / p25 / p75。模型的 error_rate 應校準到重現中位數',
        },
        'transition': trans_mult,
        'lexical': {**lex_mult, **pos_mult},
        'counts': {'transition': trans_n, 'lexical': lex_n, 'position': pos_n,
                   'dwell_letter': len(dwell['letter'])},
    }

    with open(OUT, 'w') as f:
        json.dump(profile, f, indent=2, ensure_ascii=False)

    print(f"受試者 {len(wpm_of)}｜digraph {n_rows}｜速度中位數 "
          f"{profile['sample']['wpm_median']} WPM")
    print(f"\ndwell 中位數  字母 {statistics.median(dwell['letter'])*1000:.0f}ms  "
          f"空白 {statistics.median(dwell['space'])*1000:.0f}ms  "
          f"Shift {statistics.median(dwell['shift'])*1000:.0f}ms  "
          f"退格 {statistics.median(dwell['backspace'])*1000:.0f}ms")
    print(f"\n轉換倍率（已正規化）{trans_mult}  n={trans_n}")
    print(f"字詞倍率 {lex_mult}  n={lex_n}")
    print(f"位置倍率 {pos_mult}  n={pos_n}")
    print("\n級距   sigma  IKI中位  dwell   CV    rollover      n")
    for k, v in bands.items():
        print(f"  {k:>3}  {v['sigma']:.3f}  {v['iki_median']*1000:6.1f}ms "
              f"{v['dwell_letter']*1000:5.1f}ms {v['cv']:.2f}   "
              f"{v['rollover_pct']:5.1f}%  {v['n']:7d}")
    print(f"\n退格/字元 中位 {statistics.median(_er):.4f}  "
          f"p25 {_er[len(_er)//4]:.4f}  p75 {_er[3*len(_er)//4]:.4f}")
    print(f"\n寫出 {OUT}")


if __name__ == '__main__':
    main()
