"""typingnorm — 人類打字的常模，以及據此判斷輸入是否為真人的判準。

`profile.json` 是常模本身：擬合自 KeyRecs（CC BY 4.0，可商業使用）的擊鍵時序分佈。
`detect.check()` 拿觀測到的擊鍵去比對常模。`simulate` 反過來從常模抽樣產生擊鍵，
主要用途是給偵測端當測試對手。

每條判準的誤判率都在另一份獨立資料集（Aalto 136M Keystrokes，2,245 位受試者）上
量過，方法與數字見 METHOD.md。
"""

from .detect import RULES, Report, check
from .metrics import (DEFAULT_METRIC, METRICS, Session, all_scores,
                      load_session, score)

__version__ = "0.1.0"
__all__ = [
    "check", "Report", "RULES",
    "score", "all_scores", "Session", "load_session", "METRICS", "DEFAULT_METRIC",
]
