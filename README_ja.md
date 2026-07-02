# Pokemon Sleep ボックスCSVエクスポート

> 📖 [English README](README.md)

ポケモンスリープのアプリ内DBからボックスのポケモン一覧を取得し、日本語CSVに出力するツールです。

<img width="1823" height="975" alt="image" src="https://github.com/user-attachments/assets/710ee4a6-04b0-4e72-98b5-33ee1d62f45a" />

## 必要なもの

- Windows PC
- root化済み Android 端末（USB接続）
- [Frida](https://frida.re/) （Python パッケージ + 端末側 frida-server）

## セットアップ

### 1. Python 環境

```bash
python -m venv .venv
.venv\Scripts\activate
pip install frida frida-tools
```

### 2. Android 端末セットアップ（自動）

```bash
python setup_android.py
```

frida-server のダウンロードと端末へのインストールを自動で行います。

## 使い方

### ボックスデータの取得 → CSV出力

```bash
# 1. frida-server 起動
adb shell "su -c '/data/local/tmp/frida-server &'"

# 2. アプリを起動してボックスを開く

# 3. データ取得 + CSV生成
python dump_pokemon_box.py
```

出力ファイル：
- `pokemon_box.csv` — 日本語列名のCSV（30列）
- `pokemon_box_raw.csv` — DB生データCSV
- `pokemon_box_dump.json` — DBダンプ（JSON）

### CSV だけ再生成（DBダンプ済みの場合）

```bash
python -c "import json; from dump_pokemon_box import build_csv; build_csv(json.load(open('pokemon_box_dump.json', encoding='utf-8')))"
```

### 不足テーブルの追加取得

```bash
python fetch_missing_tables.py
```

マスターDBのテーブルを調査し、不足データを既存ダンプに追加します。

## CSV の列

| 列名 | 説明 |
|---|---|
| 図鑑No | 全国図鑑番号 |
| ポケモン名 | 日本語名 |
| Lv | レベル |
| SP | 総合SP |
| 性別 | ♂ / ♀ / - |
| とくい | きのみ / 食材 / スキル |
| リボンランク | リボンランク |
| お気に入り | ★ |
| きのみ | きのみの種類 |
| 食材A/B/C | 食材とその個数 |
| 最大所持数 | ベース最大所持数 |
| メインスキル | メインスキル名 |
| メインスキルLv | メインスキルレベル |
| サブスキル1〜5 | サブスキル名 |
| せいかく | せいかく名 |
| 出会った日 | 捕獲日時（JST） |
| 出会ったフィールド | フィールド名 |
| げんき | 現在のげんき |
| きのみSP / 料理SP / スキルSP | 各SP |
| 進化回数 | 進化回数 |
| 個体ID | 内部ID |

## HTMLビューア

`pokemon_box_viewer.html` をブラウザで開き、CSVをドラッグ＆ドロップすると表形式で閲覧できます。

- 列ソート（ヘッダークリック）
- 列の表示/非表示切り替え（「📋 列の表示」ボタン）
- 設定はlocalStorageに保存

### 📊🔍 大福サイトチェッカー連携

ビューアから [ポケモンスリープ大福](https://www.pokemonsleepdaifuku.com/) のチェッカーに自動入力できます。

- **📊 期待値** — [期待値チェッカー](https://www.pokemonsleepdaifuku.com/checker/expected/)
- **🔍 個体値** — [個体値チェッカー](https://www.pokemonsleepdaifuku.com/checker/)

1. テーブルの行をクリックして選択
2. 「📊 期待値」または「🔍 個体値」ボタンをクリック → JSコードがクリップボードにコピーされます
3. 大福サイトの対応するチェッカーを開く
4. URLバー（アドレスバー）にペースト → `Enter` で実行

> ⚠️ **Chrome注意:** URLバーにペーストすると先頭の `javascript:` が自動削除されます。ペースト後に `javascript:` を手入力してください。

- 進化前のポケモンは自動的に最終進化形に変換されます（例: フシギダネ → フシギバナ）
- イーブイ等の分岐進化は手動でポケモン名を選択してください

## ファイル構成

```
pokemonsleep/
├── dump_pokemon_box.py       # メイン: Frida→DB→CSV
├── fetch_missing_tables.py   # 補助: 不足テーブル追加取得
├── pokemon_data.json         # マスターデータ定義（日本語名等）
├── pokemon_box_viewer.html   # CSVビューア（HTML）
├── setup_android.py          # Android端末セットアップ
├── README_ja.md              # 日本語README
├── README.md                 # 英語README
└── .gitignore
```

## 注意事項

- 本ツールは教育・研究目的です
- アプリ由来のデータ（DBファイル、ダンプJSON、CSV）は著作権保護のためgit管理に含めないでください
