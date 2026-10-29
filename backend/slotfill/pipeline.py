"""编排层：槽位设计 -> 提取器设计 -> 方案文件 -> 槽位填充。

模式（extractor 参数，API/CLI 通用）：
  code   = 代码逻辑提取，零 LLM，最快；语义槽一定缺失
  llm    = LLM 提取（YAML 输出，Python 转 JSON），python 是它的旧别名
  hybrid = 代码先行 + LLM 只补缺（缺失/低置信/语义），默认推荐，速度与准确率折中
  agent  = ReAct harness，小文档/疑难槽专用
  auto   = 先跑代码，覆盖率满且无语义缺失就直接返回（0 LLM 调用）；
           否则走 hybrid；LLM 未配置时退化为代码档

完整性多阶段兜底（保证“错版、标题错乱也不丢槽”）：
  阶段 0 代码容错解析（破表/混分隔符/断行/重复键/标题归一化）
  阶段 1 LLM 扩大选块重试（llm/hybrid 档内）
  阶段 2 全文格式/枚举扫描（代码档的 format/enum 本来就扫全文，不是只扫候选块）
  阶段 3 agent 复查（仅 auto 且仍有必填缺失、文档 <=120K 字、且显式允许时，
           默认不开，避免小文档以外的速度失控）
  每一阶段只填仍缺失的槽，不覆盖已校验通过的高置信结果；最终 missing 清单
  和每槽的填充阶段都写进 trace，完整率是可审计的，不是口头保证。
"""
from __future__ import annotations
import time
from .chunking import chunk_document
from .documents import Document, parse_bytes, parse_text
from .extract_agent import AGENT_MAX_CHARS, extract_agent
from .extract_code import extract_code
from .extract_hybrid import extract_hybrid
from .extract_llm import extract_llm
from .llm import LLMClient
from .retrieval import ChunkIndex
from .slots import parse_slots

ALIASES = {"python": "llm", "py": "llm"}


def run_pipeline(document_text: str | None = None, document_bytes: bytes | None = None,
                 document_filename: str = "", document_type: str = "txt",
                 slots_payload: dict | None = None, extractor: str = "auto",
                 llm: LLMClient | None = None, chunk_chars: int = 8000, chunk_overlap: int = 800,
                 output_format: str = "yaml", concurrency: int = 4,
                 agent_fallback: bool = False) -> tuple[dict, dict]:
    t0 = time.perf_counter()
    if slots_payload is None:
        raise ValueError("缺少槽位 JSON")
    slots = parse_slots(slots_payload)
    if document_bytes is not None:
        doc = parse_bytes(document_bytes, document_filename)
    elif document_text is not None:
        doc = parse_text(document_text, document_type)
    else:
        raise ValueError("缺少文档：document_text / document_bytes 二选一")
    chunks = chunk_document(doc, chunk_chars=chunk_chars, overlap=chunk_overlap)
    index = ChunkIndex(chunks)
    mode = ALIASES.get(extractor, extractor)
    if mode not in ("code", "llm", "hybrid", "agent", "auto"):
        raise ValueError(f"extractor 非法：{extractor!r}，只支持 code / llm / hybrid / agent / auto（python 是 llm 的旧别名）")
    stages: list[str] = []
    if mode == "code":
        result, trace, _ = extract_code(slots, doc.text, chunks)
        stages.append("code")
    elif mode == "llm":
        if llm is None:
            raise ValueError("llm 模式需要配置模型（.env），或改用 code / hybrid（无模型时退化为代码档）")
        result, trace = extract_llm(slots, chunks, index, llm, output_format=output_format, concurrency=concurrency)
        stages.append("llm")
    elif mode == "hybrid":
        result, trace = extract_hybrid(slots, doc.text, chunks, index, llm,
                                       output_format=output_format, concurrency=concurrency)
        stages.append("hybrid")
    elif mode == "agent":
        if llm is None:
            raise ValueError("agent 模式需要配置模型")
        result, trace = extract_agent(slots, chunks, index, llm)
        stages.append("agent")
    else:  # auto
        code_result, code_trace, _ = extract_code(slots, doc.text, chunks)
        stages.append("code(auto-first)")
        has_semantic_missing = any(s.type == "semantic" and code_result.get(k) is None for k, s in slots.items())
        required_missing = [k for k, s in slots.items() if s.required and not s.nullable and code_result.get(k) is None]
        if not required_missing and not has_semantic_missing:
            result, trace = code_result, code_trace
        elif llm is None:
            result, trace = code_result, code_trace
            trace["auto_note"] = "未配置 LLM，auto 退化为代码档"
        else:
            result, trace = extract_hybrid(slots, doc.text, chunks, index, llm,
                                           output_format=output_format, concurrency=concurrency)
            stages.append("hybrid(auto)")
    # 阶段 3：agent 复查（仅显式开启 + 小文档 + 仍有必填缺失）
    if agent_fallback and llm is not None and doc.chars <= AGENT_MAX_CHARS:
        missing_now = [k for k, s in slots.items() if s.required and not s.nullable and result.get(k) is None]
        if missing_now:
            missing_slots = {k: slots[k] for k in missing_now}
            agent_result, agent_trace = extract_agent(missing_slots, chunks, index, llm)
            for k, v in agent_result.items():
                if v is not None:
                    result[k] = v
            trace["agent_fallback"] = agent_trace
            stages.append("agent-fallback")
    required_all = [k for k, s in slots.items() if s.required and not s.nullable]
    final_missing = [k for k in required_all if result.get(k) is None]
    trace.update({
        "extractor_requested": extractor, "extractor_used": mode, "stages": stages,
        "document_chars": doc.chars, "document_type": doc.source_type,
        "chunk_count": len(chunks), "slot_count": len(slots),
        "sections": [s.title for s in doc.sections],
        "image_count": len(doc.images),
        "missing": final_missing,
        "coverage": {
            "filled": sum(1 for v in result.values() if v is not None), "total": len(slots),
            "filled_required": sum(1 for k in required_all if result.get(k) is not None),
            "total_required": len(required_all),
        },
        "elapsed_seconds": round(time.perf_counter() - t0, 3),
    })
    return result, trace
