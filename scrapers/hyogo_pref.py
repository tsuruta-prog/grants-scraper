"""兵庫県の補助金スクレイパ。"""
from __future__ import annotations

from scrapers.base import BaseScraper


class Scraper(BaseScraper):
    municipality = "兵庫県"
    # 中小企業支援カテゴリ
    start_url = "https://web.pref.hyogo.lg.jp/work/cate3_332.html"

    def parse(self) -> list[dict]:
        return self.parse_listing(
            list_url=self.start_url,
            link_selector="a",
            keywords=("補助金", "助成金", "支援金", "支援補助"),
        )
