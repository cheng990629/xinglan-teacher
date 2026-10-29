"""校验门：Python 说了算，LLM 说了不算。

这是整个程序最关键的一层，也是它和“直接调 LLM 返回 JSON”的区别：
LLM 只负责“找值、给候选”，最终进结果 JSON 之前，必须过这一关。
过不了的：要么自动纠正（可纠正的格式/类型），要么进 repair 再抽一次，
要么老实标 missing/null，绝不把一个看起来像的值蒙混过去。
"""
from __future__ import annotations

import re
from datetime import datetime

from .slots import Slot

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_CN_DATE = re.compile(r"^(\d{4})年(\d{1,2})月(\d{1,2})日")
_CN_DATETIME = re.compile(r"^(\d{4})年(\d{1,2})月(\d{1,2})日\s*(\d{1,2})[:：](\d{1,2})(?::(\d{1,2}))?")


def _coerce_number(v):
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return v
    if isinstance(v, str):
        s = v.strip().replace(",", "").replace("，", "")
        s = re.sub(r"[元¥￥$%]", "", s)
        m = re.search(r"-?\d+(\.\d+)?", s)
        if m:
            num = float(m.group(0))
            return int(num) if num.is_integer() else num
    raise ValueError(f"无法转成 number：{v!r}")


def _coerce_bool(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("true", "yes", "是", "有", "1", "t", "y"):
            return True
        if s in ("false", "no", "否", "无", "0", "f", "n"):
            return False
    raise ValueError(f"无法转成 boolean：{v!r}")


def _check_format(fmt: str, v: str) -> str:
    if fmt == "email" and not _EMAIL.match(v):
        raise ValueError(f"不是合法 email：{v!r}")
    if fmt == "uuid" and not _UUID.match(v):
        raise ValueError(f"不是合法 uuid：{v!r}")
    if fmt == "date":
        m = _CN_DATE.match(v)
        if m:
            return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        # 错版日期：2026/10/29、2026.10.29 先归一化成 - 再校验，不因分隔符丢槽
        v_norm = v.strip().replace("/", "-").replace(".", "-")
        try:
            return datetime.strptime(v_norm[:10], "%Y-%m-%d").strftime("%Y-%m-%d")
        except ValueError:
            raise ValueError(f"不是合法 date（YYYY-MM-DD）：{v!r}")
    if fmt == "datetime":
        m = _CN_DATETIME.match(v)
        if m:
            hh, mm, ss = int(m.group(4)), int(m.group(5)), int(m.group(6) or 0)
            return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}T{hh:02d}:{mm:02d}:{ss:02d}"
        try:
            return datetime.fromisoformat(v.strip().replace("Z", "+00:00")).isoformat()
        except ValueError:
            raise ValueError(f"不是合法 datetime：{v!r}")
    # phone / url 等未知或宽松格式：只做非空检查，不硬拦（避免小模型被误杀）
    return v


def validate_value(slot: Slot, value, path: str) -> tuple[object, list[str]]:
    """返回 (纠正后的值, 警告列表)。缺失/非法时值返回 None，警告里说明原因。"""
    warnings: list[str] = []
    if value is None:
        if slot.required and not slot.nullable:
            warnings.append(f"{path}: 必填但缺失")
        return None, warnings
    if isinstance(value, str) and value.strip() == "":
        if slot.required and not slot.nullable:
            warnings.append(f"{path}: 必填但为空字符串")
        return None, warnings

    try:
        if slot.type == "string" or slot.type == "semantic":
            v = str(value)
            if slot.length_max is not None and len(v) > slot.length_max:
                warnings.append(f"{path}: 超长 {len(v)} > {slot.length_max}，已截断")
                v = v[: slot.length_max]
            if slot.length_min is not None and len(v) < slot.length_min:
                warnings.append(f"{path}: 过短 {len(v)} < {slot.length_min}")
            if slot.format:
                v = _check_format(slot.format, v)
            if slot.enum is not None and v not in slot.enum:
                # 大小写/空白容错一次
                for e in slot.enum:
                    if str(e).strip().lower() == v.strip().lower():
                        v = e
                        break
                else:
                    warnings.append(f"{path}: 不在 enum {slot.enum} 内：{v!r}")
                    return None, warnings
            return v, warnings

        if slot.type == "number":
            v = _coerce_number(value)
            if slot.enum is not None and v not in slot.enum:
                warnings.append(f"{path}: 不在 enum 内：{v!r}")
                return None, warnings
            return v, warnings

        if slot.type == "boolean":
            return _coerce_bool(value), warnings

        if slot.type == "object":
            if not isinstance(value, dict):
                warnings.append(f"{path}: 应为 object，实际是 {type(value).__name__}")
                return None, warnings
            out: dict = {}
            for k, sub in slot.properties.items():
                sub_v, sub_w = validate_value(sub, value.get(k), f"{path}.{k}")
                out[k] = sub_v
                warnings.extend(sub_w)
            return out, warnings

        if slot.type == "array":
            if not isinstance(value, list):
                warnings.append(f"{path}: 应为 array，实际是 {type(value).__name__}")
                return None, warnings
            if slot.length_max is not None and len(value) > slot.length_max:
                warnings.append(f"{path}: 数组超长 {len(value)} > {slot.length_max}，已截断")
                value = value[: slot.length_max]
            if slot.length_min is not None and len(value) < slot.length_min:
                warnings.append(f"{path}: 数组过短 {len(value)} < {slot.length_min}")
            out = []
            if slot.items is None:
                return list(value), warnings
            for i, item in enumerate(value):
                iv, iw = validate_value(slot.items, item, f"{path}[{i}]")
                out.append(iv)
                warnings.extend(iw)
            return out, warnings

    except ValueError as e:
        warnings.append(f"{path}: {e}")
        return None, warnings
    warnings.append(f"{path}: 未知类型 {slot.type}")
    return None, warnings
