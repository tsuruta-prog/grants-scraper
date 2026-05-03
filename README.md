# 自治体補助金スクレイピングシステム

大阪・兵庫の主要自治体および J-Net21 から、事業者向け補助金情報を毎日自動収集して
1 つの Excel ファイル（`data/grants.xlsx`）に蓄積するパイプラインです。

## 対象サイト

| キー (モジュール名) | 自治体 / サイト |
| --- | --- |
| `osaka_pref` | 大阪府 |
| `osaka_city` | 大阪市 |
| `sakai` | 堺市 |
| `higashiosaka` | 東大阪市 |
| `suita` | 吹田市 |
| `hyogo_pref` | 兵庫県 |
| `kobe` | 神戸市 |
| `himeji` | 姫路市 |
| `amagasaki` | 尼崎市 |
| `nishinomiya` | 西宮市 |
| `jnet21` | J-Net21 補助金検索（中小機構） |

## 抽出項目

- 自治体名
- 補助金名
- 公募ステータス（公募中 / 公募開始 / 公募予定 / 不明）
- 締切日
- 補助金額（上限）
- 概要（200字程度）
- URL
- 取得日時

## ディレクトリ構成

```
grants-scraper/
├── main.py                  # エントリポイント
├── config.py                # 共通設定（自治体一覧、UA、出力先 など）
├── requirements.txt
├── README.md
├── .gitignore
├── .github/
│   └── workflows/
│       └── scrape.yml       # 毎朝 JST 7:00 実行 + auto commit
├── scrapers/
│   ├── __init__.py
│   ├── base.py              # 基底クラス + 共通リスト走査ロジック
│   ├── osaka_pref.py
│   ├── osaka_city.py
│   ├── sakai.py
│   ├── higashiosaka.py
│   ├── suita.py
│   ├── hyogo_pref.py
│   ├── kobe.py
│   ├── himeji.py
│   ├── amagasaki.py
│   ├── nishinomiya.py
│   └── jnet21.py            # Playwright 利用
├── utils/
│   ├── __init__.py
│   ├── http.py              # robots.txt 尊重 + アクセス間隔制御
│   ├── excel_writer.py      # openpyxl で書き込み + URL 重複排除
│   └── logger.py
├── data/
│   └── grants.xlsx          # 出力（自治体別シート + 全件統合シート）
└── logs/
    └── scraper.log
```

## セットアップ

Python 3.11 以上を推奨。

```bash
python -m venv .venv
source .venv/bin/activate          # Windows は .venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium
```

## 実行

### 全自治体を一括実行

```bash
python main.py
```

### 一部の自治体だけ実行（モジュール名を引数で指定）

```bash
python main.py osaka_pref kobe jnet21
```

### 出力

`data/grants.xlsx` に以下の構成で書き込まれます。

- `全件統合` シート: すべての自治体のデータを 1 シートに集約
- 自治体名のシート（例: `大阪府`, `神戸市`, ...）: 自治体ごとのデータ

URL をキーに重複排除するため、毎日実行しても新規分のみが追記されます。

## 動作の特徴

### アクセスマナー

- `User-Agent` を明示（`config.py` の `USER_AGENT`）
- 同一ホストへのアクセス間隔は最低 **2 秒** （`REQUEST_INTERVAL_SEC`）
- `robots.txt` を都度取得して `can_fetch` で判定。禁止対象は取得しない

### 失敗耐性

- 各スクレイパは個別 try/except で囲まれ、1 サイトの失敗で他サイトが止まらない
- `logs/scraper.log` にローテート付きで全エラーが記録される
- GitHub Actions では `continue-on-error` 設定により部分失敗でも commit ステップが実行される

### 重複排除

- 起動時に既存 `grants.xlsx` の全シートから URL 集合を構築
- 取得結果のうち、既存 URL に含まれない & バッチ内でも重複しないものだけを追記

### JS 必須サイト対応

- `jnet21.py` は Playwright (Chromium / headless) を使用
- 他サイトは `requests + BeautifulSoup`。JS が必要な追加自治体は `jnet21.py` を参考にしてください

## GitHub Actions

`.github/workflows/scrape.yml` が以下を毎朝 **JST 7:00** に実行します（cron は UTC 22:00）。

1. リポジトリ checkout
2. Python 3.11 セットアップ
3. 依存インストール（Playwright ブラウザを含む）
4. `python main.py` を実行
5. `data/grants.xlsx` と `logs/` の差分を **自動 commit & push**
6. ログを Actions Artifact として 14 日保管

`workflow_dispatch` で手動実行も可能です。

### 必要な権限

リポジトリの **Settings → Actions → General → Workflow permissions** で
`Read and write permissions` を有効にしてください（auto commit のため）。

## メンテナンス（重要）

各自治体サイトはリニューアルや URL 変更が頻繁にあります。出力件数が急に
ゼロになった、不要な記事が混ざる、といった場合は以下を確認してください。

1. **`scrapers/<自治体>.py` の `start_url`**
   実際にブラウザで開いて、補助金一覧ページが残っているか確認
2. **`link_selector`（CSS セレクタ）**
   開発者ツールで一覧の `<a>` 要素を選択し、適切なセレクタに更新
3. **キーワードフィルタ**
   `base.py::parse_listing` の `keywords` 引数で、リンクテキストに含む語句を
   絞り込んでいます。サイト固有の用語があれば呼び出し側で渡してください
4. **詳細ページの本文セレクタ**
   `parse_listing(detail_selector=...)` を上書き

### 新しい自治体を追加する手順

1. `scrapers/<new_name>.py` を作成し、`BaseScraper` を継承した `Scraper` クラスを定義
2. `parse()` を実装（多くの場合 `self.parse_listing(...)` を呼ぶだけで足りる）
3. `config.py::MUNICIPALITIES` にエントリを追加
4. ローカルで `python main.py <new_name>` を実行して件数を確認

JS が必要なサイトは `scrapers/jnet21.py` を参考にして Playwright を使ってください。

## トラブルシューティング

| 現象 | 確認ポイント |
| --- | --- |
| 「robots.txt によりアクセス禁止」と出る | 当該自治体は対象外。`config.MUNICIPALITIES` から外すか、許可されたパスに `start_url` を変更 |
| 件数が 0 になる | `start_url` の HTML 構造変更を疑う。`link_selector` を見直す |
| Playwright が起動しない | `python -m playwright install chromium` を再実行。Linux なら `--with-deps` |
| Excel が壊れる | `data/grants.xlsx` を削除すれば次回実行時に再生成される（過去データは失う） |
| 文字化け | `utils/http.py::polite_get` で `apparent_encoding` を使っているが、稀に誤検出する。サイト個別に `resp.encoding = "shift_jis"` 等を強制 |

## 留意事項 / 免責

- 本ツールは **公開情報** のみを対象とし、各サイトの利用規約・robots.txt を尊重します
- 過剰アクセスを避けるため `REQUEST_INTERVAL_SEC` を短縮しないでください
- 抽出される「公募ステータス」「締切日」「補助金額(上限)」は HTML テキストからの **推定値** です。
  正確な情報は必ず各自治体の元ページで確認してください
- 各自治体サイトの構造変更により、予告なく取得件数が変動します（上記メンテナンス参照）

## ライセンス

MIT
