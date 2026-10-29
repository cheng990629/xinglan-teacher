"""基于 LLM 的槽位填充后端。

设计要点（详见 README.md）：
- 不以向量 RAG 为答案来源：结构化分块 + 确定性 BM25 选块 + 每槽证据 + Python 校验门。
- 两种提取器共用同一套槽位编译、选块、校验代码：
  ``python`` = 确定性编排（大文档默认），``agent`` = ReAct harness（小文档 / 语义槽 / 疑难槽）。
- 模型只走 OpenAI 兼容 /chat/completions，.env 配置 base_url / api_key / model。
"""
__version__ = "1.0.0"
