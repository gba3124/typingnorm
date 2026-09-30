#!/usr/bin/env python3
"""真人打字模擬器。時序參數擬合自公開的擊鍵動態資料集，見 profile.json 與 METHOD.md。

真跑：  python -m typingnorm.simulate --file 文章.txt --wpm 65 --delay 5
乾跑：  python -m typingnorm.simulate --dry-run      # 不碰鍵盤，只印時間統計與對帳
對帳：  python -m typingnorm.simulate --validate     # 輸出分佈與 profile.json 的實測值對帳
自檢：  python -m typingnorm.simulate --selftest     # 驗證修正邏輯與按鍵序列合法性

真跑需要 pynput：pip install "typingnorm[desktop]"。

執行中按 Esc 中止。macOS 需在「系統設定 → 隱私權與安全性 → 輔助使用」
把終端機（或 iTerm）打勾，否則按鍵送不出去。

參數來源：Dias, Vitorino, Maia, Sousa, Praça. KeyRecs: A keystroke dynamics and
typing pattern recognition dataset. Data in Brief, 2023. CC BY 4.0，可商業使用。
https://zenodo.org/records/7886743
"""

import argparse
import json
import ctypes
import ctypes.util
import math
import os
import platform
import random
import sys
import time

try:
    from pynput.keyboard import Key, Controller as KeyboardController, Listener as KeyListener
    from pynput.mouse import Controller as MouseController
except ImportError:  # ponytail: --dry-run / --selftest 不需要真的 pynput
    KeyboardController = MouseController = KeyListener = None

    class Key:
        shift = "<shift>"
        ctrl = "<ctrl>"
        alt = "<alt>"
        space = "<space>"
        enter = "<enter>"
        backspace = "<backspace>"
        esc = "<esc>"

IS_MAC = platform.system() == "Darwin"

# 物理鍵盤相鄰按鍵映射表 (QWERTY)：用來產生「手滑打到隔壁鍵」的真實錯字
QWERTY_NEIGHBORS = {
    'a': ['q', 'w', 's', 'z'], 'b': ['v', 'g', 'h', 'n'], 'c': ['x', 'd', 'f', 'v'],
    'd': ['e', 'r', 'f', 'c', 'x', 's'], 'e': ['w', '3', '4', 'r', 'd', 's'],
    'f': ['r', 't', 'g', 'v', 'c', 'd'], 'g': ['t', 'y', 'h', 'b', 'f', 'v'],
    'h': ['y', 'u', 'j', 'n', 'b', 'g'], 'i': ['u', '8', '9', 'o', 'k', 'j'],
    'j': ['u', 'i', 'k', 'm', 'n', 'h'], 'k': ['i', 'o', 'l', ',', 'm', 'j'],
    'l': ['o', 'p', ';', '.', ',', 'k'], 'm': ['j', 'k', ',', 'n'],
    'n': ['b', 'h', 'j', 'm'], 'o': ['i', '9', '0', 'p', 'l', 'k'],
    'p': ['o', '0', '-', '[', ';', 'l'], 'q': ['1', '2', 'w', 'a'],
    'r': ['e', '4', '5', 't', 'f', 'd'], 's': ['w', 'e', 'd', 'x', 'z', 'a'],
    't': ['r', '5', '6', 'y', 'g', 'f'], 'u': ['y', '7', '8', 'i', 'j', 'h'],
    'v': ['c', 'f', 'g', 'b'], 'w': ['q', '2', '3', 'e', 's', 'a'],
    'x': ['z', 's', 'd', 'c'], 'y': ['t', '6', '7', 'u', 'h', 'g'],
    'z': ['a', 's', 'x'],
}

# 人類手指分配矩陣
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

# 高頻肌肉記憶 N-gram。實測顯示 n-gram 的加速多半已經被「換手輪替」解釋掉了
# （th、he、an 剛好都是左右手交替），所以這裡只留很輕的額外加成。
FAST_NGRAMS = {
    'tion', 'ment', 'able', 'ness', 'ther', 'with', 'have', 'from', 'this', 'that',
    'ion', 'ate', 'ing', 'ent', 'ter', 'her', 'and', 'for', 'tha', 'all', 'ver', 'pro',
    'th', 'he', 'in', 'er', 'an', 're', 'on', 'at', 'en', 'nd', 'ti', 'es', 'or', 'te',
    'of', 'ed', 'ou', 'ar',
}

