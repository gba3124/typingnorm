# typingnorm

人類打字的常模，以及據此判斷一段輸入是否為真人的判準。

每條判準的誤判率都在一份獨立資料集上量過，數字寫在程式碼裡，方法寫在
[METHOD.md](METHOD.md)，擬合與驗證的腳本都在這個 repo 裡，你可以自己重跑。

```python
from typingnorm import check

report = check(events)      # events: [(毫秒, 'D'|'U', 實體鍵碼, key), ...]，不含自動重複

report.verdict              # 'human-consistent' | 'synthetic-signals' | 'insufficient-data'
report.flags                # ['zero_rollover']
report.measures             # {'wpm': 61.2, 'rollover_pct': 0.0, 'dwell_cv': 0.31, ...}
report.false_positive_budget  # 0.0016，觸發判準當中最高的誤判率
```

鍵碼必須是實體鍵（瀏覽器的 `event.code`），不是字元；按住不放產生的自動重複
（`event.repeat` 為真的 keydown）不是擊鍵，收集時就要丟掉。

## 判準

只有三條，而且都是刻意選的。

| 判準 | 內容 | 在 2,500 位真人上的誤判率 |
|---|---|---|
| `same_key_overlap` | 同一個實體鍵在放開前又緊接著被按下 | 0.04% |
| `constant_dwell` | 每個鍵按住的時間幾乎完全一樣 | 0.00% |
| `zero_rollover` | 完全沒有按鍵重疊（僅 35 WPM 以上套用） | 0.16% |

誤判率是拿 `check()` 本身判定 Aalto 資料集的 2,500 人量到的，見 METHOD.md 第 7.3 節。

選擇的原則是**只用不受打字速度影響的判準**。打字快與慢的人，重疊率、間隔、按住時間
全都差很多，任何「離人類平均多遠」的判準都會系統性誤判速度極端的人，而那恰好是最
不該被誤傷的族群：密碼管理器、語音輸入、切換式存取、螢幕小鍵盤的使用者在時序上都
長得像機器人。

被排除在外的例子：換手比值（左右手交替是否比同手快）看起來是很好的特徵，實測卻在
慢速端反轉，用它當硬判準會誤判 15.46% 的真人。詳見 METHOD.md 第 7.2 節。

## 這個方法擋得住什麼、擋不住什麼

擋得住不用心的自動化。擋不住刻意模仿真人時序的程式，包括本套件自己的模擬器。

所以 `check()` 回傳的是訊號不是判決，也刻意不提供 `is_human` 這種布林值：那會誘導
呼叫端拿它當閘門。請把它當成風險分數的其中一個輸入，不要當成身分驗證。

樣本不足時會回 `insufficient-data` 而不是猜。少於 150 次擊鍵的統計不可靠，登入表單
那種二三十個按鍵的長度做不了任何判斷。

## 速度指標

同一份原始資料可以用不同國家的慣用指標計分，因為分數不儲存，只在顯示時現算。

```python
from typingnorm import accuracy, all_scores, load_session, score, tqc_grade

s = load_session("session.json")   # 或 parse_session(dict)，格式見 session_schema.json
score(s)                    # 依語言自動選當地慣用指標
score(s, "kdph_ssc")        # 換成印度公職考試的單位
all_scores(s)               # 全部指標各算一次，給介面切換用
accuracy(s)                 # 0.97
tqc_grade(score(s)["value"])  # '專業級'，只對 cpm_tqc 有意義
```

| 指標 | 單位 | 出處 | 官方 |
|---|---|---|---|
| `cpm_tqc` | 字/分 | TQC 中文輸入，專業級 80 | 是 |
| `cpm_jp` | 字/分 | 全商速度部門，1 級 70 | 是 |
| `tasu` | 타수 | 韓文慣用單位，按字母鍵計數 | 否 |
| `kdph_ssc` | KDPH | SSC 公職考試，10,500 = 35 WPM | 是 |
| `wpm_net_5` | WPM | 英文慣例，五字元一詞 | 否 |
| `wpm_4` | คำ/นาที | 泰文慣例，四字元一詞 | 否 |
| `kpm` | 打鍵/分 | 跨語言比較用的共同分母 | 否 |
| `cpm_raw` | 字元/分 | 沒有當地標準時的中性預設 | 否 |

標為 `authoritative=False` 的指標沒有官方標準，介面上不應出現「合格」「專業級」
這類字眼。

錯打、多打、漏打各算一次錯誤，題目與輸入先以最少錯誤對齊，中間漏打一個字不會讓
後面整段都算錯。秒數與擊鍵數一律從事件流現算。算法與出處見 METHOD.md 第 10 節；
JS 套件的 `score()` 與 `toSample()` 是同一套規則，兩邊的數字逐位相同。

## 模擬器

`typingnorm.simulate` 從同一份常模抽樣，產生帶時間戳的按鍵事件流。它存在的主要理由
是給偵測端當測試對手：本套件的測試就是拿它產生的真人樣本，驗證判準不會誤判。

```bash
python -m typingnorm.simulate --validate    # 輸出分佈與常模對帳
python -m typingnorm.simulate --selftest    # 修正邏輯與按鍵序列合法性
```

## 資料來源

常模擬合自 KeyRecs（99 位受試者、562,372 筆 digraph，CC BY 4.0，**允許商業使用**）：

> Dias, T., Vitorino, J., Maia, E., Sousa, O., & Praça, I. (2023). KeyRecs: A keystroke
> dynamics and typing pattern recognition dataset. *Data in Brief*, 50, 109509.

誤判率則在 Aalto 136M Keystrokes 的 2,500 位受試者上獨立量測。該資料集授權限研究與
非商業用途，**其導出參數未進入本套件**，僅用於驗證，且驗證結果不回頭調整常模參數。
同鍵重疊判準的定義曾依這份資料修正一次，經過與影響見 METHOD.md 第 7.3 節。

兩份資料集都能公開下載，`fit/build_profile.py` 重跑出來的 `profile.json` 與 repo
裡的逐位元相同，`validate/aalto_holdout.py` 重跑出 METHOD.md 第 7.1 至 7.3 節的每一個
數字。指令見 METHOD.md 第 11 節。

## 授權

MIT。
