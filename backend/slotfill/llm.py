"""LLM 客户端：只走 OpenAI 兼容 /chat/completions，标准库 urllib 实现，零依赖。

小模型适配（8b / 27b / 35b 的硬经验，写进提示词和解析两层）：
- temperature 恒为 0；一次只给一个槽位组，不把 50 个槽位塞进一个 prompt。
- 不依赖原生 tool_calls：本地小模型 tool_calls 经常格式漂移，agent 模式改用
  文本 JSON action（{"action": ..., "args": {...}}），解析失败可重试、可修复。
- 不依赖 response_format=json_object：默认关，靠“只输出 JSON”指令 + 后处理修复；
  大模型 / 严格网关再开 LLM_JSON_MODE=1。
- 输出解析三层：直接 json.loads -> 去 ```fence -> 截取首个 {..} / [..] -> 修 trailing comma。
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from typing import Protocol

from .config import LLMConfig


def extract_json(text: str):
    """尽力从模型输出里抠出一个 JSON 对象/数组；抠不出来才报错，不直接丢弃整轮。"""
    if text is None:
        raise ValueError("模型输出为空")
    t = text.strip()
    try:
        return json.loads(t)
    except Exception:
        pass
    m = re.search(r"```(?:json)?\s*(.*?)\s*```", t, flags=re.S | re.I)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            t = m.group(1)
    # 截取最外层 {} 或 []
    start = min([i for i in [t.find("{"), t.find("[")] if i >= 0] or [0])
    end = max(t.rfind("}"), t.rfind("]"))
    if end > start:
        cand = t[start : end + 1]
        try:
            return json.loads(cand)
        except Exception:
            # 修 trailing comma 这一种最常见的小模型毛病
            cand2 = re.sub(r",\s*([}\]])", r"\1", cand)
            return json.loads(cand2)
    raise ValueError(f"无法从模型输出解析 JSON：{text[:300]!r}")


class LLMClient(Protocol):
    def chat(self, messages: list[dict], max_tokens: int | None = None) -> str: ...


class OpenAICompatClient:
    def __init__(self, cfg: LLMConfig):
        cfg.validate()
        self.cfg = cfg

    def chat(self, messages: list[dict], max_tokens: int | None = None) -> str:
        url = self.cfg.base_url.rstrip("/") + "/chat/completions"
        body: dict = {
            "model": self.cfg.model,
            "messages": messages,
            "temperature": self.cfg.temperature,
            "max_tokens": max_tokens or self.cfg.max_tokens,
        }
        if self.cfg.json_mode:
            body["response_format"] = {"type": "json_object"}
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.cfg.api_key}"},
            method="POST",
        )
        last_err: Exception | None = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=self.cfg.timeout) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                choice = payload["choices"][0]["message"]
                # 兼容原生 tool_calls：有则拼成文本返回，agent 层统一解析
                if choice.get("tool_calls"):
                    return json.dumps(choice["tool_calls"], ensure_ascii=False)
                return choice.get("content") or ""
            except (urllib.error.URLError, urllib.error.HTTPError, KeyError, IndexError, ValueError) as e:
                last_err = e
                time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"LLM 调用失败（已重试 3 次）：{last_err}")


class FakeLLM:
    """测试/演示用：按 prompt 里出现的槽位 key 返回预设值。生产绝不用它。

    用法：FakeLLM({"company_name": "ACME", ...})；prompt 里每出现一个 key 就按
    那个 key 的预设值填；没预设的返回 null。测试借此验证管线、校验、合并逻辑，
    而不是假装测了模型智能。
    """

    def __init__(self, values: dict | None = None, sequence: list[str] | None = None, output_format: str = "json"):
        self.values = values or {}
        self.sequence = list(sequence or [])
        self.output_format = output_format
        self.calls: list[list[dict]] = []

    def chat(self, messages: list[dict], max_tokens: int | None = None) -> str:
        self.calls.append(messages)
        if self.sequence:
            return self.sequence.pop(0)
        prompt = "\n".join(m.get("content", "") for m in messages)
        out: dict = {}
        for key, val in self.values.items():
            if f'"{key}"' in prompt or key in prompt or f"{key}:" in prompt:
                out[key] = val
        if self.output_format == "yaml":
            import yaml
            return yaml.safe_dump(out, allow_unicode=True, sort_keys=False)
        return json.dumps(out, ensure_ascii=False)


def build_client(cfg: LLMConfig | None = None) -> LLMClient:
    cfg = cfg or LLMConfig.from_env()
    if cfg.mock:
        return FakeLLM()
    return OpenAICompatClient(cfg)
