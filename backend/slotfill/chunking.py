"""结构化分块：先按 section 切，再按段落/句子切，绝不跨 section 硬切。
标题错乱补充：标题层级不可信，所以分块只认扁平 section，不建父子嵌套；
标题错乱常把文档切成一堆碎小节（标题行本身没正文），碎块会和下一块合并，
避免证据被切成标题孤儿、LLM 一块只能看到标题看不到正文。
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from .documents import Document


@dataclass
class Chunk:
    id: str
    section: str
    start: int
    end: int
    text: str


def _split_long(text: str, start_offset: int, chunk_chars: int, overlap: int) -> list[tuple[int, int, str]]:
    if len(text) <= chunk_chars:
        return [(start_offset, start_offset + len(text), text)]
    paras: list[tuple[int, str]] = []
    pos = 0
    for para in re.split(r"(\n\s*\n)", text):
        if para:
            paras.append((pos, para))
            pos += len(para)
    pieces: list[tuple[int, int, str]] = []
    buf, buf_start = "", None
    for p_off, para in paras:
        if buf_start is None:
            buf_start = p_off
        if len(buf) + len(para) > chunk_chars and buf.strip():
            pieces.append((start_offset + buf_start, start_offset + buf_start + len(buf), buf))
            buf = buf[-overlap:] if overlap else ""
            buf_start = p_off - len(buf) if buf else p_off
        buf += para
    if buf.strip():
        pieces.append((start_offset + buf_start, start_offset + buf_start + len(buf), buf))
    out: list[tuple[int, int, str]] = []
    for s, e, t in pieces:
        if len(t) <= chunk_chars:
            out.append((s, e, t))
        else:
            i = 0
            while i < len(t):
                out.append((s + i, min(e, s + i + chunk_chars), t[i:i + chunk_chars]))
                i += chunk_chars - overlap
    return out


def chunk_document(doc: Document, chunk_chars: int = 8000, overlap: int = 800) -> list[Chunk]:
    chunks: list[Chunk] = []
    for sec in doc.sections:
        sec_text = doc.text[sec.start:sec.end]
        for s, e, t in _split_long(sec_text, sec.start, chunk_chars, overlap):
            chunks.append(Chunk(id=f"c{len(chunks):04d}", section=sec.title, start=s, end=e, text=t))
    if not chunks:
        chunks.append(Chunk(id="c0000", section="(全文)", start=0, end=len(doc.text), text=doc.text))
    # 碎小节合并：标题错乱/空标题小节产生的 <800 字碎块，和下一块合并（不超过上限）
    merged: list[Chunk] = []
    for c in chunks:
        if merged and len(merged[-1].text) < 800 and len(merged[-1].text) + len(c.text) <= chunk_chars:
            prev = merged[-1]
            merged[-1] = Chunk(id=prev.id, section=f"{prev.section} / {c.section}",
                               start=prev.start, end=c.end, text=prev.text + c.text)
        else:
            merged.append(c)
    for i, c in enumerate(merged):
        c.id = f"c{i:04d}"
    return merged
