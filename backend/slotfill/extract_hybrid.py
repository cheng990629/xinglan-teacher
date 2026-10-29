"""混合提取器：代码先行，LLM 只补缺，速度和准确率的折中点，也是默认推荐档。

流程：
  1. 代码档全量跑一遍（零 LLM 调用，最快）；
  2. 只把这些槽交给 LLM：必填缺失、低置信度（<0.8）、校验警告、semantic 槽；
     高置信度的代码结果不重抽，省调用、也避免 LLM 把对的改错；
  3. LLM 结果只在校验通过且非空时才覆盖代码结果；
  4. 仍缺失的必填槽，记进 missing，不编造。

省调用账：50 个槽里代码能解决 40 个，LLM 只需要跑 10 个槽的组，
而不是 50 个槽全量跑一遍——这就是混合档“速度要快”的主要来源。
"""
from __future__ import annotations
from .chunking import Chunk
from .extract_code import extract_code
from .extract_llm import extract_llm
from .llm import LLMClient
from .retrieval import ChunkIndex
from .slots import Slot
from .validate import validate_value

LOW_CONFIDENCE = 0.8


def extract_hybrid(slots: dict[str, Slot], doc_text: str, chunks: list[Chunk], index: ChunkIndex,
                   llm: LLMClient | None, top_k: int = 4, output_format: str = "yaml",
                   concurrency: int = 4) -> tuple[dict, dict]:
    code_result, code_trace, confidences = extract_code(slots, doc_text, chunks)
    need: dict[str, Slot] = {}
    reasons: dict[str, str] = {}
    for key, slot in slots.items():
        if slot.type == "semantic":
            need[key] = slot
            reasons[key] = "semantic-needs-llm"
        elif code_result.get(key) is None and slot.required:
            need[key] = slot
            reasons[key] = "code-missing-required"
        elif code_result.get(key) is None:
            # 非必填缺失也补一次，但优先级低：如果 LLM 也没有，仍是 null，不算 missing
            need[key] = slot
            reasons[key] = "code-missing"
        elif confidences.get(key, 0) < LOW_CONFIDENCE:
            need[key] = slot
            reasons[key] = f"code-low-confidence-{confidences.get(key, 0)}"
        elif code_trace["slots"][key]["warnings"]:
            need[key] = slot
            reasons[key] = "code-validation-warning"
    trace: dict = {"extractor": "hybrid", "code_trace": code_trace, "llm_slots": list(need),
                   "llm_reasons": reasons, "llm_calls": 0}
    result = dict(code_result)
    if not need:
        trace["missing"] = code_trace["coverage"] and [k for k, s in slots.items() if result.get(k) is None and s.required and not s.nullable]
        trace["coverage"] = code_trace["coverage"]
        return result, trace
    if llm is None:
        trace["llm_skipped"] = "未配置 LLM，混合档退化为代码档"
        trace["missing"] = [k for k, s in slots.items() if result.get(k) is None and s.required and not s.nullable]
        trace["coverage"] = code_trace["coverage"]
        return result, trace
    llm_result, llm_trace = extract_llm(need, chunks, index, llm, top_k=top_k,
                                        output_format=output_format, concurrency=concurrency)
    trace["llm_calls"] = llm_trace.get("llm_calls", 0)
    trace["llm_trace"] = llm_trace
    for key, slot in need.items():
        lv = llm_result.get(key)
        if lv is not None:
            # LLM 结果已经在 extract_llm 里校验过；只有非空才覆盖
            result[key] = lv
    required = [k for k, s in slots.items() if s.required and not s.nullable]
    trace["missing"] = [k for k in required if result.get(k) is None]
    trace["coverage"] = {
        "filled": sum(1 for v in result.values() if v is not None), "total": len(slots),
        "filled_required": sum(1 for k in required if result.get(k) is not None), "total_required": len(required),
    }
    return result, trace
