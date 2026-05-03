"""豊中市の補助金スクレイパ。"""
from __future__ import annotations

from scrapers.base import BaseScraper


class Scraper(BaseScraper):
    municipality = "豊中市"
    # 補助金・助成制度ページ
    start_url = "https://www.city.toyonaka.osaka.jp/machi/sangyoushinkou/hojokin/index.html"

    def parse(self) -> list[dict]:
        return self.parse_listing(
            list_url=self.start_url,
            link_selector="a",
            keywords=("補助金", "助成金", "支援金", "支援補助", "応援金", "奨励金"),
        )
