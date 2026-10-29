"""槽位定义编译：把用户给的 slots JSON 编译成一棵 Slot 树，并校验定义本身。

用户格式（强约束示例，不低于它）：
  {"slots": {"name": {"desc": "...", "type": "string|number|boolean|object|array|semantic",
                      "required": true, "length": {"min": 0, "max": 100},
                      "enum": [...], "format": "email|date|datetime|uuid|...",
                      "nullable": true, "items": {...}, "properties": {...}}}}

语义约定（本程序的硬规定，写进 README，不让 LLM 猜）：
- string：length = 字符数；array：length = 元素个数；object：length 忽略。
- semantic：值一定是 string，是“综合归纳”不是“原文照抄”；长度同样受 length 约束。
- items：数组元素的槽位定义（可以是 primitive，也可以是带 properties 的 object）。
- properties：object 子槽位的 dict，key -> 槽位定义。
- 未填：必填缺失进 missing；非必填缺失统一输出 null（消费端不用猜 key 在不在）。
"""
from __future__ import annotations

from dataclasses import dataclass, field

TYPES = {"string", "number", "boolean", "object", "array", "semantic"}
FORMATS = {"email", "date", "datetime", "uuid", "phone", "url"}


@dataclass
class Slot:
    key: str
    desc: str = ""
    type: str = "string"
    required: bool = False
    nullable: bool = False
    length_min: int | None = None
    length_max: int | None = None
    enum: list | None = None
    format: str | None = None
    items: "Slot | None" = None
    properties: dict[str, "Slot"] = field(default_factory=dict)

    def is_leaf(self) -> bool:
        return self.type not in ("object", "array")

    def to_prompt_dict(self) -> dict:
        """给 LLM 的精简版定义：只保留它需要决策的信息，不塞冗余。"""
        d: dict = {"desc": self.desc, "type": self.type, "required": self.required}
        if self.length_min is not None or self.length_max is not None:
            d["length"] = {"min": self.length_min, "max": self.length_max}
        if self.enum:
            d["enum"] = self.enum
        if self.format:
            d["format"] = self.format
        if self.nullable:
            d["nullable"] = True
        if self.type == "object" and self.properties:
            d["properties"] = {k: v.to_prompt_dict() for k, v in self.properties.items()}
        if self.type == "array" and self.items:
            d["items"] = self.items.to_prompt_dict()
        return d

    def keywords(self) -> list[str]:
        """确定性选块用的关键词：key 切分 + desc 分词 + enum 值，不依赖 embedding。"""
        import re

        words: list[str] = []
        # key：snake_case / camelCase 切分
        for part in re.split(r"[^A-Za-z0-9\u4e00-\u9fff]+", self.key):
            if part:
                words.append(part)
            for sub in re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])", part):
                words.append(sub)
        words += re.findall(r"[\u4e00-\u9fff]+|[A-Za-z0-9]+", self.desc or "")
        if self.enum:
            for e in self.enum:
                words += re.findall(r"[\u4e00-\u9fff]+|[A-Za-z0-9]+", str(e))
        seen, out = set(), []
        for w in words:
            lw = w.lower()
            if lw not in seen and len(lw) >= 1:
                seen.add(lw)
                out.append(w)
        return out


def _parse_slot(key: str, raw: dict, path: str) -> Slot:
    if not isinstance(raw, dict):
        raise ValueError(f"槽位 {path} 定义必须是 object，实际是 {type(raw).__name__}")
    typ = raw.get("type", "string")
    if typ not in TYPES:
        raise ValueError(f"槽位 {path} 的 type 非法：{typ!r}，只支持 {sorted(TYPES)}")
    fmt = raw.get("format")
    if fmt is not None and fmt not in FORMATS:
        # 未知 format 不直接拒收：校验时只做“已知格式才校验”，但定义里要留痕
        pass
    length = raw.get("length") or {}
    if not isinstance(length, dict):
        raise ValueError(f"槽位 {path} 的 length 必须是 object")
    slot = Slot(
        key=key,
        desc=str(raw.get("desc", "") or ""),
        type=typ,
        required=bool(raw.get("required", False)),
        nullable=bool(raw.get("nullable", False)),
        length_min=length.get("min"),
        length_max=length.get("max"),
        enum=list(raw["enum"]) if isinstance(raw.get("enum"), list) else None,
        format=fmt,
    )
    if typ == "object":
        props = raw.get("properties") or {}
        if not isinstance(props, dict):
            raise ValueError(f"槽位 {path} 的 properties 必须是 object")
        slot.properties = {k: _parse_slot(k, v, f"{path}.{k}") for k, v in props.items()}
    if typ == "array":
        items = raw.get("items")
        if items is not None:
            slot.items = _parse_slot("items", items, f"{path}[]")
    if not slot.desc and typ != "object":
        raise ValueError(f"槽位 {path} 缺少 desc：没有描述的槽位没法选块、没法让小模型抽准")
    return slot


def parse_slots(payload: dict) -> dict[str, Slot]:
    """入口只认 {"slots": {...}}；同时兼容直接传 {...} 的情况（容错，不鼓励）。"""
    if not isinstance(payload, dict):
        raise ValueError("槽位 JSON 顶层必须是 object")
    raw = payload.get("slots", payload)
    if not isinstance(raw, dict) or not raw:
        raise ValueError("槽位 JSON 里没有 slots，或 slots 为空")
    return {k: _parse_slot(k, v, k) for k, v in raw.items()}


def flatten_slots(slots: dict[str, Slot]) -> list[Slot]:
    """展平：object 的子槽、array 的 items 都展开，供选块/分组用；路径用 key 保留。"""
    out: list[Slot] = []

    def walk(slot: Slot, prefix: str) -> None:
        out.append(slot)
        if slot.type == "object":
            for k, sub in slot.properties.items():
                walk(sub, f"{prefix}.{k}")
        if slot.type == "array" and slot.items:
            walk(slot.items, f"{prefix}[]")

    for k, s in slots.items():
        walk(s, k)
    return out
