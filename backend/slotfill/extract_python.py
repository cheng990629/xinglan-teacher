"""兼容层：上一版的 extract_python 就是现在的 LLM 提取器，名字保留，行为不变（YAML 输出）。
新代码请直接用 extract_llm.extract_llm。
"""
from .extract_llm import extract_llm as extract_python  # noqa: F401
from .extract_llm import extract_llm  # noqa: F401
