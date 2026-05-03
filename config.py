"""共通設定。

各種定数（User-Agent、リクエスト間隔、出力先、対象自治体一覧 など）を集約。
"""
from __future__ import annotations

from pathlib import Path

# プロジェクトルート
ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"
LOG_DIR = ROOT_DIR / "logs"

# 出力ファイル
EXCEL_PATH = DATA_DIR / "grants.xlsx"

# HTTP 設定
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36 "
    "GrantsScraperBot/1.0"
)
REQUEST_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Language": "ja,en;q=0.8",
}

# アクセス間隔（秒）。robots.txt を尊重しつつ最低この秒数は空ける
REQUEST_INTERVAL_SEC = 2.0
REQUEST_TIMEOUT = 30  # 秒

# Playwright 設定
PLAYWRIGHT_TIMEOUT_MS = 30_000

# Excel 列定義（順序が出力列順）
COLUMNS = [
    "自治体名",
    "補助金名",
    "公募ステータス",
    "締切日",
    "補助金額(上限)",
    "概要",
    "URL",
    "取得日時",
]

# 統合シート名
ALL_SHEET = "全件統合"

# 自治体マスタ
# key  : スクレイパモジュール名（scrapers/<name>.py）
# value: シート名 / ラベルとして使う日本語名
MUNICIPALITIES: dict[str, str] = {
    # 大阪府＋大阪府内市
    "osaka_pref": "大阪府",
    "osaka_city": "大阪市",
    "sakai": "堺市",
    "higashiosaka": "東大阪市",
    "suita": "吹田市",
    "toyonaka": "豊中市",
    "ikeda": "池田市",
    "minoh": "箕面市",
    "takatsuki": "高槻市",
    "ibaraki": "茨木市",
    # 兵庫県＋兵庫県内市
    "hyogo_pref": "兵庫県",
    "kobe": "神戸市",
    "himeji": "姫路市",
    "amagasaki": "尼崎市",
    "nishinomiya": "西宮市",
    "kawanishi": "川西市",
    # ポータル
    "jnet21": "J-Net21",
}
