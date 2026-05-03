"""自治体補助金スクレイピングのエントリポイント。

- config.MUNICIPALITIES に列挙された各モジュール (scrapers/<name>.py) を順に実行
- 失敗してもパイプラインは止めず、エラーは logs/scraper.log に記録
- 既存 Excel から URL を読み込み、新規分のみ追記
"""
from __future__ import annotations

import importlib
import sys
import traceback
from typing import Iterable

from config import EXCEL_PATH, MUNICIPALITIES
from utils.excel_writer import append_grants, load_existing_urls
from utils.logger import get_logger

logger = get_logger(__name__)


def _dedup_by_url(records: Iterable[dict], existing_urls: set[str]) -> list[dict]:
    """既存 URL に含まれず、かつバッチ内でも重複しないものだけ返す。"""
    out: list[dict] = []
    seen: set[str] = set()
    for r in records:
        url = (r.get("URL") or "").strip()
        if not url:
            continue
        if url in existing_urls or url in seen:
            continue
        seen.add(url)
        out.append(r)
    return out


def run_one(module_name: str) -> list[dict]:
    """単一スクレイパを動的 import して実行。失敗時は空リスト。"""
    try:
        mod = importlib.import_module(f"scrapers.{module_name}")
    except Exception as exc:  # noqa: BLE001
        logger.error("scrapers.%s の import 失敗: %s", module_name, exc)
        logger.debug(traceback.format_exc())
        return []

    scraper_cls = getattr(mod, "Scraper", None)
    if scraper_cls is None:
        logger.error("scrapers.%s に Scraper クラスが定義されていません", module_name)
        return []

    try:
        scraper = scraper_cls()
        return scraper.fetch()
    except Exception as exc:  # noqa: BLE001
        logger.exception("scrapers.%s 実行失敗: %s", module_name, exc)
        return []


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    targets = list(MUNICIPALITIES.keys())

    if argv:
        # 引数で対象を絞れる: python main.py osaka_pref kobe
        targets = [a for a in argv if a in MUNICIPALITIES]
        if not targets:
            logger.error("有効な対象がありません。指定可能: %s", ", ".join(MUNICIPALITIES))
            return 2

    logger.info("=== 開始: 対象 %d 件 ===", len(targets))

    existing = load_existing_urls(EXCEL_PATH)
    logger.info("既存 URL %d 件を読込", len(existing))

    all_new: list[dict] = []
    summary: dict[str, int] = {}

    for name in targets:
        records = run_one(name)
        new_records = _dedup_by_url(records, existing)
        # 既存集合にも反映（同一バッチ内の他スクレイパとの重複も防ぐ）
        for r in new_records:
            existing.add(r["URL"])
        all_new.extend(new_records)
        summary[MUNICIPALITIES[name]] = len(new_records)
        logger.info(
            "[%s] 取得 %d 件 / 新規 %d 件",
            MUNICIPALITIES[name],
            len(records),
            len(new_records),
        )

    if all_new:
        append_grants(all_new, EXCEL_PATH)
    else:
        logger.info("新規データなし。Excel は更新しません。")

    logger.info("=== 終了 ===")
    for muni, n in summary.items():
        logger.info("  %s: 新規 %d 件", muni, n)
    logger.info("合計新規: %d 件", len(all_new))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