COMMON_WORDS = frozenset("""
the be to of and a in that have i it for not on with he as you do at this but his
by from they we say her she or an will my one all would there their what so up out
if about who get which go me when make can like time no just him know take people
into year your good some could them see other than then now look only come its over
think also back after use two how our work first well way even new want because any
these give day most us is are was were been has had did does said made get got
""".split())

SHIFT_MAP = {
    'A': 'a', 'B': 'b', 'C': 'c', 'D': 'd', 'E': 'e', 'F': 'f', 'G': 'g', 'H': 'h',
    'I': 'i', 'J': 'j', 'K': 'k', 'L': 'l', 'M': 'm', 'N': 'n', 'O': 'o', 'P': 'p',
    'Q': 'q', 'R': 'r', 'S': 's', 'T': 't', 'U': 'u', 'V': 'v', 'W': 'w', 'X': 'x',
    'Y': 'y', 'Z': 'z',
    '!': '1', '@': '2', '#': '3', '$': '4', '%': '5', '^': '6', '&': '7', '*': '8',
    '(': '9', ')': '0', '_': '-', '+': '=', '{': '[', '}': ']', ':': ';', '"': "'",
    '<': ',', '>': '.', '?': '/', '~': '`', '|': '\\',
}
UNSHIFT_MAP = {v: k for k, v in SHIFT_MAP.items()}

# ---------------------------------------------------------------------------
# 所有時序常數都來自 profile.json，不是手調的。那份檔案由 fit/ 從公開資料集
# 擬合產生，可以自己重跑。這裡只負責讀取與內插。
# ---------------------------------------------------------------------------

def _load_profile():
    """已安裝時讀套件內的副本，開發時讀 repo 根的 profile.json。單一事實來源在後者。"""
    here = os.path.dirname(os.path.abspath(__file__))
    for path in (os.path.join(here, "profile.json"),
                 os.path.join(here, "..", "..", "profile.json")):
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f)
    raise FileNotFoundError("找不到 profile.json")


PROFILE = _load_profile()

_BANDS = {int(k): v for k, v in PROFILE["bands"].items()}
DWELL_SIGMA = PROFILE["dwell"]["letter_sigma"]
DWELL_SPACE = tuple(PROFILE["dwell"]["space"])
DWELL_SHIFT = tuple(PROFILE["dwell"]["shift"])
DWELL_BKSP = tuple(PROFILE["dwell"]["backspace"])

HAND_ALTERNATE = PROFILE["transition"]["alternate_hand"]
HAND_SAME = PROFILE["transition"]["same_hand"]
FINGER_SAME = PROFILE["transition"]["same_finger"]
WORD_COMMON = PROFILE["lexical"]["common_word"]
WORD_RARE = PROFILE["lexical"]["rare_word"]
POS_EDGE = PROFILE["lexical"]["word_edge"]
POS_MID = PROFILE["lexical"]["word_middle"]
BKSP_PER_CHAR = PROFILE["error"]["backspaces_per_char"][0]   # 實測中位數
ERROR_RATE_DEFAULT = 0.046          # 校準到重現上面那個退格率，見 METHOD.md
NGRAM_BONUS = 0.92                  # 唯一沒有實測依據的倍率，見 METHOD.md 的限制一節

# 停頓層會把整體擊鍵間隔的中位數推高約 14%，而資料集的中位數本來就含受試者自己的
# 停頓，所以擊鍵層要先扣掉這個量，模型的「整體」輸出才會對上資料集的「整體」統計。
# 這個係數是拿 --validate 反解出來的，不是猜的；改動停頓層就要重新校準。
PAUSE_MEDIAN_OFFSET = 0.88


