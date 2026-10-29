"""文档解析：txt / md / docx / pdf / html -> 带章节结构的纯文本。

两条硬原则：
1. 不要把文档打平成无结构字符串再切块。标题、表格是槽位证据的天然边界。
2. 错版格式也要认：格式错了不等于内容没了，解析层先把格式修到可读。
3. 标题错乱也要认：大小标题层级本身不可信，不按 H1>H2>H3 建树，
   所有标题只当扁平分界线，标题文字归一化后比对；段落误标标题时降级。
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field

MAX_BYTES = 5 * 1024 * 1024


@dataclass
class Section:
    title: str
    start: int
    end: int


@dataclass
class ImageInfo:
    name: str
    alt: str
    start: int


@dataclass
class Document:
    text: str
    source_type: str
    sections: list[Section]
    images: list[ImageInfo] = field(default_factory=list)

    @property
    def chars(self) -> int:
        return len(self.text)


_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_CN_CHAPTER = re.compile(r"^(第[一二三四五六七八九十百千0-9]+[章节条].{0,40})$")
_NUM_HEADING = re.compile(r"^(\d{1,2}[.、]\s*.{1,40})$")
_CN_NUM_HEADING = re.compile(r"^([一二三四五六七八九十]+[、.]\s*.{1,40})$")
_BRACKET_HEADING = re.compile(r"^\u3010(.{1,40})\u3011$")


def normalize_section_title(title: str) -> str:
    """标题归一化：层级错乱时，标题的文字才是身份，# 数量、编号、装饰都不是。
    '### 合同金额'、'#合同金额：'、'1. 合同金额'、'【合同金额】'归一后都是'合同金额'。
    """
    s = (title or "").strip()
    s = re.sub(r"^#{1,6}\s*", "", s)
    s = re.sub(r"^\d{1,2}[.、]\s*", "", s)
    s = re.sub(r"^[一二三四五六七八九十]+[、.]\s*", "", s)
    if s.startswith("\u3010") and s.endswith("\u3011"):
        s = s[1:-1]
    s = s.strip("*_=- \t").strip()
    s = re.sub(r"[：:]\s*$", "", s)
    s = re.sub(r"\s+", " ", s)
    return s


def _looks_like_kv_line(stripped: str) -> bool:
    """段落误作标题的防线：带冒号且冒号后有值的行是键值行，不是标题。
    例如'甲方：沈阳晨光科技有限公司'很短很像标题，但冒号后有值，一旦当标题切分值就没了。
    """
    for sep in ("：", ":"):
        if sep in stripped:
            head, tail = stripped.split(sep, 1)
            if head.strip() and tail.strip():
                return True
    return False


def normalize_text(text: str) -> str:
    if text.startswith("\ufeff"):
        text = text[1:]
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u3000", " ").replace("\xa0", " ").replace("\t", "  ")
    return text


def _sections_from_text(text: str) -> list[Section]:
    """扁平切分：不按 H1>H2>H3 建树，层级跳号、重复标题都不影响切分，内容按顺序保留。"""
    marks: list[tuple[int, str]] = []
    pos = 0
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        m = _HEADING.match(stripped)
        if m:
            marks.append((pos, normalize_section_title(m.group(2))))
        elif _looks_like_kv_line(stripped):
            pass
        elif _CN_CHAPTER.match(stripped) and len(stripped) <= 50:
            marks.append((pos, normalize_section_title(stripped)))
        elif _NUM_HEADING.match(stripped) and len(stripped) <= 50 and not stripped.endswith(("。", "，", "：", ":")):
            marks.append((pos, normalize_section_title(stripped)))
        elif _CN_NUM_HEADING.match(stripped) and len(stripped) <= 50:
            marks.append((pos, normalize_section_title(stripped)))
        elif _BRACKET_HEADING.match(stripped):
            marks.append((pos, normalize_section_title(stripped)))
        pos += len(line)
    if not marks:
        return [Section(title="(全文)", start=0, end=len(text))]
    sections = []
    for i, (start, title) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        sections.append(Section(title=title, start=start, end=end))
    return sections


def _images_from_text(text: str) -> list[ImageInfo]:
    out: list[ImageInfo] = []
    for m in re.finditer(r"!\[([^\]]*)\]\(([^)]+)\)", text):
        out.append(ImageInfo(name=m.group(2).strip(), alt=m.group(1).strip(), start=m.start()))
    for m in re.finditer(r"!\[([^\]\n]{0,80})\](?!\()", text):
        out.append(ImageInfo(name="", alt=m.group(1).strip(), start=m.start()))
    for m in re.finditer(r"\[图片[：:]\s*([^\]\n]{0,80})\]", text):
        out.append(ImageInfo(name=m.group(1).strip(), alt=m.group(1).strip(), start=m.start()))
    out.sort(key=lambda x: x.start)
    return out


def decode_bytes(raw: bytes) -> str:
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def parse_text(text: str, source_type: str = "txt") -> Document:
    text = normalize_text(text)
    return Document(text=text, source_type=source_type,
                    sections=_sections_from_text(text), images=_images_from_text(text))


def parse_bytes(raw: bytes, filename: str = "") -> Document:
    if len(raw) > MAX_BYTES:
        raise ValueError(f"文档超过 5M 上限：{len(raw)} bytes，强约束内不接受更大文件")
    name = (filename or "").lower()
    if name.endswith(".docx"):
        return parse_docx(raw)
    if name.endswith(".pdf"):
        return parse_pdf(raw)
    if name.endswith((".md", ".markdown")):
        return parse_text(decode_bytes(raw), "md")
    if name.endswith((".html", ".htm")):
        return parse_text(_strip_html(decode_bytes(raw)), "html")
    return parse_text(decode_bytes(raw), "txt")


def _strip_html(html: str) -> str:
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", "\n", html, flags=re.S | re.I)
    html = re.sub(r"<[^>]+>", "\n", html)
    import html as _html
    return _html.unescape(html)


def parse_docx(raw: bytes) -> Document:
    try:
        from docx import Document as _Docx
    except ImportError as e:
        raise ValueError("解析 .docx 需要 python-docx：pip install python-docx") from e
    import io
    doc = _Docx(io.BytesIO(raw))
    lines: list[str] = []
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    for child in doc.element.body.iterchildren():
        if child.tag.endswith("}p"):
            p = Paragraph(child, doc)
            style = p.style.name if p.style is not None else ""
            txt = p.text.strip()
            alts: list[str] = []
            last_alt: str | None = None
            for el in p._p.iter():
                if el.tag.endswith("}docPr"):
                    last_alt = el.get("descr") or el.get("title") or el.get("name")
                elif el.tag.endswith("}blip"):
                    alts.append(last_alt or "图片")
            for alt in alts:
                lines.append(f"[图片：{alt}]")
            if not txt and not alts:
                continue
            if txt:
                # 标题误作段落的反向问题：Heading 被误标在长段落/键值行上时降级为正文
                if style.startswith("Heading") and (len(txt) > 80 or _looks_like_kv_line(txt) or txt.endswith("。")):
                    style = "Normal"
                if style.startswith("Heading"):
                    try:
                        level = int(style.replace("Heading", "").strip() or "1")
                    except ValueError:
                        level = 1
                    lines.append("#" * max(1, min(6, level)) + " " + txt)
                else:
                    lines.append(txt)
        elif child.tag.endswith("}tbl"):
            tbl = Table(child, doc)
            rows: list[list[str]] = []
            for row in tbl.rows:
                rows.append([c.text.strip().replace("\n", " ") for c in row.cells])
            if rows:
                width = max(len(r) for r in rows)
                for r in rows:
                    r += [""] * (width - len(r))
                    lines.append("| " + " | ".join(r) + " |")
    return parse_text("\n".join(lines), "docx")


def parse_pdf(raw: bytes) -> Document:
    try:
        from pypdf import PdfReader
    except ImportError as e:
        raise ValueError("解析 .pdf 需要 pypdf：pip install pypdf") from e
    import io
    reader = PdfReader(io.BytesIO(raw))
    pages = []
    for i, page in enumerate(reader.pages):
        t = page.extract_text() or ""
        pages.append(f"\n## 第 {i + 1} 页\n{t}")
    return parse_text("\n".join(pages), "pdf")
