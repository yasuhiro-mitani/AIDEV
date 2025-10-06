# Countdown App

マルチターゲットのカウントダウン PWA。オフライン利用可。ローカルに複数の目標日を保存し残り時間を表示します。

## 特徴
- 複数ターゲット日: タイトルと日時を入力して追加
- 自動更新: 1秒ごとに残り時間を再計算
- 永続化: `localStorage` に保存（ブラウザ単位）
- PWA: オフラインキャッシュ / ホーム画面追加
- ダーク/ライト対応 (prefers-color-scheme)

## 毎朝通知の実現方法
ブラウザのみで「毎朝定時通知」を安定的に行うには制約があります。目的別に選択肢をまとめます。

### 1. ローカル通知 (Service Worker + Push 未使用)
ブラウザのタブが開いている、または SW が維持される状況で `Notification` API を使い、アプリ起動時に「今日まだ通知していなければ即時通知」パターンを採用。
- Pros: サーバ不要
- Cons: 完全な指定時刻に必ずは鳴らない（SW は任意時刻に自動起床しない）
- 実装案: 起動/フォーカス時に最後に通知した日を `localStorage` に記録し未通知なら通知

### 2. Web Push + サーバ(推奨)
1日1回 (例: 08:00 JST) の定期バッチ（cron）で対象ユーザの Push Subscription に通知を送信。
- Pros: 閉じていても受信。信頼性高
- Cons: サーバ必須。VAPID キー管理が必要

実装ステップ概要:
1. フロント: `Notification.requestPermission()` と `navigator.serviceWorker.ready` で `pushManager.subscribe({ userVisibleOnly: true, applicationServerKey })`
2. サーバ: VAPID キー生成 (`web-push` ライブラリ)
3. サブスクリプション(エンドポイント+鍵)を保存 (例: DB)
4. cron (例: Cloud Scheduler, GitHub Actions, Node cron) で `webpush.sendNotification(subscription, payload)` を送信
5. SW の `push` イベントで `self.registration.showNotification()`

### 3. ネイティブアプリ化 (Capacitor / React Native 等)
App Store / Google Play 配信し OS のローカルスケジュール通知を使用。
- Pros: 最も正確
- Cons: コスト増

## 今後の拡張案
- Push 通知用エンドポイント (Express) 追加
- サブスクリプション管理 API: `POST /api/push/subscribe` / `DELETE /api/push/subscribe`
- 指定時刻ごとの個別通知 (複数ターゲットそれぞれに朝リマインド)
- エクスポート / インポート (JSON)
- ソート / フィルタ (締切の近い順など)

## ローカルでの動作
既存の Express サーバがあるなら、`countdownApp` ディレクトリを静的配信に追加するか、`/countdown` パスで提供します。単体で試すには VSCode の簡易静的サーバや `npx serve countdownApp` などを利用。

## 制約メモ
- ブラウザのみでは cron 的な正確な「毎朝 08:00」を完全保証できない
- iOS Safari の Push 対応は iOS 16.4+ のホーム画面追加 PWA で利用可能

## 次の選択肢
Push 通知バックエンド実装が必要であれば依頼してください。概要設計～実装を進めます。

## Push 通知セットアップ手順 (サーバ + フロント)

1. VAPIDキー生成
```
npx web-push generate-vapid-keys
```
出力された `publicKey` / `privateKey` を環境変数に設定:
```
set VAPID_PUBLIC_KEY=...  # Windows PowerShell: $env:VAPID_PUBLIC_KEY="..."
set VAPID_PRIVATE_KEY=... # PowerShell: $env:VAPID_PRIVATE_KEY="..."
```

2. サーバ起動
```
npm run dev
```

3. ブラウザで `http://localhost:3000/countdownApp/` を開き、「通知を有効化」押下 → 権限許可

4. テスト通知
フロントの「テスト通知送信」ボタン、または curl:
```
curl -X POST http://localhost:3000/api/push/test
```

5. 毎朝通知時刻
環境変数 `PUSH_DAILY_HOUR_UTC` (0–23) で UTC 時刻を指定。例: 日本時間 08:00 ≒ 23 UTC (前日)
```
set PUSH_DAILY_HOUR_UTC=23
```

6. 本番移行注意
- メモリストア→DBへ (subscriptions)
- 適切な `mailto:` を設定
- HTTPS 必須 (localhost を除く)
- タイムゾーン処理は Luxon/Temporal 等で明示的に

### サブスクリプション削除
```
curl -X DELETE http://localhost:3000/api/push/subscribe \
	-H "Content-Type: application/json" \
	-d '{"endpoint":"<endpoint URL>"}'
```

### 既知の制限
- 現在は UTC 時刻で単純比較
- Daily 通知はサーバ常駐が前提 (外部 cron サービス推奨)
- エラーハンドリングと再送戦略は最小限