def profile_for(wpm):
    """回傳 (mu, sigma, 字母鍵 dwell, 變異係數, rollover 參考值)。

    mu 取該速度級距的實測 IKI 中位數，而不是由吞吐量反推。真實的 IKI 分佈比對數
    常態更尖峰厚尾，若讓對數常態去對平均數，中位數會被推高兩三成。所以擊鍵層負責
    對上分佈的主體，長尾交給認知停頓那層補。

    超出資料涵蓋的 30~80 WPM 時按比例外推，並沿用最接近級距的形狀參數。
    """
    keys = sorted(_BANDS)
    w = min(max(wpm, keys[0]), keys[-1])
    lo = max(k for k in keys if k <= w)
    hi = min(k for k in keys if k >= w)
    f = 0.0 if lo == hi else (w - lo) / (hi - lo)
    pick = lambda name: (_BANDS[lo][name] + (_BANDS[hi][name] - _BANDS[lo][name]) * f)
    median = pick("iki_median") * (w / wpm if wpm > 0 else 1.0)
    return (math.log(median * PAUSE_MEDIAN_OFFSET), pick("sigma"), pick("dwell_letter"),
            pick("cv"), pick("rollover_pct"), median)


def mac_accessibility_ok():
    """問 macOS 這個行程有沒有輔助使用權限；沒有的話 pynput 送的按鍵會被靜靜丟掉。"""
    try:
        lib = ctypes.cdll.LoadLibrary(ctypes.util.find_library("ApplicationServices"))
        return bool(lib.AXIsProcessTrusted())
    except Exception:
        return True  # ponytail: 問不到就別擋路


class Aborted(Exception):
    """使用者按了 Esc。"""


class Clock:
    """真跑時 sleep，乾跑時只累加虛擬時間（所以 --dry-run 是瞬間完成的）。"""

    def __init__(self, real=True):
        self.real = real
        self.t = 0.0
        self.stop = False

    def nap(self, seconds):
        if self.stop:
            raise Aborted()
        if seconds <= 0:
            return
        self.t += seconds
        if self.real:
            time.sleep(seconds)


class RecordKeyboard:
    """乾跑用的假鍵盤：還原成文字緩衝區，順便記錄按下／放開事件供節奏統計。"""

    def __init__(self, clock=None):
        self.buf = []
        self.mods = set()
        self.keystrokes = 0
        self.clock = clock
        self.events = []

    def _stamp(self, kind, k):
        if self.clock is not None:
            self.events.append((self.clock.t, kind, k))

    def press(self, k):
        self._stamp('D', k)
        if k in (Key.shift, Key.ctrl, Key.alt):
            self.mods.add(k)
            return
        self.keystrokes += 1
        if k == Key.backspace:
            if Key.ctrl in self.mods or Key.alt in self.mods:
                while self.buf and self.buf[-1] == ' ':
                    self.buf.pop()
                while self.buf and self.buf[-1] not in ' \n':
                    self.buf.pop()
            elif self.buf:
                self.buf.pop()
        elif k == Key.space:
            self.buf.append(' ')
        elif k == Key.enter:
            self.buf.append('\n')
        elif Key.shift in self.mods:
            self.buf.append(k.upper() if k.isalpha() else UNSHIFT_MAP.get(k, k))
        else:
            self.buf.append(k)

    def release(self, k):
        self._stamp('U', k)
        self.mods.discard(k)

    def type(self, s):
        self.buf.extend(s)
        self.keystrokes += len(s)

    def text(self):
        return ''.join(self.buf)


class NullMouse:
    def move(self, dx, dy):
        pass


