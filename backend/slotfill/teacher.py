"""教师端：Word 上传 -> 平台标准提取 -> 21/4/6 筹划模板。

诚实边界（和槽位填充同一条）：
- 提取找不到填 null，不编造；筹划模板的 21/4/6 只是结构（M01-M21 / K01-K04 / I01-I06），
  内容必须由教师 Word 或已配置的模型生成后填入，模板本身不是答案。
- 没有模型配置时，/api/v1/teacher/plan 原样返回模板并注明未生成，不假装生成过。
"""
from __future__ import annotations

import base64
import binascii
import json
from pathlib import Path

from .config import LLMConfig
from .documents import parse_bytes
from .llm import build_client
from .pipeline import run_pipeline

_HERE = Path(__file__).parent


def load_plans() -> dict:
    return json.loads((_HERE / "plans.json").read_text(encoding="utf-8"))


def load_platform_slots() -> dict:
    return json.loads((_HERE / "platform_slots.json").read_text(encoding="utf-8"))


def upload_word(filename: str, docx_base64: str, extractor: str = "auto") -> dict:
    if not filename.lower().endswith(".docx"):
        raise ValueError("只接受 .docx：请上传教师手写的 Word 文档")
    try:
        raw = base64.b64decode(docx_base64, validate=True)
    except binascii.Error:
        raise ValueError("文件内容不是合法 base64")
    if len(raw) > 5 * 1024 * 1024:
        raise ValueError("文档超过 5M 上限")
    doc = parse_bytes(raw, filename)
    llm = None
    if extractor != "code":
        llm = build_client(LLMConfig.from_env())
    result, trace = run_pipeline(document_text=doc.text, slots_payload=load_platform_slots(), extractor=extractor, llm=llm)
    return {"filename": filename, "chars": doc.chars, "text": doc.text, "extraction": result,
            "missing": trace.get("missing", []), "warnings": trace.get("warnings", []), "plans": load_plans()}


def generate_plans(extraction: dict | None) -> dict:
    """有模型时才生成筹划内容；没有模型配置时原样返回模板并注明。"""
    plans = load_plans()
    cfg = LLMConfig.from_env()
    if cfg.mock or not cfg.base_url or not cfg.model or not cfg.api_key:
        plans["generated"] = False
        plans["note"] = "未配置模型（模型配置页填入百炼 Key、地址、模型名后才可生成）；以下为 21/4/6 结构模板，不是生成结果。"
        return plans
    client = build_client(cfg)
    prompt = ("你是星澜数字人教师的筹划助手。根据以下提取结果，分别给出 21 个明确、4 个知、6 个构想，"
              "每项一句话，只输出 JSON，键为 M01-M21、K01-K04、I01-I06，不要多余文字。\n提取结果："
              + json.dumps(extraction or {}, ensure_ascii=False))
    reply = client.chat([{"role": "user", "content": prompt}])
    from .llm import extract_json
    try:
        filled = extract_json(reply)
    except Exception:
        plans["generated"] = False
        plans["note"] = "模型输出无法解析为 JSON，已原样返回模板；请重试或检查模型配置。"
        return plans
    for stage in plans["stages"]:
        for item in stage["items"]:
            if item["id"] in filled:
                item["title"] = str(filled[item["id"]])
                item["status"] = "已生成"
    plans["generated"] = True
    plans["note"] = "已由已配置模型生成；知项仍需人工核对溯源后再用于课堂。"
    return plans
