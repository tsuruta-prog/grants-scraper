"""西宮市の補助金スクレイパ。"""
from __future__ import annotations

from scrapers.base import BaseScraper


class Scraper(BaseScraper):
    municipality = "西宮市"
    # 起業家・事業者むけ支援メニュー
    start_url = "https://www.nishi.or.jp/jigyoshajoho/sangyoshinko/shinkisogyo/sougyou.html"

    def parse(self) -> list[dict]:
        return self.parse_listing(
            list_url=self.start_url,
            link_selector="a",
            keywords=("補助金", "助成金", "支援金", "支援補助"),
        )