class HumanTypist:
    def __init__(self, keyboard, mouse, clock, target_wpm=65,
                 error_rate=ERROR_RATE_DEFAULT, dual_capital_rate=0.005):
        self.kb = keyboard
        self.mouse = mouse
        self.clock = clock
        self.mu, self.sigma, self.dwell_med = profile_for(target_wpm)[:3]
        # 認知停頓也跟著整體流暢度縮放：打字快的人讀稿的語塊更大、頓得更少。
        # 這條沒有實測依據（資料集沒有語意標註，分不出寫作停頓與擊鍵節奏），
        # 是保守的平方根縮放。
        self.pause_scale = math.sqrt(math.exp(self.mu) / 0.160)
        self.error_rate = error_rate
        self.dual_capital_rate = dual_capital_rate
        self.last_char = None
        self.total_typed_chars = 0
        self._held = []  # [(key, 該放開的時刻)]，允許與下一鍵重疊

    # ---------- 底層：按下與放開分開排程，所以會自然產生 rollover ----------

    def _pause(self, lo, hi):
        """認知停頓，隨整體速度縮放。"""
        return random.uniform(lo, hi) * self.pause_scale

    def _lognorm(self, median, sigma):
        return random.lognormvariate(math.log(median), sigma)

    def _dwell(self, kind='letter'):
        if kind == 'letter':
            return self._lognorm(self.dwell_med, DWELL_SIGMA)
        return self._lognorm(*{'space': DWELL_SPACE, 'shift': DWELL_SHIFT,
                               'bksp': DWELL_BKSP}[kind])

    def _release_due(self, until):
        """把到期的按鍵放開，時間推進到各自的放開時刻。"""
        while self._held and self._held[0][1] <= until:
            key, at = self._held.pop(0)
            self.clock.nap(at - self.clock.t)
            self.kb.release(key)

    def _advance(self, seconds):
        """推進時間，途中把到期的按鍵放開。"""
        target = self.clock.t + seconds
        self._release_due(target)
        self.clock.nap(target - self.clock.t)

    def _flush(self):
        self._release_due(float('inf'))

    def _tap(self, key, kind='letter'):
        """按下 key，並排程它在 dwell 之後放開。dwell 比下一鍵的間隔長就會重疊。"""
        self._release_due(self.clock.t)
        for i, (held, _) in enumerate(self._held):
            if held == key:
                # 同一個實體鍵不可能重疊（ll、ss 這種），手指一定要先抬起來
                self._held.pop(i)
                self.kb.release(key)
                break
        self.kb.press(key)
        self._held.append((key, self.clock.t + self._dwell(kind)))
        self._held.sort(key=lambda h: h[1])

    def _type_char(self, char):
        """送出一個字元。大寫與符號要壓 Shift，這段不做重疊以免誤把下個字也變大寫。"""
        if char in SHIFT_MAP:
            self._flush()
            hold = self._dwell('shift')
            letter_dwell = self._dwell('letter')
            lead = max(0.02, (hold - letter_dwell) * random.uniform(0.25, 0.45))
            trail = max(0.02, hold - letter_dwell - lead)
            self.kb.press(Key.shift)
            self.clock.nap(lead)
            self.kb.press(SHIFT_MAP[char])
            self.clock.nap(letter_dwell)
            self.kb.release(SHIFT_MAP[char])
            self.clock.nap(trail)
            self.kb.release(Key.shift)
        elif char == ' ':
            self._tap(Key.space, 'space')
        elif char == '\n':
            self._flush()
            self._tap(Key.enter, 'space')
            self._flush()
        elif char.isascii():
            self._tap(char)
        else:
            self._flush()
            self.kb.type(char)  # ponytail: 非 ASCII（中文等）沒有實體鍵，直接送字
            self.clock.nap(self._dwell('letter'))

    def _backspace(self):
        self._flush()
        self._tap(Key.backspace, 'bksp')
        self._advance(self._lognorm(0.12, 0.45))

    def _delete_entire_word(self):
        """多元修正策略：Ctrl+Backspace（Mac 為 Option+Backspace）整詞刪除。"""
        self._flush()
        modifier = Key.alt if IS_MAC else Key.ctrl
        self.kb.press(modifier)
        self.clock.nap(random.uniform(0.03, 0.07))
        self.kb.press(Key.backspace)
        self.clock.nap(self._dwell('bksp'))
        self.kb.release(Key.backspace)
        self.clock.nap(random.uniform(0.02, 0.05))
        self.kb.release(modifier)

    # ---------- 擊鍵間隔 ----------

    def _iki(self, current_char, word_mult, pos_mult, ngram_mult, fatigue):
        """擊鍵間隔。基礎分佈直接來自實測，倍率也是實測，所以不再另外加人工卡頓。"""
        base = random.lognormvariate(self.mu, self.sigma)

        bio = 1.0
        f1 = FINGER_MAP.get((self.last_char or '').lower())
        f2 = FINGER_MAP.get(current_char.lower())
        if f1 and f2:
            if f1 == f2:
                bio = FINGER_SAME
            elif f1[0] != f2[0]:
                bio = HAND_ALTERNATE
            else:
                bio = HAND_SAME

        return max(0.02, base * bio * word_mult * pos_mult * ngram_mult * fatigue)

    # ---------- 錯誤與修正 ----------

    def _typo_and_fix(self, word, c_idx):
        """手滑打到隔壁鍵，多打 0~2 個字才發現，然後退格重來。回傳是否真的觸發。"""
        char = word[c_idx]
        neighbors = QWERTY_NEIGHBORS.get(char.lower())
        if not neighbors:
            return False

        wrong = random.choice(neighbors)
        self._type_char(wrong.upper() if char.isupper() else wrong)
        self._advance(self._lognorm(0.16, 0.4))

        overrun = min(random.randint(0, 2), len(word) - c_idx - 1)
        for k in range(1, overrun + 1):
            self._type_char(word[c_idx + k])
            self._advance(self._lognorm(0.16, 0.4))

        self._flush()
        self._mouse_micro_jitter(self._pause(0.30, 0.75))  # 眼睛發現錯誤
        for _ in range(overrun + 1):
            self._backspace()
        self._advance(random.uniform(0.10, 0.25))
        return True

    def _dual_capital_and_fix(self, word):
        """偶發「WHat」雙大寫：Shift 放太慢，多打 1~2 個字才發現，整詞或逐字修掉。"""
        self._flush()
        self.kb.press(Key.shift)
        self.clock.nap(random.uniform(0.04, 0.09))
        for c in (SHIFT_MAP[word[0]], SHIFT_MAP[word[1].upper()]):
            self.kb.press(c)
            self.clock.nap(self._dwell('letter'))
            self.kb.release(c)
            self.clock.nap(self._lognorm(0.10, 0.35))
        self.kb.release(Key.shift)

        extra = min(len(word) - 2, random.randint(1, 2))
        for k in range(2, 2 + extra):
            self._type_char(word[k])
            self._advance(self._lognorm(0.16, 0.4))

        self._flush()
        self._mouse_micro_jitter(self._pause(0.45, 0.90))

        if random.random() < 0.5:
            self._delete_entire_word()                       # 整詞砍掉重打
            self._advance(random.uniform(0.15, 0.30))
            rest = word
        else:
            for _ in range(extra + 1):                       # 逐字退到只剩首字
                self._backspace()
            self._advance(random.uniform(0.15, 0.30))
            rest = word[1:]

        for char in rest:
            self._type_char(char)
            self._advance(self._lognorm(0.16, 0.4))
        self._flush()

    # ---------- 停頓 ----------

    def _mouse_micro_jitter(self, duration):
        """思考停頓時，滑鼠 1~3 px 的生理微震，打破「完全靜止」特徵。"""
        end = self.clock.t + duration
        while self.clock.t < end - 1e-9:
            if random.random() < 0.2:
                self.mouse.move(random.randint(-2, 2), random.randint(-2, 2))
            self._advance(min(random.uniform(0.15, 0.45), end - self.clock.t))

    # ---------- 主流程 ----------

    def _type_word(self, word, fatigue):
        core = word.strip('.,!?;:"\'()[]').lower()
        word_mult = WORD_COMMON if core in COMMON_WORDS else WORD_RARE

        c_idx = 0
        while c_idx < len(word):
            char = word[c_idx]

            if random.random() < self.error_rate and self._typo_and_fix(word, c_idx):
                self.last_char = None
                continue  # 不推進 index，退格後重打這個字

            ngram_mult = 1.0
            sub = word[c_idx:].lower()
            for n in (4, 3, 2):
                if sub[:n] in FAST_NGRAMS:
                    ngram_mult = NGRAM_BONUS
                    break
            pos_mult = POS_EDGE if c_idx in (0, len(word) - 2) else POS_MID

            self._type_char(char)
            self.total_typed_chars += 1
            self._advance(self._iki(char, word_mult, pos_mult, ngram_mult, fatigue))
            self.last_char = char
            c_idx += 1

    def type_text(self, text):
        tokens = [t for t in text.replace('\n', ' \n ').split(' ') if t]
        chunk_counter = 0
        chunk_target = random.randint(3, 6)  # 認知語塊：3~6 個單字消化一次緩衝區

        for i, word in enumerate(tokens):
            if word == '\n':
                self._type_char('\n')
                self._advance(self._pause(0.15, 0.40))
                self.last_char = None
                continue

            # 疲勞因子：資料集的作業時間太短，量不到長時間疲勞，這條維持保守估計
            fatigue = 1.0 + (self.total_typed_chars / 3000.0) * 0.12

            trigger_dual_cap = (
                len(word) >= 2
                and word[0] in SHIFT_MAP and word[0].isalpha()
                and word[1].islower()
                and random.random() < self.dual_capital_rate
            )
            if trigger_dual_cap:
                self._dual_capital_and_fix(word)
                self.total_typed_chars += len(word)
                self.last_char = word[-1]
            else:
                self._type_word(word, fatigue)

            chunk_counter += 1
            if chunk_counter >= chunk_target:
                self._mouse_micro_jitter(self._pause(0.40, 1.10))
                chunk_counter = 0
                chunk_target = random.randint(3, 6)

            nxt = tokens[i + 1] if i + 1 < len(tokens) else None
            if nxt is None or nxt == '\n':
                continue

            self._type_char(' ')
            self.last_char = ' '
            # 標點後的重構停頓。資料集沒有語意標註，量不到這層，維持人工估計。
            if word[-1] in '.!?':
                self._mouse_micro_jitter(self._pause(1.8, 3.8))
            elif word[-1] == ',':
                self._advance(self._pause(0.4, 0.9))
            else:
                self._advance(self._iki(' ', WORD_RARE, POS_EDGE, 1.0, fatigue))

        self._flush()


