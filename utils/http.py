"""HTTP クライアントユーティリティ。

- アクセス間隔を担保（同一ホスト単位）
- robots.txt を尊重
- User-Agent を明示
"""
from __future__ import annotations

import time
from typing import Optional
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests

from config import REQUEST_HEADERS, REQUEST_INTERVAL_SEC, REQUEST_TIMEOUT, USER_AGENT
from utils.logger import get_logger

logger = get_logger(__name__)

# ホストごとに最終アクセス時刻 / robots を保持
_last_access: dict[str, float] = {}
_robots_cache: dict[str, Optional[RobotFileParser]] = {}


def _host(url: str) -> str:
    return urlparse(url).netloc


def _get_robots(url: str) -> Optional[RobotFileParser]:
    """robots.txt を取得・解析。失敗時は None。"""
    host = _host(url)
    if host in _robots_cache:
        return _robots_cache[host]

    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rp = RobotFileParser()
    rp.set_url(robots_url)
    try:
        rp.read()
        _robots_cache[host] = rp
        return rp
    except Exception as exc:  # noqa: BLE001 - 外部 IO エラーは握る
        logger.warning("robots.txt 取得失敗 host=%s err=%s", host, exc)
        _robots_cache[host] = None
        return None


def can_fetch(url: str) -> bool:
    """robots.txt 上アクセス可能か。判定不能時は True を返す（過度な厳格化を避ける）。"""
    rp = _get_robots(url)
    if rp is None:
        return True
    try:
        return rp.can_fetch(USER_AGENT, url)
    except Exception:  # noqa: BLE001
        return True


def _throttle(url: str) -> None:
    """同一ホストへのアクセスを REQUEST_INTERVAL_SEC 以上空ける。"""
    host = _host(url)
    now = time.monotonic()
    last = _last_access.get(host, 0.0)
    wait = REQUEST_INTERVAL_SEC - (now - last)
    if wait > 0:
        time.sleep(wait)
    _last_access[host] = time.monotonic()


def polite_get(url: str, **kwargs) -> requests.Response:
    """robots / 間隔を尊重した GET。

    Raises:
        PermissionError: robots.txt で禁止されている場合
        requests.RequestException: HTTP 関連エラー
    """
    if not can_fetch(url):
        raise PermissionError(f"robots.txt によりアクセス禁止: {url}")

    _throttle(url)

    headers = {**REQUEST_HEADERS, **kwargs.pop("headers", {})}
    timeout = kwargs.pop("timeout", REQUEST_TIMEOUT)
    logger.debug("GET %s", url)
    resp = requests.get(url, headers=headers, timeout=timeout, **kwargs)
    resp.raise_for_status()
    # 文字コード推定の精度向上
    if resp.encoding is None or resp.encoding.lower() == "iso-8859-1":
        resp.encoding = resp.apparent_encoding
    return resp
