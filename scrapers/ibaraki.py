"""茨木市の補助金スクレイパ。"""
from __future__ import annotations

from scrapers.base import BaseScraper


class Scraper(BaseScraper):
    municipality = "茨木市"
    # 補助金・助成金 一覧トップ
    start_url = "https://www.city.ibaraki.osaka.jp/hojokin_joseikin/index.html"

    def parse(self) -> list[dict]:
        return self.parse_listing(
            list_url=self.start_url,
            link_selector="a",
            keywords=("補助金", "助成金", "支援金", "支援補助"),
        )
