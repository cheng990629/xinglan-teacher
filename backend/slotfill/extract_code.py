"""代码逻辑提取器：零 LLM、纯 Python 规则，速度最快的一档。

适用：标签化、表格化、格式化的文档（合同、发票、简历、订单……）。
不适用：语义归纳（semantic）、纯散文里藏着的隐含信息——那些交给 LLM/混合档。
诚实边界：代码档填不出来的槽，返回 null + 原因，不编造；混合档再交给 LLM 补。

错版容错（本文件是主战场）：
- 分隔符混用：全角：、半角:、=、【】、**粗体**、多空格分隔，统一认；
- 破表：缺首尾 |、列数不齐、分隔行缺失、表头即数据行，全部按“含 | 的连续行”成组、按最长行补齐；
- 断行：键值行的值被换行切断时，把后续无标签行拼回值里；
- 重复键：保留全部候选，取置信度最高的，不静默丢弃；
- 标题错乱：不依赖标题层级，只用归一化后的标题文字做章节匹配；
- 数字/日期/邮箱错版：中文数字、中文日期、带空格的邮箱、点/斜杠日期，全部先纠正再校验。
"""
from __future__ import annotations
import re
from .retrieval import tokenize
from .slots import Slot
from .validate import validate_value

_CN_DIGIT = {"零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
             "两": 2, "壹": 1, "贰": 2, "叁": 3, "肆": 4, "伍": 5, "陆": 6, "柒": 7, "捌": 8, "玖": 9}
_CN_UNIT = {"十": 10, "拾": 10, "百": 100, "佰": 100, "千": 1000, "仟": 1000, "万": 10000, "萬": 10000, "亿": 100000000, "億": 100000000}


def parse_cn_number(s: str):
    """中文数字 -> float，支持'一百二十五万'、'壹佰贰拾伍万元'这类合同常见写法。"""
    s = s.strip().replace("元", "").replace("整", "")
    if not s or not any(c in _CN_DIGIT or c in _CN_UNIT for c in s):
        return None
    total, cur, tmp = 0, 0, 0
    for c in s:
        if c in _CN_DIGIT:
            tmp = _CN_DIGIT[c]
        elif c in _CN_UNIT:
            u = _CN_UNIT[c]
            if u >= 10000:
                total = (total + cur + (tmp or 0)) * u if (cur or tmp) else total * u
                cur, tmp = 0, 0
            else:
                cur += (tmp or 1) * u
                tmp = 0
        else:
            return None
    return float(total + cur + tmp)


def parse_number_value(s: str):
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return s
    t = str(s).strip().replace(",", "").replace("，", "")
    m = re.search(r"-?\d+(\.\d+)?", t)
    if m:
        v = float(m.group(0))
        if "亿" in t:
            v *= 100000000
        elif "万" in t:
            v *= 10000
        return int(v) if v.is_integer() else v
    return parse_cn_number(t)


def _clean_str(v: str) -> str:
    v = str(v).strip().strip("\"'“”‘’")
    v = re.sub(r"[。；;]\s*$", "", v)
    # 尾部说明性括号剥离：XXX（以下简称甲方）-> XXX；只剥“以下/简称/下称”类说明，不动“（红色）”这类实质内容
    m = re.search(r"[（(]([^）)]*(?:以下|简称|下称)[^）)]*)[）)]\s*$", v)
    if m:
        v = v[:m.start()].strip()
    return v.strip()


def _parse_kv(line: str):
    """一行键值解析，容错分隔符。返回 (key, value) 或 None。"""
    s = line.strip()
    if not s or s.startswith("|"):
        return None
    s = re.sub(r"^[-*•·]\s*", "", s)
    m = re.match(r"^\u3010(.+?)\u3011\s*(.+)$", s)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    m = re.match(r"^\*\*(.+?)\*\*\s*[：:]\s*(.+)$", s)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    m = re.match(r"^(.{1,40}?)\s*[：:＝=]\s*(.+)$", s)
    if m and not any(p in m.group(1) for p in "。，；、"):
        return m.group(1).strip(), m.group(2).strip()
    m = re.match(r"^(.{1,20}?)\s{2,}(.+)$", s)
    if m and not any(p in m.group(1) for p in "。，；"):
        return m.group(1).strip(), m.group(2).strip()
    return None


