# Copilot 活用ナレッジ (Starter)

目的: 開発中に得た Copilot / LLM 利用上の学び・良いプロンプト・改善案を軽量に蓄積し、再利用と品質向上サイクルを作る。

## ディレクトリ概要
- `journal/` : 日次 or セッション毎のログ (成功/失敗/学び/未解決)
- `prompts/` : 再利用価値のあるプロンプトテンプレ
- `patterns/` : 有効だった生成パターン (Before/After/理由)
- `anti-patterns/` : 失敗例と改善形
- `questions/` : 未解決の疑問 (回答後ファイル内へ追記 or `answered-` リネーム)
- `metrics/` : 受け入れ率など計測系 (将来自動化予定)
- `decisions/` : 運用方針やルール (ADR 形式)

## 初期ルール
1. 書くことを迷ったら `journal/今日の日付.md` にメモ → 後で分類
2. 再利用したい/再現性がありそうなプロンプトは `prompts/` に独立
3. 重要な改善は `patterns/` に昇格 (逆に悪い例は `anti-patterns/`)
4. 未解決質問は `questions/open-YYYYMMDD-<slug>.md` 形式
5. 週次で open 質問を棚卸しし、回答済みはファイル末尾に `## Answer` を追記

## 推奨ワークフロー (最小)
```
(開発中)
  └─ メモを journal へ
      └─ 週次: journal → パターン化候補を抽出
          ├─ patterns/ へ昇格
          ├─ anti-patterns/ へ分類
          └─ prompts/ テンプレ整形
```

## 参考メトリクス (後で導入)
| 指標 | 初期取得方法 |
|------|--------------|
| Suggestion Acceptance | 手動カウント (journal) |
| Heavy Rewrite 件数 | journal に “heavy-rewrite” タグ |
| 再利用プロンプト数 | prompts/ ファイル数 |
| 未解決質問残数 | `questions/open-*` の数 |

## 今後の拡張候補
- GitHub Actions で open 質問数バッジ化
- 受け入れ率自動集計スクリプト
- embeddings 検索 (類似質問/プロンプト検索)

---
最初は “書くハードルを極小に” することを優先。慣れたら構造化を追加。
