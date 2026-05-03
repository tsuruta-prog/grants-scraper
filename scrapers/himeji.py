"""姫路市の補助金スクレイパ。"""
from __future__ import annotations

from scrapers.base import BaseScraper


class Scraper(BaseScraper):
    municipality = "姫路市"
    # 中小企業者への支援制度カテゴリ
    start_url = "https://www.city.himeji.lg.jp/sangyo/category/4-2-1-2-0-0-0-0-0-0.html"

    def parse(self) -> list[dict]:
        return self.parse_listing(
            list_url=self.start_url,
            link_selector="a",
            keywords=("補助金", "助成金", "支援金", "支援補助"),
            # 姫路市サイトは "本文へスキップ" リンクが #HONBUN を指している。
            detail_selector="#HONBUN, main, article",
        )
