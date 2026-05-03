"""吹田市の補助金スクレイパ。"""
from __future__ import annotations

from scrapers.base import BaseScraper


class Scraper(BaseScraper):
    municipality = "吹田市"
    # 「事業者向けの補助金」カテゴリ一覧
    start_url = "https://www.city.suita.osaka.jp/sangyo/1018028/1018029/1018030/index.html"

    def parse(self) -> list[dict]:
        return self.parse_listing(
            list_url=self.start_url,
            link_selector="a",
            keywords=("補助金", "助成金", "支援金", "支援補助"),
        )
