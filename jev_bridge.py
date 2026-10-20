"""OpenCode V2 -> Hermes Jev bridge.

Reads tool args as JSON on stdin, calls the Hermes Jev handler, prints JSON on stdout.

Env:
  JEV_HERMES_PLUGIN  path to the Hermes jev __init__.py
  AGNES_API_KEY      optional; the Hermes plugin also falls back to apikey.txt
"""
import importlib.util
import json
import os
import sys
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", category=UserWarning)

DEFAULTS = {"jev": 15.0, "jev_guard": 45.0}
TRANSIENT = ("Connection error", "TypeSafeAPIConnectionError", "APIConnectionError")
LOCAL = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
PLUGIN = Path(os.environ.get("JEV_HERMES_PLUGIN") or LOCAL / "hermes" / "plugins" / "jev" / "__init__.py")


def _emit(payload: dict) -> None:
    sys.stdout.buffer.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    sys.stdout.buffer.flush()


def _fail(message: str) -> None:
    _emit({"error": message, "engine": "none", "latency_seconds": 0.0})
    os._exit(0)


def _transient(result: str) -> bool:
    try:
        payload = json.loads(result)
    except Exception:
        return False
    return isinstance(payload, dict) and any(m in str(payload.get("error", "")) for m in TRANSIENT)


def main() -> None:
    tool = sys.argv[1] if len(sys.argv) > 1 else "jev"
    try:
        raw = sys.stdin.buffer.read().decode("utf-8").strip()
        args = json.loads(raw) if raw else {}
    except Exception as exc:
        _fail(f"无法解析请求参数: {exc}")
        return
    if not isinstance(args, dict):
        _fail("请求参数必须是 JSON 对象")
        return
    if not PLUGIN.is_file():
        _fail(f"未找到 Hermes jev 插件: {PLUGIN}")
        return

    args.setdefault("timeout_seconds", DEFAULTS.get(tool, 15.0))
    try:
        spec = importlib.util.spec_from_file_location("hermes_jev_plugin", PLUGIN)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        handler = getattr(module, "_handle_jev_guard" if tool == "jev_guard" else "_handle_jev")

        started = time.monotonic()
        result = str(handler(args))
        # 上游偶发瞬时断连，预算够就重试一次。
        if _transient(result):
            budget = float(args["timeout_seconds"]) - (time.monotonic() - started)
            if budget > 3:
                result = str(handler({**args, "timeout_seconds": round(budget - 0.5, 2), "no_cache": True}))

        # 缓存写盘挂在后台线程，退出前同步刷一次。
        try:
            module._save_disk_cache()
        except Exception:
            pass
    except Exception as exc:
        _fail(f"Jev 执行失败: {type(exc).__name__}: {exc}")
        return

    sys.stdout.buffer.write(result.encode("utf-8"))
    sys.stdout.buffer.flush()
    os._exit(0)  # 后台线程可能仍在等网络，跳过解释器关闭


if __name__ == "__main__":
    main()