SAMPLE = (
    "In this project, I evaluated the primary model output carefully.\n"
    "The response provides accurate facts, follows all instructions, "
    "and demonstrates strong reasoning capabilities throughout the entire task."
)


def rollover_rate(events):
    """下一鍵在上一鍵放開前就按下去的比例。實測人類在 60 WPM 約 22%。"""
    pending, order = {}, []
    for t, kind, k in events:
        if kind == 'D':
            pending.setdefault(k, []).append(len(order))
            order.append([t, None])
        else:
            q = pending.get(k)
            if q:
                order[q.pop(0)][1] = t
    pairs = [o for o in order if o[1] is not None]
    if len(pairs) < 2:
        return 0.0
    return sum(1 for a, b in zip(pairs, pairs[1:]) if b[0] < a[1]) / (len(pairs) - 1)


IKI_WINDOW = (0.02, 2.0)   # 與擬合時的過濾條件相同，統計才是對等比較


def backspace_rate(events, n_chars):
    """每字元的退格次數，用來跟資料集的錯誤修正行為對帳。"""
    n = sum(1 for _, kind, k in events if kind == 'D' and k == Key.backspace)
    return n / max(n_chars, 1)


def rhythm_report(events, wpm):
    """跟資料集對照。統計窗口刻意跟擬合時一致，否則是拿蘋果比橘子。"""
    presses = [t for t, kind, _ in events if kind == 'D']
    gaps = sorted(b - a for a, b in zip(presses, presses[1:]))
    if len(gaps) < 5:
        return ""
    n = len(gaps)
    p = lambda q: gaps[min(n - 1, int(n * q))] * 1000
    inwin = [g for g in gaps if IKI_WINDOW[0] <= g <= IKI_WINDOW[1]]
    mean = sum(inwin) / len(inwin)
    cv = (sum((g - mean) ** 2 for g in inwin) / len(inwin)) ** 0.5 / mean
    _, _, _, cv_target, roll_target, med_target = profile_for(wpm)
    return (f"擊鍵間隔 中位 {p(0.5):.0f}ms（資料集 {med_target * 1000:.0f}ms）｜"
            f"p10 {p(0.10):.0f}ms｜p90 {p(0.90):.0f}ms\n"
            f"變異係數 {cv:.2f}（資料集 {cv_target:.2f}）｜"
            f"rollover 重疊率 {rollover_rate(events) * 100:.1f}%"
            f"（資料集 {roll_target:.0f}%）")


