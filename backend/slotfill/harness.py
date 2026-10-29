"""Harness 核心：AgentScope 可借鉴的部分，只取骨架，不取全套。

借鉴自 AgentScope（见 README 对照表）：
- ReAct 循环：reason（LLM 决策）-> act（调工具）-> observe（把结果喂回去），直到
  submit 或步数/调用预算耗尽。
- Toolkit：工具注册表 + 统一的“工具名 + JSON 参数 + 文本结果”契约。
- Hook：在循环关键点插钩子（本程序只用三个：before_llm / after_tool / on_error），
  不搞 AgentScope 那种全量中间件链。

刻意不借鉴的（后端批处理不需要，反而是负担）：
- 会话持久化 / 双层记忆 / 对话压缩：槽位填充是一次性任务，状态 = 本次 job 的
  trace 文件，不需要跨会话“记得用户”。
- 工作区人格（AGENTS.md / MEMORY.md 注入）：槽位定义就是本次任务的全部“人格”，
  注入工作区文件只会污染 prompt、浪费小模型上下文。
- 流式 SSE / 多租户 RuntimeContext：强约束要求出参是结果 JSON 的 URL（非 SSE），
  所以 harness 跑完才落盘，不流式。
- 沙箱 shell：后端提取不需要给模型开 shell，工具只限读块/搜块/提交，攻击面最小。

小模型适配：工具调用不用原生 tool_calls，用文本 JSON action；
解析失败时把错误当作 observation 喂回去，让模型自己纠正一次，而不是直接崩。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from .llm import LLMClient, extract_json


@dataclass
class Tool:
    name: str
    desc: str
    func: object  # (args: dict) -> str


class Toolkit:
    def __init__(self):
        self.tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self.tools[tool.name] = tool

    def describe(self) -> str:
        lines = []
        for t in self.tools.values():
            lines.append(f"- {t.name}: {t.desc}")
        return "\n".join(lines)

    def call(self, name: str, args: dict) -> str:
        tool = self.tools.get(name)
        if tool is None:
            return f"错误：没有这个工具 {name}，可用工具：{', '.join(self.tools)}"
        try:
            out = tool.func(args)  # type: ignore[misc]
            return str(out)
        except Exception as e:  # 工具异常不炸循环，变成 observation
            return f"工具 {name} 执行失败：{e}"


@dataclass
class HarnessResult:
    submitted: dict | None
    steps: int
    llm_calls: int
    trace: list[dict] = field(default_factory=list)


class HarnessAgent:
    """最小 ReAct harness：LLM 每轮只输出一个 JSON action，harness 执行并回填结果。"""

    SYSTEM = (
        "你是一个槽位提取 agent。你只能通过工具读取文档，不能凭空编造。\n"
        "每轮只输出一个 JSON，格式必须是：\n"
        '{"action": "search_chunks|read_chunk|list_sections|submit", "args": {...}}\n'
        "search_chunks 的 args：{\"query\": \"...\", \"top_k\": 4}\n"
        "read_chunk 的 args：{\"chunk_id\": \"c0000\"}\n"
        "list_sections 的 args：{}\n"
        "submit 的 args：{\"values\": {槽位 key: 值}}，值缺失用 null，不要编。\n"
        "不要输出任何解释文字，不要用 markdown 包裹 JSON。"
    )

    def __init__(self, llm: LLMClient, toolkit: Toolkit, max_steps: int = 20, max_llm_calls: int = 25):
        self.llm = llm
        self.toolkit = toolkit
        self.max_steps = max_steps
        self.max_llm_calls = max_llm_calls
        self.hooks: dict[str, list] = {"before_llm": [], "after_tool": [], "on_error": []}

    def on(self, event: str, fn) -> None:
        self.hooks.setdefault(event, []).append(fn)

    def _emit(self, event: str, payload) -> None:
        for fn in self.hooks.get(event, []):
            try:
                fn(payload)
            except Exception:
                pass

    def run(self, task: str) -> HarnessResult:
        messages: list[dict] = [
            {"role": "system", "content": self.SYSTEM + "\n可用工具：\n" + self.toolkit.describe()},
            {"role": "user", "content": task},
        ]
        trace: list[dict] = []
        llm_calls = 0
        for step in range(self.max_steps):
            if llm_calls >= self.max_llm_calls:
                break
            self._emit("before_llm", {"step": step})
            raw = self.llm.chat(messages)
            llm_calls += 1
            trace.append({"step": step, "llm_output": raw[:2000]})
            try:
                action = extract_json(raw)
                name, args = action["action"], action.get("args") or {}
            except Exception as e:
                self._emit("on_error", {"step": step, "error": str(e), "raw": raw})
                messages.append({"role": "user", "content": f"你的输出不是合法 JSON action，错误：{e}。请只输出一个 JSON action。"})
                continue
            if name == "submit":
                values = args.get("values")
                if isinstance(values, str):
                    try:
                        from .yaml_output import parse_yaml_output
                        values, _used = parse_yaml_output(values)
                    except Exception as e:
                        messages.append({"role": "user", "content": f"submit 的 YAML 解析失败：{e}，请重发。"})
                        continue
                if not isinstance(values, dict):
                    messages.append({"role": "user", "content": "submit 的 values 必须是 object，请重发。"})
                    continue
                return HarnessResult(submitted=values, steps=step + 1, llm_calls=llm_calls, trace=trace)
            result = self.toolkit.call(name, args)
            self._emit("after_tool", {"step": step, "tool": name, "result_len": len(result)})
            trace.append({"step": step, "tool": name, "result": result[:2000]})
            messages.append({"role": "user", "content": f"工具 {name} 的结果：\n{result}\n请继续：下一步只输出一个 JSON action。"})
        return HarnessResult(submitted=None, steps=self.max_steps, llm_calls=llm_calls, trace=trace)
