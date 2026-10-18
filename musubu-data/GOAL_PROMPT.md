# ゴール: Musubu 全セクション read-only API 収集の完遂

Canonical copy of the armed `/goal` objective. See `musubu_cursor_status.json` for live progress.

## 背景

Musubu（https://app.production.musubu.in）のデータを、UI/CSV ではなく **正規 read API のみ** で取得し、**gzip** として Google Drive に保存する。Collector: `scripts/musubu_collect.py` on branch `cursor/musubu-resume-c549`.

## 正（仕様・参照）

| 項目 | 場所 |
|------|------|
| Drive フォルダ | `1kR8pPEahMbgj4ErAzHxCqwU85tMPL8Ea` |
| 仕様書 | `musubu-api-data.md`, `musubu-api-endpoints.md` |
| ローカル出力 | `/workspace/musubu-data/` |
| チェックポイント | `musubu_cursor_checkpoint_20261018.json` |
| 進捗サマリー | `musubu_cursor_status.json` → Drive |

## 非交渉条件

1. API のみ。レート **≥2.2s**、**並列1**。
2. JSON 妥当性、gzip、`raw_sha256` / `gzip_sha256` を manifest / checkpoint に記録。
3. トークン・パスワードを git / ログ / PR に出さない。
4. 上書き禁止: `key_people_page_00001–00003.json.gz`、既存 `companies_pages_*.tar.gz`（1–1833、page 70 欠損・71 重複は監査のみ）。

## パッケージング

- Key people **page 4+**: `key_people_pages_{start:05d}-{end:05d}.tar.gz` every **200** pages (4–203, 204–403, …).
- `search_range` auto-packs complete 200-page windows.
- Pages 1–3 remain legacy `.json.gz` on Drive.

## 作業順序

- **Phase A:** key_people fetch → 58552 (tmux `musubu-kp-fetch`)
- **Phase B:** Drive publish tar/b64 + SHA
- **Phase C:** companies page 70 + 1834+
- **Phase D:** departments, offices, stores, facilities, recruits (last)
- **Phase E:** audit, `status: complete`

## 完了定義

Sections 1–9 API-complete, Drive artifacts + SHA verified, checkpoint `status: complete`, PR updated.
