# HN日報 — Hacker News 日本語まとめ

Hacker News のトップ記事を、日本語タイトル・一言メモ・コメント要約付きで読める静的サイトです。

- 取得: 公式 HN API（トップ30）
- 更新: 1日3回（JST 7:00 / 12:00 / 23:00）
- 公開: `docs/` を GitHub Pages または Cloudflare Pages にデプロイ

## ローカル実行

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 任意: OpenRouter キーがあるとコメント要約の精度が上がります
cp .env.example .env

python -m scripts.fetch_and_generate --slot 23
python -m http.server 8080 --directory docs
```

## GitHub Actions

`.github/workflows/update.yml` がスケジュール実行します。

リポジトリ Secrets に次を設定してください。

| Secret | 必須 | 説明 |
|--------|------|------|
| `OPENROUTER_API_KEY` | 推奨 | コメント要約・編集メモ用 |

未設定でもタイトルの日本語化とページ生成は動きます（要約は簡易フォールバック）。

## サイト構成

```
docs/
  index.html          # 最新スナップショット
  archive/            # 過去の取得結果
  data/               # JSON スナップショット
  assets/             # CSS / favicon
  feed.xml            # RSS
```
