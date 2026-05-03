"""川西市の補助金スクレイパ。"""
from __future__ import annotations

from scrapers.base import BaseScraper


class Scraper(BaseScraper):
    municipality = "川西市"
    # 補助金・税制優遇ページ
    start_url = "https://www.city.kawanishi.hyogo.jp/business/syokogyo/1019925/index.html"

    def parse(self) -> list[dict]:
        return self.parse_listing(
            list_url=self.start_url,
            link_selector="a",
            keywords=("補助金", "助成金", "支援金", "支援補助"),
        )