def _parse_tables(lines: list[str]):
    """容错表格解析：连续含 | 的行成组，分隔行跳过，列数按最长行补齐。"""
    tables = []
    cur: list[list[str]] = []
    for line in lines:
        s = line.strip()
        if "|" in s and len(s) >= 3:
            cells = [c.strip() for c in s.strip("|").split("|")]
            if all(re.fullmatch(r"[-: ]+", c) for c in cells):
                continue  # 分隔行：|---|---|，不是数据
            cur.append(cells)
        else:
            if len(cur) >= 2:
                tables.append(cur)
            cur = []
    if len(cur) >= 2:
        tables.append(cur)
    out = []
    for rows in tables:
        w = max(len(r) for r in rows)
        rows = [r + [""] * (w - len(r)) for r in rows]
        out.append({"header": rows[0], "rows": rows[1:]})
    return out


class CodeContext:
    def __init__(self, doc_text: str, chunks):
        self.text = doc_text
        self.chunks = chunks
        self.lines: list[str] = doc_text.splitlines()
        self.offsets: list[int] = []
        pos = 0
        for line in self.lines:
            self.offsets.append(pos)
            pos += len(line) + 1
        self.kv: list[tuple[int, str, str]] = []
        for i, line in enumerate(self.lines):
            kv = _parse_kv(line)
            if kv:
                self.kv.append((i, kv[0], kv[1]))
        self.tables = _parse_tables(self.lines)
        self.token_index: dict[str, set[int]] = {}
        for i, line in enumerate(self.lines):
            for tok in set(tokenize(line)):
                self.token_index.setdefault(tok, set()).add(i)

    def chunk_id_for_offset(self, offset: int):
        for c in self.chunks:
            if c.start <= offset < c.end:
                return c.id
        return self.chunks[0].id if self.chunks else None

    def candidate_lines(self, slot: Slot) -> list[int]:
        toks = set(tokenize(slot.desc or "")) | set(tokenize(slot.key))
        cand: set[int] = set()
        for tok in toks:
            cand |= self.token_index.get(tok, set())
        # 标题/描述里的连续中文串也当关键词（tokenize 会拆单字，上面已覆盖）
        return sorted(cand)


def _key_score(key: str, slot: Slot) -> int:
    k, desc = key.strip(), (slot.desc or "").strip()
    if not k or not desc:
        return 0
    if k == desc or k == slot.key:
        return 3
    if k in desc or desc in k:
        return 2
    if len(set(k) & set(desc)) >= 2:
        return 1
    return 0


def _continuation_value(ctx: CodeContext, line_idx: int, first: str) -> str:
    """断行合并：值被切到下一行时，把后续无标签行拼回来，直到空行/键值/表格/标题行。"""
    parts = [first]
    for j in range(line_idx + 1, min(line_idx + 4, len(ctx.lines))):
        nxt = ctx.lines[j].strip()
        if not nxt or nxt.startswith("|") or _parse_kv(ctx.lines[j]) or nxt.startswith("#"):
            break
        if re.match(r"^[-*•·\d]+[.\)、]\s+", nxt):
            break
        parts.append(nxt)
    # 拼接规则：编码/中文名断行用 "" 拼（FP202 + 60005、沈阳晨光 + 科技有限公司），
    # 英文句子断行才用空格拼，否则 “FP202 60005” 会和 gold 对不上
    out = parts[0]
    for part in parts[1:]:
        if out and part and out[-1].isalnum() and part[0].isalnum():
            out += part
        elif any("\u4e00" <= ch <= "\u9fff" for ch in out):
            out += part
        else:
            out += " " + part
    return out


