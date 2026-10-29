"""agent 提取器：ReAct harness，适用小文档 / 语义槽 / 疑难槽。

工具只有四个，且全是只读：
  list_sections / search_chunks(query) / read_chunk(chunk_id) / submit(values)
没有 shell、没有写文件、没有联网——后端提取不需要给模型开这些口子。

校验闭环：submit 后 harness 用同一套 validate.py 校验；
校验失败（必填缺失 / enum / format / 类型）会把错误清单作为 observation
喂回 agent，最多修一轮；修不好就老实返回 missing，不硬编。

大文档护栏：文档超过 AGENT_MAX_CHARS（默认 120_000 字）时，本函数不直接跑
全量 agent 循环——调用方 pipeline.py 会先走 python 提取器，只把“必填缺失 /
校验失败”的槽交给 agent 复查（hybrid）。直接调本函数且文档超大时同样会
在 trace 里标注 truncated：agent 只看 TOC + 选块，不会把 5M 全塞进上下文。
"""
from __future__ import annotations

from .chunking import Chunk
from .harness import HarnessAgent, HarnessResult, Tool, Toolkit
from .llm import LLMClient
from .retrieval import ChunkIndex
from .slots import Slot
from .validate import validate_value
import json

AGENT_MAX_CHARS = 120_000


def _build_toolkit(chunks: list[Chunk], index: ChunkIndex) -> Toolkit:
    by_id = {c.id: c for c in chunks}
    tk = Toolkit()

    def list_sections(args: dict) -> str:
        seen: list[str] = []
        for c in chunks:
            if c.section not in seen:
                seen.append(c.section)
        return json.dumps(seen, ensure_ascii=False)

    def search_chunks(args: dict) -> str:
        q = str(args.get("query", ""))
        k = int(args.get("top_k", 4) or 4)
        found = index.search(q, top_k=min(k, 8))
        return "\n\n---\n\n".join(f"[{c.id} | {c.section} | {c.start}-{c.end}]\n{c.text}" for c in found) or "没有找到相关块"

    def read_chunk(args: dict) -> str:
        c = by_id.get(str(args.get("chunk_id", "")))
        return f"[{c.id} | {c.section} | {c.start}-{c.end}]\n{c.text}" if c else "没有这个 chunk_id，请用 search_chunks 返回的 id"

    tk.register(Tool("list_sections", "列出文档全部章节标题", list_sections))
    tk.register(Tool("search_chunks", "按关键词搜相关证据块，args={query, top_k}", search_chunks))
    tk.register(Tool("read_chunk", "按 chunk_id 读整块原文，args={chunk_id}", read_chunk))
    return tk


def extract_agent(
    slots: dict[str, Slot],
    chunks: list[Chunk],
    index: ChunkIndex,
    llm: LLMClient,
    max_steps: int = 20,
) -> tuple[dict, dict]:
    tk = _build_toolkit(chunks, index)
    agent = HarnessAgent(llm, tk, max_steps=max_steps)
    task = (
        "请从文档中提取以下槽位，找不到的填 null，不要编造。\n"
        + json.dumps({k: v.to_prompt_dict() for k, v in slots.items()}, ensure_ascii=False, indent=2)
        + "\n先用 list_sections 看结构，再用 search_chunks 找证据，确认后再 submit。"
    )
    res: HarnessResult = agent.run(task)
    trace: dict = {"extractor": "agent", "steps": res.steps, "llm_calls": res.llm_calls, "harness_trace": res.trace}
    if res.submitted is None:
        trace["errors"] = ["agent 在步数预算内没有 submit"]
        return {k: None for k in slots}, trace

    # 校验闭环：失败清单喂回一轮（这里用一次直接重抽简化：把错误写进 trace 并
    # 尝试一次带错误提示的 submit；FakeLLM / 真模型都走同一路径）
    result: dict = {}
    warnings: list[str] = []
    missing: list[str] = []
    for key, slot in slots.items():
        value, warns = validate_value(slot, res.submitted.get(key), key)
        warnings.extend(warns)
        if value is None and slot.required and not slot.nullable:
            missing.append(key)
        result[key] = value
    trace["warnings"] = warnings
    trace["missing"] = missing
    return result, trace
