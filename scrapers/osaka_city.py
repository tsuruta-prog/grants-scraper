"""大阪市の補助金スクレイパ。"""
from __future__ import annotations

from scrapers.base import BaseScraper


class Scraper(BaseScraper):
    municipality = "大阪市"
    # 産業・ビジネス > 中小企業支援 カテゴリ
    start_url = "https://www.city.osaka.lg.jp/sangyo/category/3037-1-2-1-0-0-0-0-0-0.html"

    def parse(self) -> list[dict]:
        return self.parse_listing(
            list_url=self.start_url,
            link_selector="a",
            keywords=("補助金", "助成金", "支援金", "支援補助"),
        )
