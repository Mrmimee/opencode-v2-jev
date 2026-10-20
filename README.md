# opencode-v2-jev

Jev decision engine for **OpenCode V2** — registers two tools that return structured judgements
instead of chat text:

- `jev` — Choice / Noul (yes-no) / Score questions, single or batched, one round trip.
- `jev_guard` — 5 risk signals → deterministic `allow` / `ask` / `deny` verdict.

> 中文名：Jev 决策小脑（OpenCode V2 原生插件版）。一次网络往返拿结构化裁决，不做聊天。

## Architecture

```
OpenCode V2 plugin (jev.ts)
  └─ HTTPS → Agnes Chat Completions (agnes-3.0-flash)
```

Self-contained: **no Python, no bridge, no Hermes dependency**. The plugin only needs an
Agnes API key (or any OpenAI-compatible endpoint); prompts, JSON-schema output, validation, retry, cache and the guard logic all live in `jev.ts`.

## Requirements

- OpenCode **2.x** (V2 plugin API: default export `{ id, setup }`)
- An Agnes API key (`AGNES_API_KEY`, or `apikey.txt` on the Desktop)

## Install

Copy the plugin into your OpenCode plugins directory:

```powershell
# Windows
Copy-Item jev.ts "$env:USERPROFILE\.config\opencode\plugins\"
```

```bash
# macOS / Linux
cp jev.ts ~/.config/opencode/plugins/
```

OpenCode watches that directory and reloads the plugin automatically. A restart also works.

### Key resolution

1. `AGNES_API_KEY` environment variable.
2. `~/OneDrive/桌面/apikey.txt` or `~/Desktop/apikey.txt` — the line after `AgnesAi`.

```powershell
setx AGNES_API_KEY "<your-key>"
```

### Model

Default: `agnes-3.0-flash` on `https://apihub.agnes-ai.com/v1`.

Any OpenAI-compatible chat endpoint can be used instead:

```powershell
setx JEV_BASE_URL "http://127.0.0.1:3425/v1"   # base URL, no /chat/completions
setx JEV_MODEL "qoder/qfmodel"
setx JEV_API_KEY "magpie"                       # omit to reuse AGNES_API_KEY
```

Restart OpenCode after changing these; they are read at plugin load.

### Proxy

The plugin runs on Bun and uses the system `HTTPS_PROXY` / `HTTP_PROXY` when present.
No proxy configuration inside the plugin.

## Usage

```json
{
  "state": "context relevant to this decision only",
  "choice": {
    "name": "route",
    "instructions": "Which path fits best?",
    "criteria": { "terminal": "read in the shell", "browser": "open a page" }
  },
  "nouls": [{ "name": "reversible", "instructions": "Can this be undone?" }],
  "score": { "name": "effort", "instructions": "How much work?", "criteria": ["low", "medium", "high"] }
}
```

Batch multiple questions in one call with `choices` / `nouls` / `scores`.

```json
{ "state": "delete cache files older than 7 days", "guard": { "threshold": 0.75 } }
```

### Defaults

- Timeout: `jev` 15s, `jev_guard` 45s (max 120s). Override with `timeout_seconds`.
- Cache: in-process LRU, 256 entries, 1 hour TTL; keyed by state + questions.
  `no_cache: true` forces a fresh call. Restarting OpenCode clears it.
- `state` is redacted before being sent (tokens, keys, `password=` and similar fields).
- Malformed model output is corrected and retried once.
- Transient network failures and HTTP 429/5xx are retried once within the time budget.

### Failure semantics

There is **no local fallback**. Missing key, timeout, or an invalid response returns `error`.
An `error` never means "allowed".

## Verify

Call the tool once from OpenCode:

```json
{
  "state": "health check",
  "noul": { "name": "alive", "instructions": "Is the service responding?" },
  "no_cache": true
}
```

Expected: `answers.alive` plus `"engine": "agnes"`.

Check the log for plugin loading:

```powershell
Select-String -Path "$env:USERPROFILE\.local\share\opencode\log\opencode.log" -Pattern "jev.ts"
```

## Notes

- Aborting a tool call cancels the in-flight request.
- Batching questions amortizes the round trip; prefer one call with `choices`/`nouls` over several.
- The engine returns structured answers only; it never executes tools.

## License

MIT
