"""打字速度指標。以下常數與規則的來源見 METHOD.md 第 10 節。

每個語言有慣用的算法，使用者也可以切換成別的。

設計前提：**永遠不存分數，只存原始事件**。分數是顯示時才從事件流算出來的。
任何一個地方存了分數，之後換算法就得重收資料。

每個指標都是純函式 (Session) -> float。要加新語言就加一個函式，不動其他東西。

單位的來源分兩種，`authoritative` 欄位標示得很清楚：
  True  出自國家級認證機構，數字對當地人有意義（80 字/分是 TQC 專業級）
  False 業界慣例或本站自訂，介面上不得出現「合格」「專業級」這類字眼

JS 端的 metrics.js 是同一套規則，repo 根的 vectors.json 保證兩邊算出一樣的數字。
"""
import json
import sys
from dataclasses import dataclass, field
from functools import lru_cache

from .detect import _is_nav, _round

# 韓文字母，타수 是按字母鍵計數（한 = ㅎ+ㅏ+ㄴ = 3 타）
HANGUL_JAMO = set(range(0x3131, 0x3164))


@dataclass
class Session:
    """一次練習的原始紀錄。這是唯一被儲存的東西。"""
    language: str                    # zh-TW / en / ja / ko / hi / th ...
    script: str                      # han-trad / latin / kana / hangul / thai ...
    input_method: str                # zhuyin / pinyin / direct / inscript / telex ...
    layout: str                      # qwerty / dachen / kedmanee / dubeolsik ...
    prompt: str                      # 題目原文
    typed: str                       # 實際打出的內容
    seconds: float                   # 從第一次按下到最後一次按下
    keystrokes: int                  # 產生文字的按鍵次數，含修正與組字，不含 Shift 與方向鍵等
    events: list = field(default_factory=list)   # [(t, 'D'|'U', code, key)]

    def correct_chars(self):
        """正確字數：題目與輸入以最少錯誤對齊之後，對得上的字數。"""
        return _diff(self.prompt, self.typed)[0]

    def errors(self):
        """錯打、多打、漏打各算一次錯誤。顛倒字（兩字互換）算兩次，TQC 只算一次。"""
        return _diff(self.prompt, self.typed)[1]

    def minutes(self):
        return max(self.seconds, 1e-9) / 60.0


@lru_cache(maxsize=256)
def _diff(prompt, typed):
    """(正確字數, 錯誤數)。以最少的錯打、多打、漏打把輸入對齊到題目。

    逐位置比對的話，中間漏打一個字，後面每個字都會算錯。錯誤數相同的對齊有很多種，
    取正確字最多的那個，JS 端的 diff() 用同一個規則，兩邊的數字才會一樣。
    """
    head = 0
    while head < min(len(prompt), len(typed)) and prompt[head] == typed[head]:
        head += 1
    tail = 0
    while (tail < min(len(prompt), len(typed)) - head
           and prompt[-1 - tail] == typed[-1 - tail]):
        tail += 1
    a, b = prompt[head:len(prompt) - tail], typed[head:len(typed) - tail]

    # 每格是 (錯誤數, -正確字數)，取字典序最小：先求錯誤最少，再求正確最多
    prev = [(j, 0) for j in range(len(b) + 1)]
    for i, x in enumerate(a, 1):
        cur = [(i, 0)]
        for j, y in enumerate(b, 1):
            e, m = prev[j - 1]
            cur.append(min((e, m - 1) if x == y else (e + 1, m),
                           (prev[j][0] + 1, prev[j][1]),
                           (cur[j - 1][0] + 1, cur[j - 1][1])))
        prev = cur
    e, m = prev[-1]
    return head + tail - m, e


# ---------------------------------------------------------------------------
# 指標實作
# ---------------------------------------------------------------------------

def kpm(s):
    """每分鐘擊鍵數。唯一在所有書寫系統都成立的指標，因為每種文字都用鍵盤打。
    字數與詞數都是各語言自己的抽象，擊鍵數才是共同分母，跨語言比較要用這個。"""
    return s.keystrokes / s.minutes()


def wpm_net_5(s):
    """英文慣例：五個字元算一個詞，淨速度扣掉錯誤。印地文與阿拉伯文沿用。"""
    return (s.correct_chars() / 5 - s.errors() / 5) / s.minutes()


def kdph_ssc(s):
    """印度公職考試的正式單位：每小時按鍵次數。
    SSC CHSL 英文門檻 10,500 KDPH（= 35 WPM），印地文 9,000（= 30 WPM）。
    換算關係 KDPH = WPM × 300。"""
    return s.keystrokes * 3600.0 / max(s.seconds, 1e-9)


