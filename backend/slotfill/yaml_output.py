"""LLM 输出格式：优先 YAML，Python 转 JSON。

为什么 YAML 比 JSON 更可靠（尤其对 8b/27b 小模型）：
1. JSON 怕引号和换行：值里一个没转义的 " 或真实换行，整个 JSON 就解析失败，
   而且失败位置经常在文件尾，修都没法修。
2. JSON 怕尾逗号、括号不配对：小模型最常见的两种毛病，都会让整轮作废。
3. YAML 的 plain scalar 不需要给中文、引号加转义，长文本还能用块标量，
   模型只要把 key 对齐、值写对，解析成功率明显高于 JSON。
4. 类型转换交给 Python：yaml.safe_load 之后再递归转成 JSON 兼容类型
   （date/datetime -> ISO 字符串），下游永远拿到标准 JSON，不用再猜模型给的是什么。

流程：LLM 输出 YAML -> yaml.safe_load -> 转 JSON 兼容 -> validate.py 校验。
YAML 解析失败时才回退到 JSON 抠取（兼容老模型/老 prompt），回退路径要记进 trace，
不能静默混用两种格式。
"""
from __future__ import annotations

import datetime
import json
import re

from .llm import extract_json


def _strip_fence(text: str) -> str:
    m = re.search(r"```(?:yaml|yml)?\s*(.*?)\s*```", text or "", flags=re.S | re.I)
    return m.group(1) if m else (text or "").strip()


def to_jsonable(value):
    """yaml.safe_load 会把 2026-10-29 解析成 date 对象，必须转回字符串，否则 json.dumps 报错。"""
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(v) for v in value]
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _scalar(s: str):
    s = s.strip().strip("\"'")
    if s in ("null", "~", "Null", "NULL", ""):
        return None
    if s.lower() == "true":
        return True
    if s.lower() == "false":
        return False
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s


def _parse_simple_yaml_lines(text: str) -> dict:
    """行级 YAML 容错：只认顶层 key: value、缩进 - 列表、缩进 key: value 两层结构。
    用于模型输出缩进错乱、引号未闭合等错版 YAML，宁可抠出顶层字段，也不要整轮丢弃。
    """
    out: dict = {}
    current_key = None
    current_list = None
    current_obj = None
    for raw_line in text.splitlines():
        line = raw_line.replace("\t", "  ")
        if not line.strip() or line.strip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()
        if indent == 0 and ":" in stripped and not stripped.startswith("-"):
            key, val = stripped.split(":", 1)
            key, val = key.strip(), val.strip()
            if not key or " " in key:
                continue
            current_key = key
            if val == "":
                current_list = None
                current_obj = {}
                out[key] = current_obj
            elif val.startswith("[") and val.endswith("]"):
                out[key] = [_scalar(x) for x in val[1:-1].split(",") if x.strip()]
                current_list, current_obj = None, None
            else:
                out[key] = _scalar(val)
                current_list, current_obj = None, None
        elif indent > 0 and current_key is not None:
            if stripped.startswith("- "):
                if current_list is None:
                    current_list = []
                    out[current_key] = current_list
                    current_obj = None
                current_list.append(_scalar(stripped[2:]))
            elif ":" in stripped and current_obj is not None:
                k2, v2 = stripped.split(":", 1)
                current_obj[k2.strip()] = _scalar(v2)
    return out


def parse_yaml_output(text: str) -> tuple[dict, str]:
    """返回 (解析后的 dict, 实际用到的格式 'yaml'|'json-fallback')。"""
    cleaned = _strip_fence(text)
    try:
        import yaml
    except ImportError as e:  # pragma: no cover
        raise ValueError("YAML 模式需要 PyYAML：pip install pyyaml（或把 LLM_OUTPUT_FORMAT 改回 json）") from e
    try:
        parsed = yaml.safe_load(cleaned)
    except Exception:
        parsed = None
    if isinstance(parsed, dict):
        return to_jsonable(parsed), "yaml"
    # YAML 解析失败 / 解析出非 dict：回退 JSON 抠取，再不行才报错
    try:
        parsed_json = extract_json(text)
        if isinstance(parsed_json, dict):
            return to_jsonable(parsed_json), "json-fallback"
    except Exception:
        pass
    # 最后一道：行级容错解析——YAML 缩进错乱、引号未闭合时，逐行抠顶层键值，保证不整轮作废
    try:
        line_parsed = _parse_simple_yaml_lines(cleaned)
        if line_parsed:
            return to_jsonable(line_parsed), "yaml-line-fallback"
    except Exception:
        pass
    raise ValueError(f"YAML 和 JSON 都解析失败，模型输出前 300 字：{text[:300]!r}")


YAML_SYSTEM_RULES = [
    "只输出 YAML，不要输出任何解释、不要用 markdown 包裹之外的文字。",
    "key 必须和槽位 key 完全一致；object 用缩进映射，array 用 - 开头的一行一个元素。",
    "找不到的值填 null，不要编造；number 不要带单位和逗号，boolean 只写 true/false，date 写 YYYY-MM-DD。",
    "字符串一般不需要引号；只有值里含冒号、# 号、开头是引号时才加双引号；长文本不要自己断行加引号。",
    "示例：",
    "company_name: 沈阳晨光科技有限公司",
    "contract_amount: 1250000",
    "is_long_term: true",
    "deliverables:",
    "  - 需求文档",
    "  - 原型系统",
]
