# Metrics (Planned)

現時点では手動収集。将来的に自動化予定。

## 指標一覧 (v0)
| Key | 説明 | 収集方法(初期) | メモ |
|-----|------|---------------|------|
| acceptance_rate | 提案受け入れ率 | journal 手集計 | 週次平均を記録予定 |
| heavy_rewrite_count | 大幅書換回数 | journal タグ | 3回以上ならパターン化検討 |
| reusable_prompt_count | prompts/ の有効テンプレ数 | ファイル数 | 月次増加を追跡 |
| open_questions | 未解決質問数 | `questions/open-*` カウント | 減少速度で改善度合い |
| pattern_adoption | patterns/ 参照回数 | 手動メモ → 後でリンク解析 | 需要指標 |

## 収集サイクル
- 日次: journal 更新
- 週次: open 質問棚卸し / acceptance 集計
- 月次: patterns/ と anti-patterns/ の整理

## 将来の自動化案
- pre-commit で `Copilot:` プレフィックス解析 → acceptance 推定
- GitHub Actions で open 質問数バッジ生成
- 簡易 CLI で `journal` 追記と同時に CSV へ書き出し
