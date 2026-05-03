"""スクレイパ基底クラス。

各自治体のスクレイパはこのクラスを継承し、`parse()` を実装する。
共通機能:
- HTTP / Playwright アクセス
- 概要のトリミング（200字程度）
- ステータスの正規化
- 締切日のパース
- 一覧→詳細ページ巡回（PDF/PPT等のファイル直リンク自動除外）
- 本文マーカーによるヘッダー/メニュー除去
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

from bs4 import BeautifulSoup

from utils.excel_writer import now_jst_str
from utils.http import polite_get
from utils.logger import get_logger

logger = get_logger(__name__)

SUMMARY_MAX = 220

SKIP_EXTENSIONS = (
    ".pdf", ".pptx", ".ppt", ".xlsx", ".xls",
    ".docx", ".doc", ".zip", ".rar", ".7z",
)

# 本文の開始位置を示すマーカー
# rfind で「最後の出現」を探すので、ナビ/パンくずに同じ文言が混じっていても
# 確実に本文直前のマーカーを掴める。
BODY_START_MARKERS = (
    "ここから本文です。",
    "ここから本文です",
    "本文ここから",
    "本文ここからです",
)

# 本文の終わりを示すマーカー
BODY_END_MARKERS = (
    "このページの作成所属",
    "このページに関するお問い合わせ",
    "お問い合わせ先",
    "お問い合わせ",
    "ページの先頭へ戻る",
    "ページの先頭へ",
    "関連ページ",
    "よく見られているページ",
    "このページの情報は役に立ちましたか",
    "より良いウェブサイトにするためにみなさまのご意見",
)

STATUS_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"(公募中|募集中|受付中|申請受付中)"), "公募中"),
    (re.compile(r"(公募開始|募集開始|受付開始)"), "公募開始"),
    (re.compile(r"(公募予定|募集予定|準備中|近日)"), "公募予定"),
]


def normalize_status(text: Optional[str]) -> str:
    if not text:
        return "不明"
    for pat, label in STATUS_PATTERNS:
        if pat.search(text):
            return label
    return "不明"


def trim_summary(text: Optional[str], limit: int = SUMMARY_MAX) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1] + "…"


def extract_body_text(full_text: str) -> str:
    """ページ全文から、本文マーカーで囲まれた範囲だけを抜き出す。

    - 開始マーカー (BODY_START_MARKERS) の **最後の出現** 以降を本文とする
      （rfind を使うことでナビゲーション内の重複を回避）
    - 終了マーカー (BODY_END_MARKERS) が見つかれば、そこ以前で打ち切る
    - 開始マーカーが無い場合は元のテキストをそのまま返す
    """
    if not full_text:
        return ""
    text = full_text
    # 開始マーカー（最後の出現を採用）
    best_start = -1
    for marker in BODY_START_MARKERS:
        idx = text.rfind(marker)
        if idx >= 0:
            candidate = idx + len(marker)
            if candidate > best_start:
                best_start = candidate
    if best_start >= 0:
        text = text[best_start:]
    # 終了マーカー（最初の出現で打ち切る）
    best_end = len(text)
    for marker in BODY_END_MARKERS:
        idx = text.find(marker)
        if 0 < idx < best_end:
            best_end = idx
    text = text[:best_end]
    return text.strip()


_DATE_PATTERNS = [
    re.compile(r"(\d{4})[年./-](\d{1,2})[月./-](\d{1,2})"),
    re.compile(r"令和(\d+)年(\d{1,2})月(\d{1,2})日"),
]


def parse_deadline(text: Optional[str]) -> str:
    if not text:
        return ""
    for pat in _DATE_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        if "令和" in pat.pattern:
            reiwa = int(m.group(1))
            year = 2018 + reiwa
            month = int(m.group(2))
            day = int(m.group(3))
        else:
            year = int(m.group(1))
            month = int(m.group(2))
            day = int(m.group(3))
        try:
            return datetime(year, month, day).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return text.strip()[:30]


def parse_amount(text: Optional[str]) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"\s+", " ", text)
    m = re.search(
        r"(上限|最大|限度額|補助上限)[^0-9万千百億]*([0-9０-９,，\.]+)\s*(億|万|千|百)?\s*円",
        cleaned,
    )
    if m:
        return m.group(0).strip()
    m = re.search(r"[0-9０-９,，\.]+\s*(億|万|千)?\s*円", cleaned)
    if m:
        return m.group(0).strip()
    return ""


class BaseScraper(ABC):
    municipality: str = ""
    start_url: str = ""

    def __init__(self) -> None:
        if not self.municipality:
            raise ValueError(f"{self.__class__.__name__}.municipality を定義してください")

    def get_soup(self, url: str) -> BeautifulSoup:
        resp = polite_get(url)
        return BeautifulSoup(resp.text, "lxml")

    def make_record(
        self,
        title: str,
        url: str,
        status_text: str = "",
        deadline_text: str = "",
        amount_text: str = "",
        summary: str = "",
    ) -> dict:
        return {
            "自治体名": self.municipality,
            "補助金名": (title or "").strip(),
            "公募ステータス": normalize_status(status_text or title),
            "締切日": parse_deadline(deadline_text),
            "補助金額(上限)": parse_amount(amount_text or summary),
            "概要": trim_summary(summary),
            "URL": url.strip(),
            "取得日時": now_jst_str(),
        }

    @abstractmethod
    def parse(self) -> list[dict]:
        """各自治体ごとの実装を書く。"""

    def parse_listing(
        self,
        list_url: str,
        link_selector: str = "a",
        keywords: tuple[str, ...] = ("補助", "助成", "支援金", "給付金", "公募"),
        follow_detail: bool = True,
        detail_selector: str = "#main, main, .contents, .content, article",
        max_items: int = 200,
    ) -> list[dict]:
        """一覧→詳細の汎用巡回。"""
        from urllib.parse import urljoin

        soup = self.get_soup(list_url)
        anchors = soup.select(link_selector)
        records: list[dict] = []
        seen: set[str] = set()

        for a in anchors:
            if len(records) >= max_items:
                break
            text = a.get_text(strip=True)
            href = a.get("href")
            if not text or not href:
                continue
            if keywords and not any(kw in text for kw in keywords):
                continue
            href_lower = href.lower().split("?")[0].split("#")[0]
            if any(href_lower.endswith(ext) for ext in SKIP_EXTENSIONS):
                continue

            url = urljoin(list_url, href)
            if url in seen or url == list_url:
                continue
            seen.add(url)

            summary = text
            deadline_text = ""
            amount_text = text

            if follow_detail:
                try:
                    detail = self.get_soup(url)
                    main = detail.select_one(detail_selector) or detail.body
                    if main:
                        body_text = main.get_text(" ", strip=True)
                        body_text = extract_body_text(body_text) or body_text
                        summary = body_text or text
                        amount_text = body_text
                        for sentence in body_text.split("。"):
                            if any(
                                kw in sentence
                                for kw in ("締切", "申請期限", "募集期間", "応募期限")
                            ):
                                deadline_text = sentence
                                break
                except Exception:
                    logger.warning("[%s] 詳細取得失敗 url=%s", self.municipality, url)

            records.append(
                self.make_record(
                    title=text,
                    url=url,
                    status_text=text + " " + summary,
                    deadline_text=deadline_text,
                    amount_text=amount_text,
                    summary=summary,
                )
            )

        return records

    def fetch(self) -> list[dict]:
        try:
            logger.info("[%s] スクレイピング開始 url=%s", self.municipality, self.start_url)
            records = self.parse() or []
            valid = [r for r in records if r.get("URL") and r.get("補助金名")]
            logger.info("[%s] 取得 %d 件 (有効 %d 件)", self.municipality, len(records), len(valid))
            return valid
        except Exception as exc:
            logger.exception("[%s] スクレイピング失敗: %s", self.municipality, exc)
            return []
