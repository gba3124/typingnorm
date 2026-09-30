#!/usr/bin/env python3
"""用 Aalto 136M Keystrokes 當獨立驗證集，量偵測判準的誤判率。

這份資料只讀不用來擬合。任何在這裡看到的數字都不得回頭調整 profile.json，
否則就是測試集污染，授權上也站不住腳。

Aalto 授權：研究與非商業用途，需標註作者。
Dhakal, Feit, Kristensson, Oulasvirta. CHI 2018.

    curl -LO https://userinterfaces.aalto.fi/136Mkeystrokes/data/Keystrokes.zip  # 1.6 GB
    python3 validate/aalto_holdout.py Keystrokes.zip 2500

輸出分兩部分。前半是逐人的結構統計，即 METHOD 7.1 與 7.2 的表；後半直接拿
typingnorm.check() 判定同一批人，即 METHOD 7.3 的表，RULES 裡的誤判率出自這裡。
"""
import random
import statistics
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from typingnorm import RULES, check  # noqa: E402
from typingnorm.simulate import FINGER_MAP  # noqa: E402

IKI_LO, IKI_HI = 0.02, 2.0
DWELL_LO, DWELL_HI = 0.02, 0.6

# LETTER 欄的鍵名。結構統計只看字元、Shift 與退格，其餘鍵名（CAPS_LOCK、方向鍵…）略過
NAMES = {"SHIFT": "Shift", "BKSP": "Backspace"}

# KEYCODE 欄是 JS 的 keyCode，換成 check() 合約要求的實體鍵碼。左右 Shift 都是 16，
# 資料本身分不出來；59、61、173 是 Firefox 的分號、等號、減號。
CODES = {8: "Backspace", 9: "Tab", 13: "Enter", 16: "ShiftLeft", 17: "ControlLeft",
         18: "AltLeft", 20: "CapsLock", 27: "Escape", 32: "Space", 33: "PageUp",
         34: "PageDown", 35: "End", 36: "Home", 37: "ArrowLeft", 38: "ArrowUp",
         39: "ArrowRight", 40: "ArrowDown", 45: "Insert", 46: "Delete", 59: "Semicolon",
         61: "Equal", 91: "MetaLeft", 92: "MetaRight", 93: "ContextMenu", 144: "NumLock",
         173: "Minus", 186: "Semicolon", 187: "Equal", 188: "Comma", 189: "Minus",
         190: "Period", 191: "Slash", 192: "Backquote", 219: "BracketLeft",
         220: "Backslash", 221: "BracketRight", 222: "Quote", 229: "Process",
         **{k: f"Digit{k - 48}" for k in range(48, 58)},
         **{k: f"Key{chr(k)}" for k in range(65, 91)},
         **{k: f"Numpad{k - 96}" for k in range(96, 106)}}


def load(z, name):
    """一位受試者的全部擊鍵：[(句子 ID, LETTER, keyCode, 按下 ms, 放開 ms)]，依檔案順序。"""
    raw = z.read(name)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    rows = []
    for line in text.split("\n")[1:]:
        f = line.rstrip("\r").split("\t")
        if len(f) != 9:
            continue
        try:
            rows.append((f[1], f[7], int(f[8]) if f[8].isdigit() else -1,
                         int(f[5]), int(f[6])))
        except ValueError:
            continue
    return rows


def person_stats(rows):
    """把一位受試者的所有句子彙總成他個人的統計量（單位：秒）。"""
    sections = defaultdict(list)
    for sec, letter, _, p, r in rows:
        k = letter if len(letter) == 1 else NAMES.get(letter)
        if k:
            sections[sec].append((k, p / 1000.0, r / 1000.0))

    iki, ud, dwell = [], [], []
    alt, same = [], []
    same_key_overlap = 0
    for seq in sections.values():
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


def events(rows):
    """轉成 check() 吃的事件流。15 句接成一段，句間的停頓照實保留。"""
    ev = []
    for _, letter, kc, p, r in rows:
        code = CODES.get(kc, f"Unidentified{kc}")
        ev += [(p, "D", code, letter), (r, "U", code, letter)]
    return ev


def main(path='Keystrokes.zip', n_people=2500):
    people, reports = [], []
    with zipfile.ZipFile(path) as z:
        files = [n for n in z.namelist() if n.endswith('_keystrokes.txt')]
        random.seed(1)
        for name in random.sample(files, min(n_people, len(files))):
            rows = load(z, name)
            s = person_stats(rows)
            if s:
                people.append(s)
            reports.append(check(events(rows)))

    n = len(people)
    print(f"獨立驗證集：Aalto 136M Keystrokes，取樣 {len(reports)} 位受試者，"
          f"其中 {n} 位有足夠的結構統計量\n")

    print("== 第一層判準在真人身上的誤判率 ==")
    zero_roll = [p for p in people if p['rollover'] == 0]
    overlap = [p for p in people if p['same_key_overlap'] > 0]
    flat_dwell = [p for p in people if p['dwell_cv'] < 0.05]
    print(f"  rollover 剛好等於 0        {len(zero_roll):5d} / {n}  "
          f"({len(zero_roll)/n*100:.2f}%)")
    print(f"  同一鍵名重疊（含 Shift）   {len(overlap):5d} / {n}  "
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

    judged = [r for r in reports if r.verdict != "insufficient-data"]
    m = len(judged)
    print(f"\n== typingnorm.check() 本身的判定（{m} 人，另 {len(reports) - m} 人樣本不足）==")
    flagged = Counter(f for r in judged for f in r.flags)
    for rule in RULES.values():
        k = flagged[rule.id]
        print(f"  {rule.id:18s} {k:4d} / {m}  ({k/m*100:.2f}%)"
              f"   RULES 記載 {rule.false_positive*100:.2f}%")
    bad = sum(1 for r in judged if r.verdict == "synthetic-signals")
    print(f"  任一判準觸發       {bad:4d} / {m}  ({bad/m*100:.2f}%)")
    slow = sorted(r.measures['wpm'] for r in judged if "zero_rollover" in r.flags)
    if slow:
        print(f"    zero_rollover 觸發者的速度：{slow[0]:.1f} 到 {slow[-1]:.1f} WPM")


if __name__ == '__main__':
    args = sys.argv[1:]
    main(args[0] if args else 'Keystrokes.zip', int(args[1]) if len(args) > 1 else 2500)
