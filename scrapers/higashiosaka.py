"""東大阪市の補助金スクレイパ。"""
from __future__ import annotations

from scrapers.base import BaseScraper


class Scraper(BaseScraper):
    municipality = "東大阪市"
    # 産業振興・企業支援 カテゴリ
    start_url = "https://www.city.higashiosaka.lg.jp/category/19-1-0-0-0-0-0-0-0-0.html"

    def parse(self) -> list[dict]:
        return self.parse_listing(
            list_url=self.start_url,
            link_selector="a",
            keywords=("補助金", "助成金", "支援金", "支援補助"),
            # 東大阪市サイトは "共通メニューなどをスキップして本文へ" リンクが #HONBUN を指している
            detail_selector="#HONBUN, main, article",
        )
