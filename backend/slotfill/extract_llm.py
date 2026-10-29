"""LLM 提取器：分组 + YAML 输出 + Python 转 JSON + 并发。

为什么默认 YAML 而不是 JSON（见 yaml_output.py）：
小模型输出 JSON 常因引号未转义、尾逗号、括号不配对整轮作废；
YAML plain scalar 不需要转义中文和引号，解析成功率更高，
最后统一由 Python 转成标准 JSON，下游永远拿到 JSON。

速度：
- 分组：候选块重合的槽位并成一组，组内上限 8 个槽，证据总量可控；
- 并发：组与组之间用 ThreadPoolExecutor 并行调模型（LLM_CONCURRENCY，默认 4，
  本地单卡模型请设 1-2，否则排队反而变慢；FakeLLM 测试时强制串行保确定性）。
"""
from __future__ import annotations
import json
from concurrent.futures import ThreadPoolExecutor
from .chunking import Chunk
from .llm import LLMClient, extract_json
from .retrieval import ChunkIndex
from .slots import Slot
from .validate import validate_value
from .yaml_output import YAML_SYSTEM_RULES, parse_yaml_output

MAX_SLOTS_PER_GROUP = 8


def _evidence_text(chunks: list[Chunk]) -> str:
    parts = []
    for c in chunks:
        parts.append(f"[{c.id} | 章节：{c.section} | 字符 {c.start}-{c.end}]\n{c.text}")
    return "\n\n---\n\n".join(parts)


def _group_slots(slots: list[Slot], index: ChunkIndex, top_k: int):
    cand: dict[str, list[Chunk]] = {}
    for s in slots:
        cand[s.key] = index.top_chunks(s, top_k=top_k)
    groups: list[tuple[list[Slot], dict[str, Chunk]]] = []
    for s in slots:
        placed = False
        for g_slots, g_chunks in groups:
            if len(g_slots) >= MAX_SLOTS_PER_GROUP:
                continue
            overlap = len(set(c.id for c in cand[s.key]) & set(g_chunks))
            if overlap >= 1 or not g_chunks:
                g_slots.append(s)
                for c in cand[s.key]:
                    g_chunks[c.id] = c
                placed = True
                break
        if not placed:
            groups.append(([s], {c.id: c for c in cand[s.key]}))
    return [(gs, list(cs.values())) for gs, cs in groups]


def _prompt_for_group(group: list[Slot], chunks: list[Chunk], output_format: str) -> list[dict]:
    defs = {s.key: s.to_prompt_dict() for s in group}
    if output_format == "yaml":
        system = "\n".join([
            "你是槽位提取器。extractive 规则：值必须能在证据里找到依据，找不到填 null，绝不编造、绝不把相近数值当成答案。",
            "semantic 规则：用证据综合成一段归纳，不超过 length.max 字，不编造证据里没有的事实。",
            "number 只输出数字，不要带单位/逗号；boolean 只输出 true/false；enum 只能从给定列表里选；date 输出 YYYY-MM-DD。",
            "object 按 properties 展开，array 按 items 展开；数组元素缺失不要补编造的元素。",
        ] + YAML_SYSTEM_RULES)
    else:
        system = ("你是槽位提取器，只输出一个 JSON 对象，key 就是槽位 key，不要加解释、不要用 markdown 包裹。"
                  "找不到填 null，绝不编造；number 只输出数字，boolean 只输出 true/false，enum 只能从给定列表里选，date 输出 YYYY-MM-DD。")
    user = ("槽位定义：\n" + json.dumps(defs, ensure_ascii=False, indent=2)
            + "\n\n证据（只看这些，不要用证据以外的知识）：\n" + _evidence_text(chunks)
            + ("\n\n请输出 YAML：" if output_format == "yaml" else "\n\n请输出 JSON："))
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _call_group(llm, group, chunks, output_format):
    messages = _prompt_for_group(group, chunks, output_format)
    out_text = llm.chat(messages)
    if output_format == "yaml":
        parsed, used = parse_yaml_output(out_text)
    else:
        parsed, used = extract_json(out_text), "json"
    if not isinstance(parsed, dict):
        parsed = {}
    return parsed, used


def extract_llm(slots: dict[str, Slot], chunks: list[Chunk], index: ChunkIndex, llm: LLMClient,
                top_k: int = 4, output_format: str = "yaml", concurrency: int = 4) -> tuple[dict, dict]:
    top_slots = list(slots.values())
    groups = _group_slots(top_slots, index, top_k=top_k)
    raw_values: dict = {}
    trace: dict = {"extractor": "llm", "output_format": output_format, "groups": [], "llm_calls": 0, "formats_used": []}
    # FakeLLM 的 sequence 模式不是线程安全的，测试时强制串行
    use_concurrency = concurrency if (concurrency and concurrency > 1 and llm.__class__.__name__ != "FakeLLM") else 1
    def _run(g):
        group, group_chunks = g
        try:
            parsed, used = _call_group(llm, group, group_chunks, output_format)
            return group, group_chunks, parsed, used, None
        except Exception as e:
            return group, group_chunks, {}, None, str(e)
    results = []
    if use_concurrency > 1:
        with ThreadPoolExecutor(max_workers=use_concurrency) as ex:
            results = list(ex.map(_run, groups))
    else:
        results = [_run(g) for g in groups]
    for group, group_chunks, parsed, used, err in results:
        trace["llm_calls"] += 1
        if err:
            trace.setdefault("errors", []).append(f"组 {[s.key for s in group]} 抽取失败：{err}")
        if used:
            trace["formats_used"].append(used)
        raw_values.update(parsed)
        trace["groups"].append({"slots": [s.key for s in group], "chunks": [c.id for c in group_chunks]})
    result: dict = {}
    warnings: list[str] = []
    missing: list[str] = []
    for key, slot in slots.items():
        value, warns = validate_value(slot, raw_values.get(key), key)
        warnings.extend(warns)
        if value is None and slot.required:
            wider = index.top_chunks(slot, top_k=top_k + 4)
            try:
                parsed, used = _call_group(llm, [slot], wider, output_format)
                trace["llm_calls"] += 1
                trace["formats_used"].append(used)
                retry_v = parsed.get(key) if isinstance(parsed, dict) else None
                value, warns2 = validate_value(slot, retry_v, key)
                warnings.extend(warns2)
                trace.setdefault("retries", []).append({"slot": key, "chunks": [c.id for c in wider]})
            except Exception as e:
                trace.setdefault("errors", []).append(f"槽位 {key} 重试失败：{e}")
        if value is None and slot.required and not slot.nullable:
            missing.append(key)
        result[key] = value
    trace["warnings"] = warnings
    trace["missing"] = missing
    return result, trace
