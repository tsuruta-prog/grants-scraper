"""スクレイパ基底クラス。

各自治体のスクレイパはこのクラスを継承し、`parse()` を実装する。
共通機能:
- HTTP / Playwright アクセス
- 概要のトリミング（200字程度）
- ステータスの正規化
- 締切日のパース
- 一覧→詳細ページ巡回（PDF/PPT等のファイル直リンク自動除外）
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

# 概要の目安文字数（200字「程度」)
SUMMARY_MAX = 220

# 一覧から除外するファイル拡張子（PDF/オフィス文書/アーカイブ類は補助金本体ではなくパンフレット類）
SKIP_EXTENSIONS = (
    ".pdf", ".pptx", ".ppt", ".xlsx", ".xls",
    ".docx", ".doc", ".zip", ".rar", ".7z",
)

# ステータス正規化マップ
STATUS_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"(公募中|募集中|受付中|申請受付中)"), "公募中"),
    (re.compile(r"(公募開始|募集開始|受付開始)"), "公募開始"),
    (re.compile(r"(公募予定|募集予定|準備中|近日)"), "公募予定"),
]


def normalize_status(text: Optional[str]) -> str:
    """テキストから公募ステータスを推定。マッチしないものは '不明'。"""
    if not text:
        return "不明"
    for pat, label in STATUS_PATTERNS:
        if pat.search(text):
            return label
    return "不明"


def trim_summary(text: Optional[str], limit: int = SUMMARY_MAX) -> str:
    """概要を整形してざっくり 200 字に収める。"""
    if not text:
        return ""
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1] + "…"


_DATE_PATTERNS = [
    re.compile(r"(\d{4})[年./-](\d{1,2})[月./-](\d{1,2})"),
    re.compile(r"令和(\d+)年(\d{1,2})月(\d{1,2})日"),
]


def parse_deadline(text: Optional[str]) -> str:
    """文章中から締切日らしきものを ISO 形式 (YYYY-MM-DD) で取り出す。"""
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
    """金額表現から上限額の表示文字列を取り出す。"""
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
    """各自治体スクレイパの基底クラス。"""

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
        """一覧→詳細の汎用巡回。PDF/PPT/Excel等のファイル直リンクは自動除外。"""
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
            # PDF/PPT/Excel/ZIP 等のファイル直リンクは除外
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
        """例外を握って空リストにフォールバック（パイプラインを止めないため）。"""
        try:
            logger.info("[%s] スクレイピング開始 url=%s", self.municipality, self.start_url)
            records = self.parse() or []
            valid = [r for r in records if r.get("URL") and r.get("補助金名")]
            logger.info("[%s] 取得 %d 件 (有効 %d 件)", self.municipality, len(records), len(valid))
            return valid
        except Exception as exc:
            logger.exception("[%s] スクレイピング失敗: %s", self.municipality, exc)
            return []
