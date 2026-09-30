# 變更紀錄

Python 套件（PyPI）與 JS 套件（npm）各自編版號，兩者共用同一份 `vectors.json`。

## Python 0.2.0 ／ JS 0.3.0

### 行為變更

- **`same_key_overlap` 只計緊接著的重按。** 上一個非修飾鍵就是同一個鍵、且兩次按下
  相隔 20 ms 至 2 秒才算。原本只要按下時該鍵仍記錄為按住就算，一次遺失的 keyup
  就會誤判，在 Aalto 的 2,500 位真人上誤判 1.00%；改後 0.04%。見 METHOD.md 7.3。
- **`RULES` 的誤判率改為 `check()` 本身的實測值**：`same_key_overlap` 0.0004、
  `constant_dwell` 0、`zero_rollover` 0.0016（原為 0、0、0.0031，出自挑選判準用的
  統計，不是實作本身）。`false_positive_budget` 隨之改變。
- **錯誤改以最少編輯對齊計算。** 錯打、多打、漏打各算一次；原本逐位置比對，中間
  漏打一個字會讓後面整段都算錯。所有用到正確字數或錯誤數的指標都受影響。
- **`cpm_jp` 改用全商的純字数 = 総字数 − エラー数**，錯字只扣一次（原本扣兩次）。
- **`tasu` 改為非官方指標。** 워드프로세서 沒有打字速度門檻，「1 급 300 타」查無
  官方出處。說明文字改為「韓文慣用單位，按字母鍵計數」。
- Python：數值一律 .5 進位，與 JS 的 `Math.round` 相同（原本是銀行家捨入，會在
  37.25 這類值上與網站差 0.1）。`METRICS` 的順序與說明文字改成與 JS 相同。
- Python：`load_session()` 的秒數改為第一次到最後一次按下，擊鍵數只算產生文字的鍵，
  與 JS 的 `toSample()` 及網站伺服器的算法一致。

### 新增

- Python：`accuracy()`、`tqc_grade()`、`parse_session()`；`Report.as_dict()` 帶上
  `false_positive_budget`。
- JS：`toSample()` 從 session 算出 `score()` 要的樣本；`SAME_KEY_GAP_MS`。
- `vectors.json` 納入 session 換算、捨入、說明文字、判準與指標的中繼資料，兩邊改為
  逐位相同，不再容許誤差。
- `session_schema.json` 補上網站實際送出的欄位（`bucket`、`nickname`、`keymap`、
  `keystrokes`、`consent.purpose`、`commits[].revised`、`client.key_reports_symbol`）；
  原本的 schema 會拒收網站自己產生的 session。

### 修正

- `validate/aalto_holdout.py` 原本 import 不存在的模組而無法執行；改寫後重現
  METHOD.md 第 7.1、7.2 節的每一個數字，並加上 `check()` 本身的判定（7.3 節）。
- `fit/build_profile.py` 預設讀 Zenodo 上的原檔名 `free-text.csv`，可重現逐位元相同的
  `profile.json`。
- 模擬器的 `--help` 誤稱時序擬合自 Aalto，實為 KeyRecs。
- Python 的 `tasu` 遇到沒有 key 欄位的事件時會出錯。
- METHOD.md 的重現指令、模組名稱與幾處與實測不符的數字。

## JS 0.2.0

- 加入速度指標（`score`、`allScores`、`accuracy`、`tqcGrade`），與 Python 共用向量。

## Python 0.1.0 ／ JS 0.1.0

- 首次發布：三條偵測判準、速度指標（Python）、模擬器。