def run_dry(text, wpm, error_rate, dual_rate, verbose=True):
    clock = Clock(real=False)
    kb = RecordKeyboard(clock)
    typist = HumanTypist(kb, NullMouse(), clock, wpm, error_rate, dual_rate)
    typist.type_text(text)
    if verbose:
        wpm_eff = (len(text) / 5) / (clock.t / 60) if clock.t else 0
        print(f"虛擬耗時 {clock.t:.1f}s｜擊鍵 {kb.keystrokes} 下（原文 {len(text)} 字）｜"
              f"有效速度 {wpm_eff:.1f} WPM")
        print("還原文字：", "✅ 與原文一致" if kb.text() == text else "❌ 不一致")
        print(rhythm_report(kb.events, wpm))
        print(f"退格 {backspace_rate(kb.events, len(text)):.4f} 次/字元"
              f"（資料集 {BKSP_PER_CHAR:.4f}）")
    return kb.text()


def check_key_events(events):
    """同一個鍵不能在還按著的時候又被按一次，否則 OS 收到的按鍵序列是無效的。"""
    down = set()
    for _, kind, k in events:
        if kind == 'D':
            assert k not in down, f"{k!r} 重複按下卻沒先放開"
            down.add(k)
        else:
            down.discard(k)
    assert not down, f"結束時還有鍵沒放開：{down}"


