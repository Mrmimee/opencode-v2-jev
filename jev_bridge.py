"""OpenCode V2 -> Hermes Jev bridge.

Reads tool args as JSON from stdin, calls the Hermes Jev handler, and prints
the JSON result on stdout.

Env overrides:
  JEV_HERMES_PLUGIN  path to the Hermes jev __init__.py
  AGNES_API_KEY      optional; the Hermes plugin also falls back to apikey.txt
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", category=UserWarning)

DEFAULT_TIMEOUT_SECONDS = 15.0
TRANSIENT_MARKERS = ("Connection error", "TypeSafeAPIConnectionError", "APIConnectionError")

DEFAULT_PLUGIN = (
    Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    / "hermes"
    / "plugins"
    / "jev"
    / "__init__.py"
)


def _emit(payload: dict) -> None:
    sys.stdout.buffer.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    sys.stdout.buffer.flush()


def _fail(message: str) -> None:
    _emit({"error": message, "engine": "none", "latency_seconds": 0.0})
    os._exit(0)


def _is_transient_error(result: str) -> bool:
    try:
        payload = json.loads(result)
    except Exception:
        return False
    if not isinstance(payload, dict) or not payload.get("error"):
        return False
    message = str(payload.get("error"))
    return any(marker in message for marker in TRANSIENT_MARKERS)


def main() -> None:
    tool_name = sys.argv[1] if len(sys.argv) > 1 else "jev"
    try:
        raw = sys.stdin.buffer.read().decode("utf-8")
        args = json.loads(raw) if raw.strip() else {}
    except Exception as exc:
        _fail(f"无法解析请求参数: {exc}")
        return

    plugin_path = Path(os.environ.get("JEV_HERMES_PLUGIN") or DEFAULT_PLUGIN)
    if not plugin_path.is_file():
        _fail(f"未找到 Hermes jev 插件: {plugin_path}")
        return

    try:
        spec = importlib.util.spec_from_file_location("hermes_jev_plugin", plugin_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"无法加载模块: {plugin_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)

        handler = getattr(module, "_handle_jev_guard" if tool_name == "jev_guard" else "_handle_jev")
        started = time.monotonic()
        result = str(handler(args))

        # 上游偶发瞬时连接错误（TypeSafeAPIConnectionError），预算允许时重试一次。
        if _is_transient_error(result):
            budget = float(args.get("timeout_seconds") or DEFAULT_TIMEOUT_SECONDS) - (
                time.monotonic() - started
            )
            if budget > 3.0:
                retry_args = dict(args)
                retry_args["timeout_seconds"] = round(budget - 0.5, 2)
                retry_args["no_cache"] = True
                result = str(handler(retry_args))

        # The handler schedules the disk cache write on a background executor;
        # flush it synchronously because we exit the process immediately below.
        try:
            module._save_disk_cache()
        except Exception:
            pass
    except Exception as exc:
        _fail(f"Jev 执行失败: {type(exc).__name__}: {exc}")
        return

    sys.stdout.buffer.write(str(result).encode("utf-8"))
    sys.stdout.buffer.flush()
    # Background executor threads may still be waiting on the network after a
    # timeout; skip interpreter shutdown so the tool returns immediately.
    os._exit(0)


if __name__ == "__main__":
    main()
