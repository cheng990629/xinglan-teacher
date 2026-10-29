"""确定性选块：BM25 风格的 TF-IDF，不用向量、不调 embedding 模型。

为什么不用向量 RAG 做主路径（回答“RAG 不精准”）：
1. 向量相似 ≠ 槽位证据：desc 里的词和原文表述经常不同义（“合同金额” vs “总价款”），
   向量会把语义相近但数值不同的段落都召回，数值槽位最怕这个。
2. top-k 截断丢长尾：一个必填槽的唯一证据可能在第 50 块，top-5 永远看不到它。
3. 跨块字段拼不起来：object/array 的多个子字段散在不同块，单次检索给不出完整对象。
4. 表格/条款结构被向量化抹掉，行列关系丢失。
所以这里的选块只负责“缩小 LLM 要看的范围”，最终值必须由 LLM 在原文块里
逐字对上、再过 Python 校验门；选块本身可解释、可复现、可调 top-k。
"""
from __future__ import annotations

import math
import re
from collections import Counter

from .chunking import Chunk
from .slots import Slot

_TOKEN = re.compile(r"[\u4e00-\u9fff]+|[A-Za-z0-9]+")


def tokenize(text: str) -> list[str]:
    toks: list[str] = []
    for t in _TOKEN.findall(text or ""):
        # 中文按字/词都保留：2 字以上中文串同时拆成单字，保证“总价款”能命中“价款”
        if re.fullmatch(r"[\u4e00-\u9fff]+", t):
            toks.append(t)
            if len(t) >= 2:
                toks.extend(list(t))
        else:
            toks.append(t.lower())
    return toks


class ChunkIndex:
    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        self._tf: list[Counter] = [Counter(tokenize(c.text)) for c in chunks]
        self._df: Counter = Counter()
        for tf in self._tf:
            for tok in tf:
                self._df[tok] += 1
        self.n = max(1, len(chunks))
        # section 标题 token 也计入：标题命中是强信号
        self._title_tf: list[Counter] = [Counter(tokenize(c.section)) for c in chunks]

    def _idf(self, tok: str) -> float:
        return math.log((self.n + 1) / (self._df.get(tok, 0) + 0.5)) + 1.0

    def score(self, slot: Slot, chunk_idx: int) -> float:
        kws = slot.keywords()
        tf, title_tf = self._tf[chunk_idx], self._title_tf[chunk_idx]
        score = 0.0
        for kw in kws:
            for tok in tokenize(kw):
                if tok in tf:
                    # BM25 简化：tf 饱和 + idf
                    score += self._idf(tok) * (tf[tok] / (tf[tok] + 1.0))
                if tok in title_tf:
                    score += self._idf(tok) * 1.5  # 标题命中加权
            # key 原串 / desc 短语在原文里原样出现：强加分（数值槽位就靠这个）
            if kw and kw.lower() in self.chunks[chunk_idx].text.lower():
                score += 2.0
        return score

    def top_chunks(self, slot: Slot, top_k: int = 4) -> list[Chunk]:
        scored = sorted(
            ((self.score(slot, i), i) for i in range(len(self.chunks))),
            key=lambda x: -x[0],
        )
        out = [self.chunks[i] for s, i in scored if s > 0][:top_k]
        return out

    def search(self, query: str, top_k: int = 4) -> list[Chunk]:
        """给 agent 工具用的自由查询：把 query 当成一个临时槽位。"""
        fake = Slot(key="__query__", desc=query)
        return self.top_chunks(fake, top_k=top_k)
