"""堺市の補助金スクレイパ。"""
from __future__ import annotations

from scrapers.base import BaseScraper


class Scraper(BaseScraper):
    municipality = "堺市"
    # 中小企業支援制度ガイドブックページ（補助金リンクが豊富）
    start_url = "https://www.city.sakai.lg.jp/sangyo/shienyuushi/oshirase/SME_GB.html"

    def parse(self) -> list[dict]:
        return self.parse_listing(
            list_url=self.start_url,
            link_selector="a",
            keywords=("補助金", "助成金", "支援金", "支援補助"),
        )
