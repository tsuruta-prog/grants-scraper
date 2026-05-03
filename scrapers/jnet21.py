"""J-Net21 補助金検索スクレイパ。

中小機構運営の支援情報ポータル。検索結果ページは JavaScript で結果が
描画されるケースがあるため Playwright を利用する。
URL: https://j-net21.smrj.go.jp/snavi/support/
"""
from __future__ import annotations

from urllib.parse import urljoin

from bs4 import BeautifulSoup

from config import PLAYWRIGHT_TIMEOUT_MS, USER_AGENT
from scrapers.base import BaseScraper
from utils.logger import get_logger

logger = get_logger(__name__)


class Scraper(BaseScraper):
    municipality = "J-Net21"
    # 補助金/助成金 のカテゴリで絞り込んだ一覧。実運用では地域フィルタを足してもよい。
    start_url = "https://j-net21.smrj.go.jp/snavi/support/"

    def _fetch_html_with_playwright(self, url: str) -> str:
        """Playwright で JS レンダリング後の HTML を返す。"""
        # 遅延 import: Playwright 未インストール環境でも他スクレイパが動くように
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                context = browser.new_context(user_agent=USER_AGENT, locale="ja-JP")
                page = context.new_page()
                page.set_default_timeout(PLAYWRIGHT_TIMEOUT_MS)
                page.goto(url, wait_until="networkidle")
                # 結果リストが描画されるまで少し待つ（要素が無くてもタイムアウトで握る）
                try:
                    page.wait_for_selector("a", timeout=PLAYWRIGHT_TIMEOUT_MS)
                except Exception:  # noqa: BLE001
                    pass
                return page.content()
            finally:
                browser.close()

    def parse(self) -> list[dict]:
        try:
            html = self._fetch_html_with_playwright(self.start_url)
        except Exception as exc:  # noqa: BLE001
            logger.exception("[%s] Playwright 取得失敗: %s", self.municipality, exc)
            # フォールバック: 通常 GET（中身は薄いかもしれない）
            return self.parse_listing(
                list_url=self.start_url,
                link_selector="a",
                follow_detail=False,
            )

        soup = BeautifulSoup(html, "lxml")
        records: list[dict] = []
        seen: set[str] = set()

        # 一覧の各カードに含まれるリンクを拾う
        for a in soup.select("a"):
            text = a.get_text(" ", strip=True)
            href = a.get("href")
            if not text or not href:
                continue
            if not any(kw in text for kw in ("補助", "助成", "支援", "公募")):
                continue
            url = urljoin(self.start_url, href)
            if url in seen:
                continue
            seen.add(url)

            # 親要素から概要っぽいテキストを取得（詳細ページに行かず軽く済ます）
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