def cpm_tqc(s):
    """台灣 TQC 中文輸入：每分鐘淨字數，每錯一次扣 0.5 字。
    錯誤率 ≥ 10% 該次成績不予計算，此處回傳 0 表示不計。
    級別：實用 15、進階 30、專業 80。"""
    total = max(len(s.prompt), 1)
    if s.errors() / total >= 0.10:
        return 0.0
    return max(0.0, s.correct_chars() - 0.5 * s.errors()) / s.minutes()


def cpm_jp(s):
    """日文：純字数／分。全商速度部門 1 級為 10 分鐘純字数 700 字，即 70 字/分。
    純字数 = 総字数 − エラー数：誤字、脱字、余分字各扣一字，錯字不會被扣兩次。"""
    return max(0, len(s.prompt) - s.errors()) / s.minutes()


def tasu(s):
    """韓文 타수：按字母鍵計數，不是按字計數。
    「한」是 ㅎ+ㅏ+ㄴ 三打。所以這個指標只能從擊鍵流算，從輸出文字算不出來。
    韓國通行的單位，但沒有認證機構訂門檻：워드프로세서 考的是文書編輯，不考打字速度，
    坊間流傳的「1 급 300 타」並無官方出處。一般成人 200 到 300。"""
    jamo = sum(1 for e in s.events
               if e[1] == 'D' and len(e) > 3 and e[3] and ord(e[3][0]) in HANGUL_JAMO)
    return (jamo or s.keystrokes) / s.minutes()


def wpm_4(s):
    """泰文慣例：四個字元算一個詞。來源只有社群與練習網站，非官方標準。"""
    return (s.correct_chars() / 4 - s.errors() / 4) / s.minutes()


def cpm_raw(s):
    """每分鐘正確字元數。沒有當地標準時的中性預設。"""
    return s.correct_chars() / s.minutes()


# 順序與 JS 端的 METRIC_IDS 相同，all_scores() 依此排列
METRICS = {
    'cpm_tqc':    (cpm_tqc,    '字/分',    True,  'TQC 中文輸入，專業級 80'),
    'cpm_jp':     (cpm_jp,     '字/分',    True,  '全商速度部門，1 級 70'),
    'tasu':       (tasu,       '타수',     False, '韓文慣用單位，按字母鍵計數'),
    'kdph_ssc':   (kdph_ssc,   'KDPH',     True,  'SSC 公職考試，10500 = 35 WPM'),
    'wpm_net_5':  (wpm_net_5,  'WPM',      False, '英文慣例，五字元一詞'),
    'wpm_4':      (wpm_4,      'คำ/นาที',  False, '泰文社群慣例，四字元一詞'),
    'kpm':        (kpm,        '打鍵/分',  False, '跨語言比較用的共同分母'),
    'cpm_raw':    (cpm_raw,    '字元/分',  False, '沒有當地標準時的中性預設'),
}

# 語言的預設指標。使用者可以切換成 METRICS 裡的任何一個。
DEFAULT_METRIC = {
    'zh-TW': 'cpm_tqc', 'zh-HK': 'cpm_tqc', 'zh-CN': 'cpm_raw',
    'ja': 'cpm_jp', 'ko': 'tasu', 'hi': 'kdph_ssc',
    'en': 'wpm_net_5', 'ar': 'wpm_net_5', 'th': 'wpm_4', 'vi': 'kpm',
}


def score(session, metric=None):
    """算分。不指定就用該語言的慣用指標。"""
    key = metric or DEFAULT_METRIC.get(session.language, 'cpm_raw')
    fn, unit, authoritative, note = METRICS[key]
    return {
        'metric': key, 'value': _round(fn(session), 1), 'unit': unit,
        'authoritative': authoritative, 'note': note,
    }


def all_scores(session):
    """全部算一遍，給切換用。介面只是換一個已經算好的值，不用重打。"""
    return [score(session, k) for k in METRICS]


def accuracy(session):
    """正確率：1 − 錯誤數 / 題目字數，最低為 0。"""
    return max(0.0, 1 - session.errors() / max(len(session.prompt), 1))


def tqc_grade(cpm):
    """TQC 的級別。只有 authoritative 的指標才給得出級別。"""
    if cpm >= 80:
        return '專業級'
    if cpm >= 30:
        return '進階級'
    if cpm >= 15:
        return '實用級'
    return None


# ---------------------------------------------------------------------------

