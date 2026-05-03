"""神戸市の補助金スクレイパ。

詳細ページの本文抽出は base.py の本文マーカー機能（"ここから本文です。"〜
"このページの作成所属" などで切り出し）に任せる。
"""
from __future__ import annotations

from scrapers.base import BaseScraper


class Scraper(BaseScraper):
    municipality = "神戸市"
    # ものづくり中小企業支援
    start_url = "https://www.city.kobe.lg.jp/a93457/business/sangyoshinko/shokogyo/venture/monodukuri/index.html"

    def parse(self) -> list[dict]:
        return self.parse_listing(
            list_url=self.start_url,
            link_selector="a",
            keywords=("補助金", "助成金", "支援金", "支援補助", "助成制度"),
        )