def _extract_format(ctx: CodeContext, slot: Slot, cand: list[int]):
    fmt = slot.format
    if not fmt:
        return None, 0, None
    # 优先：键匹配的键值行里的格式值（收件人邮箱 vs 发件人邮箱、返程日期 vs 出发日期就靠这个区分）
    for idx, k, v in ctx.kv:
        if _key_score(k, slot) >= 2:
            for pat in {"email": [r"[\w.\-]+\s*@\s*[\w.\-]+\s*\.\s*[A-Za-z]{2,}"],
                        "uuid": [r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"],
                        "date": [r"\d{4}年\d{1,2}月\d{1,2}日", r"\d{4}[-/.]\d{1,2}[-/.]\d{1,2}"],
                        "datetime": [r"\d{4}年\d{1,2}月\d{1,2}日\s*\d{1,2}[:：]\d{1,2}(?::\d{1,2})?"],
                        "phone": [r"1[3-9]\d{9}", r"\d{3,4}-\d{7,8}"],
                        "url": [r"https?://[^\s\u4e00-\u9fff]+"]}.get(fmt, []):
                m = re.search(pat, v)
                if m:
                    raw = m.group(0).replace(" ", "") if fmt == "email" else m.group(0)
                    return raw, 0.95, idx
    patterns = {
        "email": [r"[\w.\-]+\s*@\s*[\w.\-]+\s*\.\s*[A-Za-z]{2,}"],
        "uuid": [r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"],
        "date": [r"\d{4}年\d{1,2}月\d{1,2}日", r"\d{4}[-/.]\d{1,2}[-/.]\d{1,2}"],
        "datetime": [r"\d{4}年\d{1,2}月\d{1,2}日\s*\d{1,2}[:：]\d{1,2}(?::\d{1,2})?", r"\d{4}[-/.]\d{1,2}[-/.]\d{1,2}[T ]\d{1,2}:\d{1,2}(:\d{1,2})?"],
        "phone": [r"1[3-9]\d{9}", r"\d{3,4}-\d{7,8}"],
        "url": [r"https?://[^\s\u4e00-\u9fff]+" ],
    }
    pats = patterns.get(fmt)
    if not pats:
        return None, 0, None
    best = None
    for idx in cand + list(range(len(ctx.lines))):
        line = ctx.lines[idx]
        for pat in pats:
            m = re.search(pat, line)
            if m:
                score = 2 if idx in cand else 0
                # 键值行里命中：加分
                for _, k, _ in ctx.kv:
                    if _key_score(k, slot) >= 2 and ctx.lines[idx] == line:
                        score += 1
                if best is None or score > best[1]:
                    best = (m.group(0), score, idx)
        if best and best[1] >= 3:
            break
    if not best:
        return None, 0, None
    raw, score, idx = best
    raw = raw.replace(" ", "") if fmt == "email" else raw
    return raw, 0.9 if score else 0.6, idx


def _extract_enum(ctx: CodeContext, slot: Slot, cand: list[int]):
    if not slot.enum:
        return None, 0, None
    best = None
    for e in sorted(slot.enum, key=len, reverse=True):
        norm_e = str(e).strip().lower().replace(" ", "")
        for idx in cand + list(range(len(ctx.lines))):
            line_norm = ctx.lines[idx].lower().replace(" ", "")
            if norm_e in line_norm:
                score = 2 if idx in cand else 0
                if best is None or score > best[1]:
                    best = (e, score, idx)
    if not best:
        return None, 0, None
    return best[0], 0.9 if best[1] else 0.6, best[2]


def _extract_bool(ctx: CodeContext, slot: Slot, cand: list[int]):
    for idx, k, v in ctx.kv:
        if _key_score(k, slot) >= 1:
            vv = v.strip()
            if vv.startswith(("否", "无", "不属于", "不是")) or vv.lower().startswith(("no", "false", "n")):
                return False, 0.95, idx
            if vv.startswith(("是", "有", "属于")) or vv.lower().startswith(("yes", "true", "y")):
                return True, 0.95, idx
            if "✓" in vv or "✔" in vv:
                return True, 0.9, idx
    # 散文肯定/否定句：核心词 + 属于/是长期 等，例如“属于长期合作”-> True
    clean_desc = re.sub(r"[（(].*?[）)]", "", slot.desc or "").strip()
    for _prefix in ("是否为", "是否", "是不是"):
        if clean_desc.startswith(_prefix):
            clean_desc = clean_desc[len(_prefix):]
            break
    if len(clean_desc) >= 2:
        for idx in cand:
            line = ctx.lines[idx]
            if clean_desc in line:
                if any(n in line for n in ("不属于", "非" + clean_desc, "不是" + clean_desc)):
                    return False, 0.8, idx
                if any(pos in line for pos in ("属于", "是" + clean_desc, "为" + clean_desc)):
                    return True, 0.8, idx
    for idx in cand:
        line = ctx.lines[idx]
        if re.search(r"(是否|是不是).{0,10}[：:]\s*(是|否)", line):
            return line.strip().endswith("是"), 0.8, idx
    return None, 0, None


def _extract_leaf(ctx: CodeContext, slot: Slot):
    cand = ctx.candidate_lines(slot)
    # 1. format 优先（邮箱/日期/uuid 全文唯一性强）
    if slot.format:
        raw, conf, idx = _extract_format(ctx, slot, cand)
        if raw is not None:
            return raw, conf, idx, "format"
    # 2. enum 优先于自由文本（避免把“开发中”当成“开发”之外的自由值）
    if slot.enum:
        raw, conf, idx = _extract_enum(ctx, slot, cand)
        if raw is not None:
            return raw, conf, idx, "enum"
    if slot.type == "boolean":
        raw, conf, idx = _extract_bool(ctx, slot, cand)
        if raw is not None:
            return raw, conf, idx, "boolean"
    # 3. 键值行（重复键取最高分）
    best = None
    for idx, k, v in ctx.kv:
        sc = _key_score(k, slot)
        # 重复键：同分时后胜——文档里重复出现通常是后面的更正/完整版，前胜会把断行残值当答案
        if sc > 0 and (best is None or sc >= best[0]):
            best = (sc, idx, v)
    if best:
        sc, idx, v = best
        v = _continuation_value(ctx, idx, v)
        if slot.type == "number":
            num = parse_number_value(v)
            if num is not None:
                return num, 0.95 if sc >= 2 else 0.8, idx, "kv-number"
        elif slot.type == "boolean":
            b, _, _ = _extract_bool(ctx, slot, [idx])
            if b is not None:
                return b, 0.9, idx, "kv-boolean"
            return v, 0.8, idx, "kv"
        else:
            return _clean_str(v), 0.95 if sc >= 2 else 0.8, idx, "kv"
    # 4. 关键词 + 为/是 的散文句
    keywords = []
    if slot.desc:
        # 先去掉括号里的说明（例如“合同总金额（数字，不含单位）”），否则简称会切成“单位）”
        clean_desc = re.sub(r"[（(].*?[）)]", "", slot.desc).strip()
        keywords.append(clean_desc)
        # 描述的后半截常是口头简称，例如“合同总金额”->“总金额”
        if len(clean_desc) >= 4:
            keywords.append(clean_desc[-3:])
            keywords.append(clean_desc[-2:])
    for idx in cand:
        line = ctx.lines[idx]
        for kw in keywords:
            m = re.search(re.escape(kw) + r"\s*[为是：:]\s*([^。，；;]+)", line)
            if m:
                val = m.group(1).strip()
                if slot.type == "number":
                    num = parse_number_value(val)
                    if num is not None:
                        return num, 0.7, idx, "keyword-number"
                elif slot.type == "string":
                    return _clean_str(val), 0.7, idx, "keyword-string"
    # 5. 数字兜底：候选行里的第一个数字（仅 number 槽，且行含金额类词时更可信）
    if slot.type == "number":
        for idx in cand:
            num = parse_number_value(ctx.lines[idx])
            # 跳过纯编号行（订单号、日期里的数字会被 format 档先处理）
            if num is not None and len(ctx.lines[idx]) < 60:
                return num, 0.6, idx, "number-fallback"
    return None, 0, None, "not-found"


def _extract_array(ctx: CodeContext, slot: Slot):
    # 表格列优先
    if slot.items and slot.items.type == "object":
        return _extract_array_objects(ctx, slot)
    keywords = [slot.desc, slot.key]
    for tbl in ctx.tables:
        header = tbl["header"]
        for ci, h in enumerate(header):
            if any(kw and (kw in h or h in kw) for kw in keywords if kw):
                vals = [r[ci].strip() for r in tbl["rows"] if r[ci].strip()]
                if vals:
                    return vals, 0.9, None, "table-column"
    # 列表行：项目符号 / 编号
    cand = ctx.candidate_lines(slot)
    items = []
    for idx in cand:
        line = ctx.lines[idx].strip()
        m = re.match(r"^[-*•·]\s*(.+)$", line) or re.match(r"^\d+[.\)、]\s*(.+)$", line)
        if m:
            items.append(_clean_str(m.group(1)))
    if items:
        return items, 0.8, cand[0] if cand else None, "list"
    # 标题行后跟破表/裸行：例如“交付物”下一行是 | 交付物 |、再下一行是裸的“需求文档”
    for idx, line in enumerate(ctx.lines):
        s = line.strip().strip("# ")
        # 空行 s="" 时 "" in desc 恒为 True，必须先排除空行，否则会把下一段正文误当列表项
        if s and (s == slot.desc or s == slot.key or (len(s) <= 10 and slot.desc and s in slot.desc)):
            items2 = []
            for j in range(idx + 1, min(idx + 20, len(ctx.lines))):
                nxt = ctx.lines[j].strip()
                if not nxt or nxt.startswith("#") or _parse_kv(ctx.lines[j]):
                    break
                item = nxt.strip("|").split("|")[0].strip().strip("-*•· ")
                if item and item != slot.desc:
                    items2.append(_clean_str(item))
            if items2:
                return items2, 0.75, idx, "section-list"
    # 键值行里的顿号/逗号分隔：取最高分键，不取第一个沾边的键（发票金额行不能抢发票明细行）
    best_kv = None
    for idx, k, v in ctx.kv:
        sc = _key_score(k, slot)
        if sc > 0 and (best_kv is None or sc >= best_kv[0]):
            best_kv = (sc, idx, v)
    if best_kv:
        sc, idx, v = best_kv
        parts = [_clean_str(p) for p in re.split(r"[、，,；;]", v) if p.strip()]
        if len(parts) >= 2:
            return parts, 0.95 if sc >= 2 else 0.8, idx, "kv-split"
    return None, 0, None, "not-found"


def _extract_array_objects(ctx: CodeContext, slot: Slot):
    props = slot.items.properties if slot.items else {}
    for tbl in ctx.tables:
        header = tbl["header"]
        col_map: dict[int, str] = {}
        for ci, h in enumerate(header):
            for pk, ps in props.items():
                if h == ps.desc or h == pk or (ps.desc and (h in ps.desc or ps.desc in h)):
                    col_map[ci] = pk
        if not col_map:
            continue
        rows = []
        for r in tbl["rows"]:
            obj = {}
            for ci, pk in col_map.items():
                ps = props[pk]
                raw = r[ci].strip()
                if ps.type == "number":
                    obj[pk] = parse_number_value(raw)
                else:
                    obj[pk] = _clean_str(raw) if raw else None
            if any(v is not None for v in obj.values()):
                rows.append(obj)
        if rows:
            return rows, 0.9, None, "table-rows"
    return None, 0, None, "not-found"


def extract_slot_code(ctx: CodeContext, slot: Slot):
    if slot.type == "object":
        obj, confs, ev = {}, [], None
        for pk, ps in slot.properties.items():
            v, conf, idx, method = extract_slot_code(ctx, ps)
            obj[pk] = v
            confs.append(conf)
            ev = idx if ev is None else ev
        conf = min(confs) if confs else 0
        return obj, conf, ev, "object"
    if slot.type == "array":
        vals, conf, idx, method = _extract_array(ctx, slot)
        if vals is None:
            return None, 0, None, method
        # 数组元素再过校验（对象元素已在表里处理， primitive 在这里统一校验）
        if slot.items and slot.items.type != "object":
            out = []
            for item in vals:
                vv, _ = validate_value(slot.items, item, slot.key)
                out.append(vv)
            return out, conf, idx, method
        return vals, conf, idx, method
    if slot.type == "semantic":
        return None, 0, None, "semantic-needs-llm"
    raw, conf, idx, method = _extract_leaf(ctx, slot)
    return raw, conf, idx, method


def extract_code(slots: dict[str, Slot], doc_text: str, chunks) -> tuple[dict, dict, dict]:
    """返回 (结果, trace, 置信度 dict)。结果里的值已经过 validate.py 校验。"""
    ctx = CodeContext(doc_text, chunks)
    result: dict = {}
    trace: dict = {"extractor": "code", "slots": {}}
    confidences: dict = {}
    for key, slot in slots.items():
        raw, conf, idx, method = extract_slot_code(ctx, slot)
        value, warns = validate_value(slot, raw, key)
        if raw is not None and value is None:
            conf = 0
        result[key] = value
        confidences[key] = conf
        trace["slots"][key] = {
            "method": method, "confidence": conf,
            "evidence_chunk": ctx.chunk_id_for_offset(ctx.offsets[idx]) if idx is not None else None,
            "warnings": warns,
        }
    filled = sum(1 for v in result.values() if v is not None)
    required = [k for k, s in slots.items() if s.required and not s.nullable]
    filled_req = sum(1 for k in required if result.get(k) is not None)
    trace["coverage"] = {
        "filled": filled, "total": len(slots),
        "filled_required": filled_req, "total_required": len(required),
    }
    return result, trace, confidences
