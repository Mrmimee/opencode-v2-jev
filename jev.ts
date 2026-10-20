import { spawn } from "node:child_process"
import { existsSync } from "node:fs"
import { homedir } from "node:os"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const BRIDGE = join(dirname(fileURLToPath(import.meta.url)), "jev_bridge.py")
const WIN = process.platform === "win32"
const PYTHON =
  process.env.JEV_PYTHON ||
  join(homedir(), "jev-starter", ".venv", WIN ? "Scripts" : "bin", WIN ? "python.exe" : "python")
const NEVER = new AbortController().signal

const error = (message: string) => JSON.stringify({ error: message, engine: "none" })

function runBridge(tool: string, payload: unknown, signal: AbortSignal): Promise<string> {
  return new Promise((resolve) => {
    if (!existsSync(PYTHON))
      return resolve(error(`未找到 Python 解释器: ${PYTHON}（可用 JEV_PYTHON 覆盖）`))
    if (!existsSync(BRIDGE)) return resolve(error(`未找到桥接脚本: ${BRIDGE}`))

    const child = spawn(PYTHON, [BRIDGE, tool], { windowsHide: true, stdio: ["pipe", "pipe", "pipe"] })
    let stdout = ""
    let stderr = ""
    let done = false

    const finish = (value: string) => {
      if (done) return
      done = true
      signal.removeEventListener("abort", onAbort)
      resolve(value)
    }
    const onAbort = () => {
      child.kill()
      finish(error("Jev 调用已取消"))
    }

    child.stdout.setEncoding("utf8")
    child.stderr.setEncoding("utf8")
    child.stdout.on("data", (chunk) => (stdout += chunk))
    child.stderr.on("data", (chunk) => (stderr += chunk))
    child.on("error", (err) => finish(error(`无法启动 Jev 桥接: ${err.message}`)))
    child.on("close", (code) =>
      finish(stdout.trim() || error(`Jev 桥接退出码 ${code}: ${stderr.trim() || "无输出"}`)),
    )

    if (signal.aborted) return onAbort()
    signal.addEventListener("abort", onAbort, { once: true })
    child.stdin.on("error", () => {})
    child.stdin.end(JSON.stringify(payload))
  })
}

const state = {
  anyOf: [{ type: "string" }, { type: "object" }],
  description: "当前状态；只传与本次判断相关的信息，不要放密钥、凭据或无关个人信息。",
}
const timeoutSeconds = {
  type: "number",
  description: "超时熔断（秒）。默认 jev 15s / jev_guard 45s，上限 120s；超时返回 error，无本地兜底。",
}
const noCache = { type: "boolean", description: "跳过本地缓存，强制实时推理（默认 false）。" }
const common = { state, timeout_seconds: timeoutSeconds, no_cache: noCache }

const question = (intent: string, extra: Record<string, unknown> = {}) => ({
  type: "object",
  properties: {
    name: { type: "string", description: "题名" },
    instructions: { type: "string", description: intent },
    ...extra,
  },
  additionalProperties: false,
})

const choice = {
  ...question("单选意图", {
    criteria: {
      type: "object",
      additionalProperties: { type: "string" },
      description: "选项及含义，如 {'terminal': '命令行', 'browser': '浏览器'}",
    },
  }),
  required: ["criteria"],
}
const noul = question("判断意图")
const score = {
  ...question("打分意图", {
    criteria: { type: "array", items: { type: "string" }, description: "评分梯度，如 ['低','中','高']" },
  }),
  required: ["criteria"],
}

const tools = {
  jev: {
    description:
      "Jev 决策小脑（system_one_adapter → Agnes 3.0 Flash 结构化裁决）：仅在多个工具/执行路径都合理、" +
      "选择确有不确定性时用于路由；普通对话或显而易见的工具选择不要调用。" +
      "单题用 choice/noul/score，多题用 choices/nouls/scores 一次往返批量裁决（默认 15s，典型 4~8s）。" +
      "只返回结构化判断，不替你执行工具。",
    input: {
      type: "object",
      properties: {
        ...common,
        choice,
        choices: { type: "array", items: choice, description: "多个单选题（并发裁决）" },
        noul,
        nouls: { type: "array", items: noul, description: "多个是非题（并发裁决）" },
        score,
        scores: { type: "array", items: score, description: "多个打分题（并发裁决）" },
      },
      required: ["state"],
      additionalProperties: false,
    },
  },
  jev_guard: {
    description:
      "Jev 动作闸门：仅在动作有实质风险、需要第二意见时调用，不替代系统或用户授权。" +
      "并行裁决 5 个信号（策略允许/读取凭据/外发内容/自我游说/破坏半径），再由确定性代码给出 allow/ask/deny。" +
      "较慢（典型 10~40s，默认 45s）；失败只返回 error，不给 verdict，拿不到 verdict 不得当作放行。",
    input: {
      type: "object",
      properties: {
        ...common,
        guard: {
          type: "object",
          properties: {
            instructions: { type: "string", description: "判定意图" },
            threshold: { type: "number", description: "放行阈值 0~1，默认 0.75" },
          },
          additionalProperties: false,
        },
      },
      required: ["state"],
      additionalProperties: false,
    },
  },
}

export default {
  id: "jev",
  async setup(ctx: any) {
    await ctx.tool.transform((editor: any) => {
      for (const [name, def] of Object.entries(tools)) {
        editor.add({
          ...def,
          name,
          execute: async (input: any, context: any) => ({
            content: await runBridge(name, input, context?.signal ?? NEVER),
          }),
        })
      }
    })
  },
}
