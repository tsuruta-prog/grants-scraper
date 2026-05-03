"""高槻市の補助金スクレイパ。"""
from __future__ import annotations

from scrapers.base import BaseScraper


class Scraper(BaseScraper):
    municipality = "高槻市"
    # 事業者向けトップ（奨励金・助成金、事業者への支援などへの導線が並ぶ）
    start_url = "https://www.city.takatsuki.osaka.jp/life/8/"

    def parse(self) -> list[dict]:
        return self.parse_listing(
            list_url=self.start_url,
            link_selector="a",
            keywords=("補助金", "助成金", "支援金", "支援補助", "奨励金"),
        )
