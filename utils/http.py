"""HTTP クライアントユーティリティ（v2）。

主な改善:
- requests.Session を使ってコネクション/TLSセッションを再利用
- SSL/接続エラー時に自動リトライ (urllib3 Retry によるバックオフ付き)
- 同一ホスト単位のアクセス間隔保持
- robots.txt 尊重
- User-Agent 明示
"""
from __future__ import annotations

import time
from typing import Optional
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import REQUEST_HEADERS, REQUEST_INTERVAL_SEC, REQUEST_TIMEOUT, USER_AGENT
from utils.logger import get_logger

logger = get_logger(__name__)

# ホストごとに最終アクセス時刻 / robots を保持
_last_access: dict[str, float] = {}
_robots_cache: dict[str, Optional[RobotFileParser]] = {}


def _build_session() -> requests.Session:
    """リトライ＆コネクション再利用設定済みの Session を作成する。

    SSL/TLS 系のエラー（自治体サイトでまれに起きる WRONG_VERSION_NUMBER 等）や
    短時間連続アクセスでサーバ側に弾かれるケースに対し、urllib3 の Retry で
    指数バックオフ付き再試行を行う。
    """
    session = requests.Session()
    retry = Retry(
        total=4,                        # 合計4回までリトライ
        connect=4,                      # 接続エラー(SSL含む)で4回まで
        read=2,                         # 読み込みエラーで2回まで
        backoff_factor=1.5,             # 1.5s, 3s, 4.5s, 6s と待つ
        status_forcelist=(500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "HEAD"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(
        max_retries=retry,
        pool_connections=10,
        pool_maxsize=10,
        pool_block=False,
    )
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update(REQUEST_HEADERS)
    return session


# モジュールレベルのSession（プロセス内で共有しTLSセッションを再利用）
_session: Optional[requests.Session] = None


def _get_session() -> requests.Session:
    global _session
    if _session is None:
        _session = _build_session()
    return _session


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
    except Exception as exc:  # noqa: BLE001
        logger.warning("robots.txt 取得失敗 host=%s err=%s", host, exc)
        _robots_cache[host] = None
        return None


def can_fetch(url: str) -> bool:
    """robots.txt 上アクセス可能か。判定不能時は True を返す。"""
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
    """robots / 間隔を尊重した GET（Session 再利用 + 自動リトライ）。

    Raises:
        PermissionError: robots.txt で禁止されている場合
        requests.RequestException: リトライしても回復しなかった HTTP/SSL エラー
    """
    if not can_fetch(url):
        raise PermissionError(f"robots.txt によりアクセス禁止: {url}")

    _throttle(url)

    session = _get_session()
    headers = kwargs.pop("headers", None)
    if headers:
        # ユーザ指定ヘッダがあればこのリクエストだけマージ
        merged = {**session.headers, **headers}
    else:
        merged = None
    timeout = kwargs.pop("timeout", REQUEST_TIMEOUT)
    logger.debug("GET %s", url)
    resp = session.get(url, headers=merged, timeout=timeout, **kwargs)
    resp.raise_for_status()
    # 文字コード推定の精度向上
    if resp.encoding is None or resp.encoding.lower() == "iso-8859-1":
        resp.encoding = resp.apparent_encoding
    return resp