VALIDATE_TEXT = (SAMPLE + " ") * 3


def validate(seeds=40):
    """跨多個亂數種子跑模型，把輸出分佈跟 profile.json 的實測值對帳。

    單一次執行的統計雜訊很大（尤其退格率），所以一定要平均之後才有意義。
    """
    print(f"資料來源：{PROFILE['source']['name']}")
    print(f"授權：{PROFILE['source']['license']}｜"
          f"樣本：{PROFILE['sample']['participants']} 人 / "
          f"{PROFILE['sample']['digraphs']:,} digraph\n")
    print("       擊鍵間隔中位數      變異係數        rollover        退格/字元")
    print("WPM     模型   資料集     模型  資料集     模型  資料集     模型   資料集")

    for wpm in sorted(_BANDS):
        gaps, rolls, bksp, chars = [], [], 0, 0
        for seed in range(seeds):
            random.seed(seed)
            clock = Clock(real=False)
            kb = RecordKeyboard(clock)
            HumanTypist(kb, NullMouse(), clock, wpm).type_text(VALIDATE_TEXT)
            presses = [t for t, kind, _ in kb.events if kind == 'D']
            gaps += [b - a for a, b in zip(presses, presses[1:])]
            rolls.append(rollover_rate(kb.events))
            bksp += sum(1 for _, k, key in kb.events if k == 'D' and key == Key.backspace)
            chars += len(VALIDATE_TEXT)

        _, _, _, cv_ref, roll_ref, med_ref = profile_for(wpm)
        inwin = [g for g in gaps if IKI_WINDOW[0] <= g <= IKI_WINDOW[1]]
        mean = sum(inwin) / len(inwin)
        cv = (sum((g - mean) ** 2 for g in inwin) / len(inwin)) ** 0.5 / mean
        print(f"{wpm:3d}   {sorted(gaps)[len(gaps) // 2] * 1000:6.0f} "
              f"{med_ref * 1000:7.0f}   {cv:8.2f} {cv_ref:6.2f}   "
              f"{sum(rolls) / len(rolls) * 100:6.1f}% {roll_ref:5.1f}%   "
              f"{bksp / chars:8.4f} {BKSP_PER_CHAR:7.4f}")
    random.seed()