def _demo():
    """對照公開的門檻值驗算，公式錯了這裡就會失敗。"""
    # 印度 SSC：35 WPM 英文應該剛好是 10,500 KDPH
    en = Session('en', 'latin', 'direct', 'qwerty',
                 prompt='x' * 175, typed='x' * 175, seconds=60,
                 keystrokes=175)
    assert abs(score(en, 'wpm_net_5')['value'] - 35.0) < 0.01
    assert abs(score(en, 'kdph_ssc')['value'] - 10500.0) < 1

    # 印地文 30 WPM 應該是 9,000 KDPH
    hi = Session('hi', 'devanagari', 'inscript', 'inscript',
                 prompt='x' * 150, typed='x' * 150, seconds=60, keystrokes=150)
    assert abs(score(hi)['value'] - 9000.0) < 1
    assert score(hi)['authoritative'] is True

    # TQC：80 字全對，一分鐘，應為專業級 80
    tw = Session('zh-TW', 'han-trad', 'zhuyin', 'dachen',
                 prompt='字' * 80, typed='字' * 80, seconds=60, keystrokes=320)
    assert abs(score(tw)['value'] - 80.0) < 0.01
    # 錯四個字：正確 76、錯誤 4，扣 2 字，應為 74
    tw_err = Session('zh-TW', 'han-trad', 'zhuyin', 'dachen',
                     prompt='字' * 80, typed='字' * 76 + '錯' * 4,
                     seconds=60, keystrokes=320)
    assert abs(score(tw_err)['value'] - 74.0) < 0.01
    # 錯誤率達 10% 不予計算
    tw_bad = Session('zh-TW', 'han-trad', 'zhuyin', 'dachen',
                     prompt='字' * 80, typed='字' * 72 + '錯' * 8,
                     seconds=60, keystrokes=320)
    assert score(tw_bad)['value'] == 0.0

    # 全商：10 分鐘純字数 700 字是 1 級，即 70 字/分；錯三字只扣三字
    jp = Session('ja', 'kana', 'romaji', 'qwerty',
                 prompt='あ' * 700, typed='あ' * 697 + 'い' * 3, seconds=600, keystrokes=1400)
    assert abs(score(jp)['value'] - 69.7) < 0.01

    # 韓文：타수 從擊鍵流算。「한」三個字母鍵，打二十次即 60 타/分
    ev = [(i * 100.0, 'D', 'KeyR', c) for i, c in enumerate('ㅎㅏㄴ' * 20)]
    ko = Session('ko', 'hangul', 'direct', 'dubeolsik',
                 prompt='한' * 20, typed='한' * 20, seconds=60,
                 keystrokes=60, events=ev)
    assert abs(score(ko)['value'] - 60.0) < 0.01

    # 同一場練習換指標，值要跟著換，原始資料完全沒動
    assert len({s['metric'] for s in all_scores(tw)}) == len(METRICS)

    print('metrics 自檢通過：SSC / TQC / 全商的門檻換算都對得上')
    print()
    print('同一場練習（TQC 專業級 80 字/分）換成各種指標：')
    for s in all_scores(tw):
        flag = '官方' if s['authoritative'] else '慣例'
        print(f"  {s['metric']:11s} {s['value']:9.1f} {s['unit']:9s} [{flag}] {s['note']}")


def parse_session(d):
    """把網站產出的 session（格式見 session_schema.json）轉成 Session。

    秒數與擊鍵數一律從事件流現算，規則與 JS 端的 toSample() 相同：秒數是第一次到
    最後一次按下，擊鍵數只算產生文字的鍵。欄位缺漏在這裡就會炸，不會拖到分析階段
    才發現。
    """
    for k in ('schema', 'session_id', 'locale', 'prompt', 'typed', 'events'):
        if k not in d:
            raise ValueError(f'session 缺少必填欄位 {k}')
    ev = sorted((tuple(e) for e in d['events']), key=lambda e: e[0])  # 派送順序不可信
    downs = [e for e in ev if e[1] == 'D']
    return Session(
        language=d['locale']['language'], script=d['locale']['script'],
        input_method=d['locale']['input_method'], layout=d['locale']['layout'],
        prompt=d['prompt'], typed=d['typed'],
        seconds=(downs[-1][0] - downs[0][0]) / 1000.0 if len(downs) > 1 else 0.0,
        keystrokes=sum(1 for e in downs if not _is_nav(e[2])), events=ev,
    )


def load_session(path):
    """從 session JSON 檔載入，見 parse_session()。"""
    with open(path, encoding='utf-8') as f:
        return parse_session(json.load(f))


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--json':
        print(json.dumps({k: {'unit': v[1], 'authoritative': v[2], 'note': v[3]}
                          for k, v in METRICS.items()}, ensure_ascii=False, indent=2))
    else:
        _demo()
