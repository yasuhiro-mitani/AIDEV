# Repository Guidelines

## Project Structure & Module Organization
All source lives under `src/`. `src/server/index.js` is a lightweight Express wrapper that serves the static assets in `src/client/`. The Pomodoro timer UI, styles, and logic are contained in `src/client/index.html`; no bundler is used, so edits here ship directly. Metadata and scripts stay in `package.json`, while this guide and the README sit at the repo root.

## Build, Test, and Development Commands
- `npm install` - install dependencies (only Express for the static server).
- `npm run dev` - start the local server on `PORT` (defaults to 3000) and host the timer at `/`.
- `npm start` - identical entry point intended for simple deployments.
If you serve the HTML from a different platform (e.g., static hosting), document the steps in the README.

## Coding Style & Naming Conventions
Use ESM modules (`type: "module"`) and keep scripting minimal—JavaScript for the timer lives inline in `index.html`. Stick to 2-space indentation, semicolons, and single quotes in JS. When editing CSS, respect the existing utility-style variables and avoid broad restyles without need.

## Testing Guidelines
No automated tests exist today. If you introduce one (e.g., a Playwright smoke test), place it under `tests/` with a `*.test.js` suffix and expose it via `npm test`. Focus on validating timer transitions, auto-start behavior, and settings persistence.

## Commit & Pull Request Guidelines
Use Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`) with optional scopes like `ui` or `server` (e.g., `feat(ui): add notification chime`). Pull requests should describe user-visible changes, include reproduction steps, and link any relevant issues. Update the README and this guide whenever you alter run scripts or app behavior.

## Agent Notes
- コミュニケーションに合わせて日本語/英語を切り替え、指示を簡潔に反映してください。
- 変更はタイマー機能に集中させ、大規模な依存追加や再構成は事前相談を行ってください。