def selftest():
    """錯字率開到極高，確認修正後文字還原成原文，且按鍵序列物理上合法。"""
    doubles = "The bookkeeper will follow all committee needs across three offices."
    for seed in range(60):
        for text in (SAMPLE, doubles):
            random.seed(seed)
            clock = Clock(real=False)
            kb = RecordKeyboard(clock)
            wpm = 30 + (seed % 8) * 10
            HumanTypist(kb, NullMouse(), clock, wpm, 0.25, 0.30).type_text(text)
            assert kb.text() == text, f"seed={seed} wpm={wpm} 還原失敗:\n{kb.text()!r}"
            check_key_events(kb.events)
    random.seed()
    print("selftest 通過：60 種種子 × 兩段文字 × 30~100 WPM，"
          "修正後文字都等於原文，按鍵序列也沒有重疊同鍵。")


def main():
    p = argparse.ArgumentParser(description="真人打字模擬器（時序擬合自 KeyRecs，CC BY 4.0）")
    p.add_argument("--file", help="要打的文字檔（不給就用內建範例；用 - 讀 stdin）")
    p.add_argument("--wpm", type=float, default=65,
                   help="目標手指速度 20~100，預設 65（含思考停頓的實際 WPM 會更低）")
    p.add_argument("--error-rate", type=float, default=ERROR_RATE_DEFAULT,
                   help=f"每字錯字機率，預設 {ERROR_RATE_DEFAULT}（校準自資料集的退格率）")
    p.add_argument("--dual-capital-rate", type=float, default=0.01, help="WHat 雙大寫機率")
    p.add_argument("--delay", type=float, default=5, help="開打前的切換視窗倒數秒數")
    p.add_argument("--dry-run", action="store_true", help="不碰鍵盤，只算時間與統計")
    p.add_argument("--selftest", action="store_true", help="驗證修正邏輯與按鍵序列合法性")
    p.add_argument("--validate", action="store_true",
                   help="跨多個種子跑模型，跟 profile.json 的實測值對帳")
    p.add_argument("--seed", type=int, help="固定亂數種子")
    args = p.parse_args()

    if args.selftest:
        selftest()
        return

    if args.validate:
        validate()
        return

    if args.seed is not None:
        random.seed(args.seed)

    if args.file == "-":
        text = sys.stdin.read()
    elif args.file:
        with open(args.file, encoding="utf-8") as f:
            text = f.read()
    else:
        text = SAMPLE
    text = text.rstrip("\n")

    if args.dry_run:
        run_dry(text, args.wpm, args.error_rate, args.dual_capital_rate)
        return

    if KeyboardController is None:
        sys.exit("需要 pynput 才能真的打字：pip install pynput")

    if IS_MAC and not mac_accessibility_ok():
        app = os.environ.get("TERM_PROGRAM", "你的終端機")
        sys.exit(
            f"macOS 沒給輔助使用權限，按鍵會被系統丟掉（所以什麼都不會打出來）。\n"
            f"系統設定 → 隱私權與安全性 → 輔助使用 → 把「{app}」加進去並打勾，\n"
            f"然後完全結束該 App 再重開（改權限後舊行程不會生效）。"
        )

    clock = Clock(real=True)
    typist = HumanTypist(KeyboardController(), MouseController(), clock,
                         args.wpm, args.error_rate, args.dual_capital_rate)

    def on_press(key):
        if key == Key.esc:
            clock.stop = True
            return False

    listener = KeyListener(on_press=on_press)
    listener.start()

    for s in range(int(args.delay), 0, -1):
        print(f"\r{s} 秒後開打，請把游標切到目標輸入框（Esc 可中止）...", end="", flush=True)
        time.sleep(1)
    print("\r開始執行全維度擬真打字（Esc 中止）           ")

    try:
        typist.type_text(text)
        print(f"完成，共 {clock.t:.1f} 秒。")
    except Aborted:
        print("\n已中止。")
    finally:
        try:
            typist._flush()
        except Aborted:
            pass
        listener.stop()


if __name__ == "__main__":
    main()
