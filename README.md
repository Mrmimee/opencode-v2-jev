# jev-opencode-v2

Jev decision engine for **OpenCode V2** — registers two tools that return structured judgements
instead of chat text:

- `jev` — Choice / Noul (yes-no) / Score questions, single or batched, one round trip.
- `jev_guard` — 5 risk signals → deterministic `allow` / `ask` / `deny` verdict.

> 中文名：Jev 决策小脑（OpenCode V2 插件版）。一次网络往返拿结构化裁决，不做聊天。

## Architecture

```
OpenCode V2 plugin (jev.ts)
  └─ spawns jev_bridge.py (your Python venv)
       └─ loads the Hermes jev plugin
            └─ system_one_adapter → Agnes 3.0 Flash
```

`jev.ts` contains **no API keys** and performs no network calls itself; all inference happens
through the Python bridge.

## Requirements

- OpenCode **2.x** (V2 plugin API: default export `{ id, setup }`)
- Python 3.10+ with `system-one-adapter[openai]`
- The Hermes jev plugin at `%LOCALAPPDATA%\hermes\plugins\jev\__init__.py`
  (override with `JEV_HERMES_PLUGIN`)
- `AGNES_API_KEY` (the Hermes plugin can also read it from `apikey.txt`)

## Install

Copy both files into your OpenCode plugins directory:

```powershell
# Windows
Copy-Item jev.ts, jev_bridge.py "$env:USERPROFILE\.config\opencode\plugins\"
```

```bash
# macOS / Linux
cp jev.ts jev_bridge.py ~/.config/opencode/plugins/
```

OpenCode watches that directory and reloads the plugin automatically. A restart also works.

### Environment

```powershell
setx JEV_PYTHON "%USERPROFILE%\jev-starter\.venv\Scripts\python.exe"
setx AGNES_API_KEY "<your-key>"   # skip if the Hermes plugin already resolves a key
```

| Variable | Default | Purpose |
| :-- | :-- | :-- |
| `JEV_PYTHON` | `~/jev-starter/.venv/Scripts/python.exe` | Python interpreter that has `system_one_adapter` |
| `JEV_HERMES_PLUGIN` | `%LOCALAPPDATA%/hermes/plugins/jev/__init__.py` | Path to the Hermes jev plugin |
| `AGNES_API_KEY` | — | Agnes API key (never logged) |

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
- Cache: keyed by `state` + questions; `no_cache: true` forces a fresh call.
- `state` is redacted before being sent (tokens, keys, `password=` and similar fields).

### Failure semantics

There is **no local fallback**. Engine failure, timeout, or a missing verdict returns `error`.
An `error` never means "allowed".

## Verify

```powershell
'{"state":"health check","noul":{"name":"alive","instructions":"Is the bridge responding?"},"timeout_seconds":15,"no_cache":true}' |
  & "$env:USERPROFILE\jev-starter\.venv\Scripts\python.exe" `
    "$env:USERPROFILE\.config\opencode\plugins\jev_bridge.py" jev
```

Then check the OpenCode log for plugin loading:

```powershell
Select-String -Path "$env:USERPROFILE\.local\share\opencode\log\opencode.log" -Pattern "jev.ts"
```

## Notes

- Aborting a tool call kills the Python bridge process.
- Transient connection errors are retried once when the time budget allows.
- Each call starts a fresh Python process (~1.7s overhead); batching questions amortizes it.
- Requires the Hermes jev implementation; this repository is the OpenCode adapter, not the engine.

## License

MIT
