# 日付カウントダウン

ローカルで動作する、シンプルな日付カウントダウン Web アプリです。ブラウザの `localStorage` に最後に設定したイベントが保存されます。PWA 対応（ホーム画面追加・オフライン対応）と、到達時の音/バイブ通知に対応しています。

## 使い方

1. フォルダを開く: `date-countdown/`
2. PC で簡易サーバーから配信（PWAのため推奨）: 例 `npx serve date-countdown`
   - 直接 `index.html` を開く（file://）でも動きますが、Service Worker は有効になりません。
3. スマホで `http://<PCのIP>:<ポート>/` にアクセス、または PC ブラウザで開く
3. 「イベント名」と「日時」を入力して「開始」
4. カウントダウンが 1 秒ごとに更新されます。リセットで設定をクリアできます。

### スマホのホーム画面に追加（PWA）
- Android Chrome: メニュー → 「ホーム画面に追加」
- iOS Safari: 共有シート → 「ホーム画面に追加」

※ 初回アクセスはオンライン（ローカルサーバー経由）で開いてください。以降はオフラインでも動作します。

## 実装メモ

- 入力: `datetime-local` を使用（ローカルタイムで指定）
- 表示: `toLocaleString('ja-JP', { dateStyle: 'full', timeStyle: 'short' })`
- 保存: `localStorage` に `{ title, targetMs }` を保存
- 更新: `setInterval` で 1 秒間隔に更新（到達で停止）
- 通知: 到達時に `navigator.vibrate()` と Web Audio で短いビープ音
- PWA: `manifest.webmanifest` と `sw.js` によるオフライン対応（キャッシュファースト）

### アイコン（PNG 192/512）
- 実行時に Canvas で 192/512px の PNG を生成し、`favicon`/`apple-touch-icon` と動的 Manifest に適用します。
- Android Chrome の PWA で高解像度のアイコンとして利用されます。
- iOS Safari のホーム画面アイコンは PNG ファイルパスが推奨です。データURLは使えない場合があります（その場合はページのスクリーンショットが使われます）。

## 注意事項

- インターネット接続やサーバは不要です。静的ファイルのみで動作します。
- 過去日時は開始できません（現在時刻以下は無効）。
 - PWA（ホーム画面追加/オフライン）は HTTPS か `http://localhost` などのサーバ経由でのみ有効です。
