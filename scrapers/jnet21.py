"""J-Net21 補助金検索スクレイパ。

中小機構運営の支援情報ポータル。検索結果ページは JavaScript で結果が
描画されるケースがあるため Playwright を利用する。
"""
from __future__ import annotations

from urllib.parse import urljoin

from bs4 import BeautifulSoup

from config import PLAYWRIGHT_TIMEOUT_MS, USER_AGENT
from scrapers.base import BaseScraper, SKIP_EXTENSIONS
from utils.logger import get_logger

logger = get_logger(__name__)

# リンクテキストにこれらのいずれかを含むものだけ採用（厳しめ）
INCLUDE_KEYWORDS = ("補助金", "助成金", "支援金", "補助制度", "助成制度")

# ナビゲーション・カテゴリ系のリンクを排除
EXCLUDE_PHRASES = (
    "ヘッドライン", "トップ", "一覧", "カテゴリ", "メニュー",
    "サイトマップ", "プライバシー", "ログイン", "新規登録",
)


class Scraper(BaseScraper):
    municipality = "J-Net21"
    start_url = "https://j-net21.smrj.go.jp/snavi/support/"

    def _fetch_html_with_playwright(self, url: str) -> str:
        """Playwright で JS レンダリング後の HTML を返す。"""
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                context = browser.new_context(user_agent=USER_AGENT, locale="ja-JP")
                page = context.new_page()
                page.set_default_timeout(PLAYWRIGHT_TIMEOUT_MS)
                page.goto(url, wait_until="networkidle")
                try:
                    page.wait_for_selector("a", timeout=PLAYWRIGHT_TIMEOUT_MS)
                except Exception:
                    pass
                return page.content()
            finally:
                browser.close()

    def parse(self) -> list[dict]:
        try:
            html = self._fetch_html_with_playwright(self.start_url)
        except Exception as exc:
            logger.exception("[%s] Playwright 取得失敗: %s", self.municipality, exc)
            return self.parse_listing(
                list_url=self.start_url,
                link_selector="a",
                keywords=INCLUDE_KEYWORDS,
                follow_detail=False,
            )

        soup = BeautifulSoup(html, "lxml")
        records: list[dict] = []
        seen: set[str] = set()

        for a in soup.select("a"):
            text = a.get_text(" ", strip=True)
            href = a.get("href")
            if not text or not href:
                continue
            # 短すぎるリンクテキストは除外（カテゴリ名の可能性）
            if len(text) < 8:
                continue
            # 包含キーワードチェック
            if not any(kw in text for kw in INCLUDE_KEYWORDS):
                continue
            # 除外フレーズチェック
            if any(p in text for p in EXCLUDE_PHRASES):
                continue
            # ファイル直リンクは除外
            href_lower = href.lower().split("?")[0].split("#")[0]
            if any(href_lower.endswith(ext) for ext in SKIP_EXTENSIONS):
                continue

            url = urljoin(self.start_url, href)
            if url in seen:
                continue
            seen.add(url)

            parent = a.find_parent(["article", "li", "div"])
            summary = parent.get_text(" ", strip=True) if parent else text

            records.append(
                self.make_record(
                    title=text,
                    url=url,
                    status_text=summary,
                    deadline_text=summary,
                    amount_text=summary,
                    summary=summary,
                )
            )

            if len(records) >= 100:
                break

        return records
