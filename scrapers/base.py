"""スクレイパ基底クラス（改良版 v2）。

主な改善点:
1. 概要抽出の改善
   - ヘッダー/ナビゲーション/フッター要素を BeautifulSoup レベルで除去
   - <h1>(タイトル) 直後の本文ノードから抽出
   - 「JavaScriptを使用しています」等の定型ノイズフレーズを除去
2. 終了済み・一覧ページを自動除外
3. detail_selector のフォールバック候補を拡充
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

from bs4 import BeautifulSoup, Tag

from utils.excel_writer import now_jst_str
from utils.http import polite_get
from utils.logger import get_logger

logger = get_logger(__name__)

SUMMARY_MAX = 220

SKIP_EXTENSIONS = (
    ".pdf", ".pptx", ".ppt", ".xlsx", ".xls",
    ".docx", ".doc", ".zip", ".rar", ".7z",
)

# 詳細ページのメインコンテンツを掴むためのセレクタ候補（順番に試す）
# 一番最初に当てたい候補（より具体的なもの）が上に来るように並べる
DEFAULT_DETAIL_SELECTORS = (
    "#main-nosub",             # 豊中市
    "#mol_contents",           # 東大阪市・姫路市・尼崎市等の共通CMS
    "#main_outline",           # 同上(やや広いラッパー)
    "#tmp_contents",           # 一部の地方自治体CMS
    "#HONBUN",                 # 東大阪市旧構造の名残
    "#main_content",
    "#main-contents",
    "#mainContent",
    "#main",
    "main",
    "article",
    ".contents",
    ".content",
    "#contents",
    ".main_contents",
    ".main-contents",
    ".wrap",                    # 豊中市の.wrap clearfix
    "#center",
    ".body",
)

# 本文要素の中で除去すべきタグ・セレクタ（パンくず・ナビ・関連リンク等）
NOISE_SELECTORS = (
    "header", "footer", "nav", "aside",
    ".header", ".footer", ".nav", ".navi", ".navigation",
    ".headbg",                # 豊中市のヘッダー全体ラッパー
    ".breadcrumb", ".breadcrumbs", ".pankuzu",
    ".sidebar", ".side", ".sidemenu", ".side-menu",
    ".pagetop", ".page-top", ".to-top",
    ".share", ".sns",
    ".search", ".searchbox", ".search_wrap", ".menu_wrap",
    "#header", "#footer", "#nav", "#sidebar",
    "#breadcrumb", "#pankuzu",
    "#globalNav", "#globalnav", "#gnav", "#gnavi_menu",
    "#menubar_smp", ".sub_menu_smp",
    "#blockskip", ".blockjump",      # 豊中市の「本文へ移動」スキップリンク
    ".skip", ".skiplink", ".skip-link",
    "#contact", ".contact-email",     # 各ページ末尾のお問合せボックス
    "p.filelink", "p.dladobereader",  # PDFリンクと「Adobe Reader必要」案内
    ".guidance",                       # 豊中市のフッタ案内
    ".date_area",                      # 「ページ番号 更新日 印刷」メタ行
    ".main_naka",                      # 東大阪市・姫路市の「ご意見をお聞かせください」枠
    ".soshiki_box", ".info_box",       # 関連組織情報ボックス
    "script", "style", "noscript",
)

# 本文に紛れ込みやすい定型ノイズフレーズ（部分一致で削除）
NOISE_PHRASES = (
    "ホームページではJavaScriptを使用しています",
    "JavaScriptの使用を有効にしていない場合",
    "ブラウザの設定でJavaScriptを有効にしてからご覧ください",
    "共通メニューなどをスキップして本文へ",
    "このページの本文へ移動",
    "Language 音声読み上げ",
    "音声読み上げ /文字拡大",
    "文字サイズ 標準 拡大",
    "文字サイズ：標準 拡大",
    "/文字拡大",
    "やさしい日本語",
    "音声読み上げ",
    "ふりがなをつける",
    "Foreign Language",
    "English Chinese Korean",
    "ページの先頭へ戻る",
    "このページの先頭へ",
    "印刷用ページを表示する",
    "Twitterでツイート",
    "Facebookでシェア",
    "LINEで送る",
    "PDF形式のファイルを開くには",
    "Adobe Acrobat Readerが必要",
    "Adobe Acrobat Reader",
)

# 本文の開始位置を示すマーカー
BODY_START_MARKERS = (
    "ここから本文です。",
    "ここから本文です",
    "本文ここから",
    "本文ここからです",
)

# 本文の終わりを示すマーカー
BODY_END_MARKERS = (
    "このページの作成所属",
    "このページに関するお問い合わせ",
    "お問い合わせ先",
    "ページの先頭へ戻る",
    "ページの先頭へ",
    "関連ページ",
    "関連リンク",
    "よく見られているページ",
    "このページの情報は役に立ちましたか",
    "より良いウェブサイトにするためにみなさまのご意見",
    "アンケートにご協力ください",
    "情報発信元",
)

# 補助金名としてふさわしくない（一覧ページ等の）パターン
EXCLUDE_TITLE_PATTERNS = (
    re.compile(r"^(補助金|助成金|補助・助成金等|奨励金・助成金|補助金・助成金|"
               r"学生向け補助金・助成金等|事業者支援|事業者向け|"
               r"中小企業支援|商工業)$"),
    # 「○○について（採択事業者を決定しました）」「○○の申し込み受付は終了しました」など
    re.compile(r"(申し?込み?受付は終了しました|申込受付は終了しました|"
               r"受付終了しました|募集を終了しました|"
               r"採択事業者を決定しました|採択事業者を公表|"
               r"採択結果について|公募は終了|募集は終了)"),
)

STATUS_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"(公募中|募集中|受付中|申請受付中)"), "公募中"),
    (re.compile(r"(公募開始|募集開始|受付開始|募集を開始|申込受付を開始|申込み受付を開始)"), "公募開始"),
    (re.compile(r"(公募予定|募集予定|準備中|近日|予定して)"), "公募予定"),
    (re.compile(r"(終了しました|受付終了|募集終了|公募終了)"), "終了"),
]


def is_excluded_title(title: str) -> bool:
    """補助金名が一覧ページや終了済みお知らせ等に該当するか。"""
    if not title:
        return True
    t = title.strip()
    for pat in EXCLUDE_TITLE_PATTERNS:
        if pat.search(t):
            return True
    return False


def normalize_status(text: Optional[str]) -> str:
    if not text:
        return "不明"
    for pat, label in STATUS_PATTERNS:
        if pat.search(text):
            return label
    return "不明"


def trim_summary(text: Optional[str], limit: int = SUMMARY_MAX) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1] + "…"


def remove_noise_phrases(text: str) -> str:
    """本文中の定型ノイズフレーズを削除する。

    順序が重要:
    1. まず文（。/改行で区切る）単位で分割
    2. ノイズキーワードを含む文は丸ごと捨てる
    3. 残った文に対して、定型句（NOISE_PHRASES）の部分置換を行う
    4. 連続空白・記号の整理
    """
    if not text:
        return ""

    # ノイズキーワードを含む文は丸ごと捨てる対象
    NOISE_HINT_KEYWORDS = (
        "JavaScript", "javascript",
        "ブラウザの設定", "ブラウザを",
        "推奨環境", "プラグイン", "Adobe Reader",
        "を使用しています", "を有効にして",
        "正確に動作しない", "正しく動作しない",
        "ご利用のブラウザ",
        "このページの作成担当",   # 豊中市フッタ
        "このページの作成所属",
        "このページに関するお問い合わせ",
        "お問い合わせ先",
    )

    # 1. 文区切り（句点・改行）
    sentences = re.split(r"(?<=[。\n])", text)
    # 2. ノイズキーワードを含む文を捨てる
    kept = [s for s in sentences if not any(kw in s for kw in NOISE_HINT_KEYWORDS)]
    text = "".join(kept)

    # 3. NOISE_PHRASES（短い定型句）の単純置換
    for phrase in NOISE_PHRASES:
        text = text.replace(phrase, " ")

    # 4. 整形
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"。\s*。", "。", text)
    text = re.sub(r"、\s*、", "、", text)
    text = re.sub(r"^[、。\s]+", "", text)
    return text.strip()


def strip_noise_elements(soup_or_tag) -> None:
    """与えられた BeautifulSoup/Tag からヘッダ・ナビ・フッタ等を破壊的に削除する。"""
    if soup_or_tag is None:
        return
    for sel in NOISE_SELECTORS:
        for el in soup_or_tag.select(sel):
            el.decompose()


def extract_body_text(full_text: str) -> str:
    """ページ全文（テキスト化済）から、本文マーカーで囲まれた範囲だけを抜き出す。

    NOISE要素を decompose した後の get_text 結果に対して使う想定。
    マーカーが無ければ元のテキストをそのまま返す。
    """
    if not full_text:
        return ""
    text = full_text
    # 開始マーカー（最後の出現を採用：ナビ重複を回避）
    best_start = -1
    for marker in BODY_START_MARKERS:
        idx = text.rfind(marker)
        if idx >= 0:
            candidate = idx + len(marker)
            if candidate > best_start:
                best_start = candidate
    if best_start >= 0:
        text = text[best_start:]
    # 終了マーカー（最初の出現で打ち切る）
    best_end = len(text)
    for marker in BODY_END_MARKERS:
        idx = text.find(marker)
        if 0 < idx < best_end:
            best_end = idx
    text = text[:best_end]
    return text.strip()


def extract_summary_from_detail(soup: BeautifulSoup, fallback_title: str,
                                detail_selector: str = "") -> str:
    """詳細ページの BeautifulSoup から、概要として使える本文を抽出する。

    手順:
    1. NOISE_SELECTORS で指定された要素を decompose（ヘッダー/ナビ/フッタ削除）
    2. detail_selector または DEFAULT_DETAIL_SELECTORS で本文要素を取得
    3. その要素の get_text を NOISE_PHRASES でクリーンアップ
    4. extract_body_text でマーカー範囲に絞る
    5. 本文がスカスカな場合は <h1> 以降の <p>/<li> を集めるフォールバック
    """
    if soup is None:
        return ""

    # 1. ノイズ要素を破壊的に削除
    strip_noise_elements(soup)

    # 2. 本文要素を探す（候補を順に試し、十分な文字数を持つ要素を選ぶ）
    main = None
    selectors_to_try = []
    if detail_selector:
        # ユーザ指定セレクタ（カンマ区切り対応）
        selectors_to_try.extend([s.strip() for s in detail_selector.split(",") if s.strip()])
    selectors_to_try.extend(DEFAULT_DETAIL_SELECTORS)
    # 重複を順序保ったまま除去
    seen = set()
    selectors_uniq = []
    for s in selectors_to_try:
        if s not in seen:
            seen.add(s)
            selectors_uniq.append(s)

    for sel in selectors_uniq:
        try:
            candidate = soup.select_one(sel)
        except Exception:
            candidate = None
        if candidate is None:
            continue
        # 取れた要素のテキスト量で判定（空のアンカーや極小要素はスキップ）
        cand_text = candidate.get_text(strip=True)
        if len(cand_text) < 30:
            # 30文字未満は本文と見なさず次の候補へ
            continue
        main = candidate
        break

    # 3. 本文要素から取れなければ body 全体（NOISE削除済）
    if main is None:
        main = soup.body if soup.body else soup

    # 4. テキスト化＋ノイズフレーズ削除
    #    separator="\n" にすると、p/li/h などタグ単位で改行が入り、
    #    文単位のノイズ判定（remove_noise_phrases）が正しく効くようになる。
    text = main.get_text("\n", strip=True)
    text = remove_noise_phrases(text)
    text = extract_body_text(text) or text

    # 5. タイトルが先頭付近に丸ごと入っている場合は1回だけ削る
    #    （get_text("空白") でスペースが挟まることもあるので緩めに比較）
    if fallback_title:
        # スペースを除去した状態で比較
        title_compact = re.sub(r"\s+", "", fallback_title)
        text_compact = re.sub(r"\s+", "", text)
        if text_compact.startswith(title_compact) and title_compact:
            # text の先頭から、タイトル分の「非空白文字数」を消費する位置を見つける
            consumed = 0
            cut_at = 0
            for i, ch in enumerate(text):
                if not ch.isspace():
                    consumed += 1
                if consumed >= len(title_compact):
                    cut_at = i + 1
                    break
            if cut_at:
                text = text[cut_at:].strip()

    # 6. それでも極端に短い/タイトル相当しか無い場合は <p>, <li> をかき集める
    if len(text) < 40:
        chunks: list[str] = []
        for tag in main.find_all(["p", "li", "dd"]):
            t = tag.get_text(" ", strip=True)
            t = remove_noise_phrases(t)
            if not t or len(t) < 8:
                continue
            if fallback_title and t == fallback_title:
                continue
            chunks.append(t)
            if sum(len(c) for c in chunks) > 300:
                break
        if chunks:
            text = " ".join(chunks)

    return text.strip()


_DATE_PATTERNS = [
    re.compile(r"(\d{4})[年./-](\d{1,2})[月./-](\d{1,2})"),
    re.compile(r"令和(\d+)年(\d{1,2})月(\d{1,2})日"),
]


def parse_deadline(text: Optional[str]) -> str:
    if not text:
        return ""
    for pat in _DATE_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        if "令和" in pat.pattern:
            reiwa = int(m.group(1))
            year = 2018 + reiwa
            month = int(m.group(2))
            day = int(m.group(3))
        else:
            year = int(m.group(1))
            month = int(m.group(2))
            day = int(m.group(3))
        try:
            return datetime(year, month, day).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return text.strip()[:30]


def parse_amount(text: Optional[str]) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"\s+", " ", text)
    m = re.search(
        r"(上限|最大|限度額|補助上限)[^0-9万千百億]*([0-9０-９,，\.]+)\s*(億|万|千|百)?\s*円",
        cleaned,
    )
    if m:
        return m.group(0).strip()
    m = re.search(r"[0-9０-９,，\.]+\s*(億|万|千)?\s*円", cleaned)
    if m:
        return m.group(0).strip()
    return ""


def smart_title(link_text: str, soup: Optional[BeautifulSoup] = None,
                max_len: int = 80) -> str:
    """リンクテキストが長すぎる（タイトル+本文がくっついている）場合に、
    詳細ページの <h1> からタイトルを取り直す。

    一覧ページの <a> のテキストが「補助金名+本文の冒頭」になっているサイト
    （姫路市など）への対策。soup が渡されない、または h1 が空・長すぎる場合は、
    リンクテキスト先頭を句読点で切るフォールバックを行う。
    """
    if not link_text:
        return ""
    text = link_text.strip()
    if len(text) <= max_len:
        return text

    # 1. 詳細ページのh1から取り直す
    if soup is not None:
        for h1 in soup.find_all("h1"):
            h1_text = h1.get_text(strip=True)
            # ヘッダーロゴなどの空・短すぎ・長すぎは除外
            if h1_text and 4 <= len(h1_text) <= max_len:
                return h1_text

    # 2. フォールバック: 句読点や記号で切る
    for sep in ["【", "（", "(", "。", "  "]:
        idx = text.find(sep, 4)
        if 4 < idx <= max_len:
            return text[:idx].strip()
    # それでも長ければ単純トリム
    return text[:max_len].rstrip() + "…"


class BaseScraper(ABC):
    municipality: str = ""
    start_url: str = ""

    def __init__(self) -> None:
        if not self.municipality:
            raise ValueError(f"{self.__class__.__name__}.municipality を定義してください")

    def get_soup(self, url: str) -> BeautifulSoup:
        resp = polite_get(url)
        return BeautifulSoup(resp.text, "lxml")

    def make_record(
        self,
        title: str,
        url: str,
        status_text: str = "",
        deadline_text: str = "",
        amount_text: str = "",
        summary: str = "",
    ) -> dict:
        return {
            "自治体名": self.municipality,
            "補助金名": (title or "").strip(),
            "公募ステータス": normalize_status(status_text or title),
            "締切日": parse_deadline(deadline_text),
            "補助金額(上限)": parse_amount(amount_text or summary),
            "概要": trim_summary(summary),
            "URL": url.strip(),
            "取得日時": now_jst_str(),
        }

    @abstractmethod
    def parse(self) -> list[dict]:
        """各自治体ごとの実装を書く。"""

    def parse_listing(
        self,
        list_url: str,
        link_selector: str = "a",
        keywords: tuple[str, ...] = ("補助", "助成", "支援金", "給付金", "公募"),
        follow_detail: bool = True,
        detail_selector: str = "",
        max_items: int = 200,
        skip_ended: bool = True,
    ) -> list[dict]:
        """一覧→詳細の汎用巡回。

        skip_ended: True にすると、補助金名に「終了しました」「採択事業者を決定」等
        を含む行と、明らかな一覧ページタイトル（"補助金"単体など）を除外する。
        """
        from urllib.parse import urljoin

        soup = self.get_soup(list_url)
        anchors = soup.select(link_selector)
        records: list[dict] = []
        seen: set[str] = set()

        for a in anchors:
            if len(records) >= max_items:
                break
            text = a.get_text(strip=True)
            href = a.get("href")
            if not text or not href:
                continue
            if keywords and not any(kw in text for kw in keywords):
                continue
            href_lower = href.lower().split("?")[0].split("#")[0]
            if any(href_lower.endswith(ext) for ext in SKIP_EXTENSIONS):
                continue

            url = urljoin(list_url, href)
            if url in seen or url == list_url:
                continue
            seen.add(url)

            # 終了済み・一覧ページ系を除外
            if skip_ended and is_excluded_title(text):
                continue

            summary = text
            deadline_text = ""
            amount_text = text
            final_title = text

            if follow_detail:
                try:
                    detail = self.get_soup(url)
                    # タイトル長すぎ対策: <h1> から取り直す
                    final_title = smart_title(text, soup=detail)
                    summary = extract_summary_from_detail(
                        detail, fallback_title=final_title, detail_selector=detail_selector
                    ) or final_title
                    amount_text = summary
                    # 締切日候補：本文を「。」区切りで走査
                    for sentence in summary.split("。"):
                        if any(
                            kw in sentence
                            for kw in ("締切", "申請期限", "募集期間", "応募期限",
                                       "受付期間", "申込期限", "申込み期限")
                        ):
                            deadline_text = sentence
                            break
                except Exception as exc:
                    logger.warning("[%s] 詳細取得失敗 url=%s err=%s: %s",
                                   self.municipality, url, type(exc).__name__, exc)

            records.append(
                self.make_record(
                    title=final_title,
                    url=url,
                    status_text=final_title + " " + summary,
                    deadline_text=deadline_text,
                    amount_text=amount_text,
                    summary=summary,
                )
            )

        return records

    def fetch(self) -> list[dict]:
        try:
            logger.info("[%s] スクレイピング開始 url=%s", self.municipality, self.start_url)
            records = self.parse() or []
            valid = [r for r in records if r.get("URL") and r.get("補助金名")]
            logger.info("[%s] 取得 %d 件 (有効 %d 件)", self.municipality, len(records), len(valid))
            return valid
        except Exception as exc:
            logger.exception("[%s] スクレイピング失敗: %s", self.municipality, exc)
            return []
