"""大阪府の補助金スクレイパ。"""
from __future__ import annotations

from urllib.parse import urljoin

from scrapers.base import BaseScraper, logger


class Scraper(BaseScraper):
    municipality = "大阪府"
    start_url = "https://www.pref.osaka.lg.jp/o110010/shokosomu/shiensaku/index.html"

    # 除外したいファイル拡張子
    SKIP_EXTENSIONS = (".pdf", ".pptx", ".ppt", ".xlsx", ".xls", ".docx", ".doc", ".zip")

    def parse(self) -> list[dict]:
        soup = self.get_soup(self.start_url)
        anchors = soup.select("a")
        records: list[dict] = []
        seen: set[str] = set()
        keywords = ("補助金", "助成金", "支援金", "支援補助")

        for a in anchors:
            text = a.get_text(strip=True)
            href = a.get("href")
            if not text or not href:
                continue
            # キーワードフィルタ
            if not any(kw in text for kw in keywords):
                continue
            # PDF/PPT などのファイル直リンクは除外
            href_lower = href.lower()
            if any(href_lower.endswith(ext) for ext in self.SKIP_EXTENSIONS):
                continue

            url = urljoin(self.start_url, href)
            if url in seen or url == self.start_url:
                continue
            seen.add(url)

            # 詳細ページから本文取得
            summary = text
            deadline_text = ""
            amount_text = text
            try:
                detail = self.get_soup(url)
                main = detail.select_one("#main, main, .contents, .content, article") or detail.body
                if main:
                    body_text = main.get_text(" ", strip=True)
                    summary = body_text or text
                    amount_text = body_text
                    for sentence in body_text.split("。"):
                        if any(kw in sentence for kw in ("締切", "申請期限", "募集期間", "応募期限")):
                            deadline_text = sentence
                            break
            except Exception:
                logger.warning("[%s] 詳細取得失敗 url=%s", self.municipality, url)

            records.append(
                self.make_record(
                    title=text,
                    url=url,
                    status_text=text + " " + summary,
                    deadline_text=deadline_text,
                    amount_text=amount_text,
                    summary=summary,
                )
            )

        return records