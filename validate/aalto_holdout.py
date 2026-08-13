#!/usr/bin/env python3
"""用 Aalto 136M Keystrokes 當獨立驗證集，量偵測判準的誤判率。

這份資料只讀不用來擬合。任何在這裡看到的數字都不得回頭調整 profile.json，
否則就是測試集污染，授權上也站不住腳。

Aalto 授權：研究與非商業用途，需標註作者。
Dhakal, Feit, Kristensson, Oulasvirta. CHI 2018.
"""
import math
import random
import statistics
import sys
import zipfile
from collections import defaultdict

from fit import FINGER_MAP, load_sections, norm_letter

ZIP = 'Keystrokes.zip'
IKI_LO, IKI_HI = 0.02, 2.0
DWELL_LO, DWELL_HI = 0.02, 0.6


def person_stats(sections):
    """把一個受試者的所有句子彙總成他個人的統計量（單位：秒）。"""
    iki, ud, dwell = [], [], []
    alt, same = [], []
    same_key_overlap = 0

    for _, ks in sections:
        seq = [(norm_letter(l), p / 1000.0, r / 1000.0) for l, p, r in ks]
        seq = [x for x in seq if x[0]]
        for i, (k1, p1, r1) in enumerate(seq):
            if DWELL_LO <= r1 - p1 <= DWELL_HI and len(k1) == 1:
                dwell.append(r1 - p1)
            if i + 1 >= len(seq):
                continue
            k2, p2, _ = seq[i + 1]
            gap = p2 - p1
            if not (IKI_LO <= gap <= IKI_HI):
                continue
            iki.append(gap)
            ud.append(p2 - r1)
            if k1 == k2 and p2 < r1:
                same_key_overlap += 1
            f1, f2 = FINGER_MAP.get(k1.lower()), FINGER_MAP.get(k2.lower())
            if f1 and f2 and gap <= 1.0:
                (alt if f1[0] != f2[0] else same).append(gap)

    if len(iki) < 150 or len(dwell) < 100 or len(alt) < 40 or len(same) < 40:
        return None
    return {
        'wpm': 12.0 / statistics.mean(iki),
        'rollover': sum(1 for x in ud if x < 0) / len(ud),
        'dwell_med': statistics.median(dwell),
        'dwell_cv': statistics.pstdev(dwell) / statistics.mean(dwell),
        'alt_ratio': statistics.median(alt) / statistics.median(same),
        'same_key_overlap': same_key_overlap,
        'n': len(iki),
    }


def main(n_people=2500):
    with zipfile.ZipFile(ZIP) as z:
        files = [n for n in z.namelist() if n.endswith('_keystrokes.txt')]
        random.seed(1)
        sample = random.sample(files, min(n_people, len(files)))
        people = []
        for name in sample:
            try:
                s = person_stats(load_sections(z, name))
            except Exception:
                continue
            if s:
                people.append(s)

    n = len(people)
    print(f"獨立驗證集：Aalto 136M Keystrokes，取樣 {n} 位受試者\n")

    print("== 第一層判準在真人身上的誤判率 ==")
    zero_roll = [p for p in people if p['rollover'] == 0]
    overlap = [p for p in people if p['same_key_overlap'] > 0]
    flat_dwell = [p for p in people if p['dwell_cv'] < 0.05]
    print(f"  rollover 剛好等於 0        {len(zero_roll):5d} / {n}  "
          f"({len(zero_roll)/n*100:.2f}%)")
    print(f"  同一實體鍵重疊             {len(overlap):5d} / {n}  "
          f"({len(overlap)/n*100:.2f}%)")
    print(f"  dwell 變異係數 < 0.05      {len(flat_dwell):5d} / {n}  "
          f"({len(flat_dwell)/n*100:.2f}%)")
    if zero_roll:
        sp = sorted(p['wpm'] for p in zero_roll)
        print(f"    rollover 為 0 的人速度：{sp[0]:.0f} 到 {sp[-1]:.0f} WPM，"
              f"中位 {statistics.median(sp):.0f}")

    print("\n== 換手比值（人跟自己比，與速度無關）==")
    ratios = sorted(p['alt_ratio'] for p in people)
    q = lambda x: ratios[min(n - 1, int(n * x))]
    print(f"  p1 {q(0.01):.3f}  p5 {q(0.05):.3f}  中位 {q(0.5):.3f}  "
          f"p95 {q(0.95):.3f}  p99 {q(0.99):.3f}")
    for thr in (1.00, 1.05, 1.10):
        bad = sum(1 for r in ratios if r >= thr)
        print(f"  以 ratio >= {thr:.2f} 判定非人類，會誤判 {bad}/{n} = {bad/n*100:.2f}%")

    print("\n== 速度極端值的人會不會被誤判 ==")
    people.sort(key=lambda p: p['wpm'])
    for label, grp in (("最慢 5%", people[:max(1, n // 20)]),
                       ("最快 5%", people[-max(1, n // 20):])):
        rr = sorted(p['rollover'] for p in grp)
        ar = sorted(p['alt_ratio'] for p in grp)
        print(f"  {label}（{grp[0]['wpm']:.0f} 到 {grp[-1]['wpm']:.0f} WPM，"
              f"{len(grp)} 人）")
        print(f"    rollover 最低 {rr[0]*100:.2f}%  中位 {statistics.median(rr)*100:.1f}%"
              f"   剛好為 0 的有 {sum(1 for x in rr if x == 0)} 人")
        print(f"    換手比值 中位 {statistics.median(ar):.3f}  "
              f"超過 1 的有 {sum(1 for x in ar if x >= 1)} 人")

    print("\n== 生成模型的泛化檢查（KeyRecs 擬合，Aalto 驗證）==")
    print("  級距   人數   rollover 中位   換手比值中位   dwell 中位")
    band = defaultdict(list)
    for p in people:
        band[10 * round(p['wpm'] / 10)].append(p)
    for b in sorted(band):
        g = band[b]
        if len(g) < 30:
            continue
        print(f"   {b:3d}   {len(g):4d}      {statistics.median([x['rollover'] for x in g])*100:5.1f}%"
              f"         {statistics.median([x['alt_ratio'] for x in g]):.3f}"
              f"        {statistics.median([x['dwell_med'] for x in g])*1000:5.0f}ms")


if __name__ == '__main__':
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 2500)
