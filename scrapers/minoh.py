"""箕面市の補助金スクレイパ。"""
from __future__ import annotations

from scrapers.base import BaseScraper


class Scraper(BaseScraper):
    municipality = "箕面市"
    # 商工業振興補助金（サイドバーに補助金関連リンクが並ぶ）
    start_url = "https://www.city.minoh.lg.jp/syoukou/syoukouhojokin.html"

    def parse(self) -> list[dict]:
        return self.parse_listing(
            list_url=self.start_url,
            link_selector="a",
            keywords=("補助金", "助成金", "支援金", "支援補助"),
        )
