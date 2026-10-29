"""配置：只读 .env，不在代码里写死任何 key / 地址。

支持的变量（见 .env.example）：
  LLM_BASE_URL / LLM_API_KEY / LLM_MODEL   必填（mock 模式除外）
  LLM_TEMPERATURE（默认 0，提取必须确定性）、LLM_TIMEOUT、LLM_MAX_TOKENS
  LLM_JSON_MODE（1=请求 response_format=json_object；本地小模型不支持时设 0）
  LLM_OUTPUT_FORMAT（yaml|json，默认 yaml：模型输出 YAML，Python 转 JSON，见 yaml_output.py）
  LLM_CONCURRENCY（LLM 分组并发数，默认 4；本地单卡模型设 1-2，避免排队反而变慢）
  MOCK_LLM（1=不调模型，走 FakeLLM，仅用于测试/演示管线，不用于生产）
  ALLOW_PRIVATE_URLS / ALLOW_FILE_URLS（本地联调时才开，默认关，防 SSRF）
  SLOTFILL_DATA_DIR、SLOTFILL_CHUNK_CHARS、SLOTFILL_CHUNK_OVERLAP
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(path: str | Path | None = None) -> None:
    """极简 .env 解析：不覆盖已有的真实环境变量；不支持 export / 引号嵌套以外的花样。"""
    p = Path(path) if path else Path.cwd() / ".env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip()
        if k.startswith("export "):
            k = k[7:].strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        os.environ.setdefault(k, v)


@dataclass
class LLMConfig:
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    temperature: float = 0.0
    timeout: int = 120
    max_tokens: int = 4000
    json_mode: bool = False
    mock: bool = False
    output_format: str = "yaml"
    concurrency: int = 4

    @classmethod
    def from_env(cls) -> "LLMConfig":
        load_dotenv()
        return cls(
            base_url=os.environ.get("LLM_BASE_URL", "").rstrip("/"),
            api_key=os.environ.get("LLM_API_KEY", ""),
            model=os.environ.get("LLM_MODEL", ""),
            temperature=float(os.environ.get("LLM_TEMPERATURE", "0")),
            timeout=int(os.environ.get("LLM_TIMEOUT", "120")),
            max_tokens=int(os.environ.get("LLM_MAX_TOKENS", "4000")),
            json_mode=os.environ.get("LLM_JSON_MODE", "0") == "1",
            mock=os.environ.get("MOCK_LLM", "0") == "1",
            output_format=os.environ.get("LLM_OUTPUT_FORMAT", "yaml").lower() or "yaml",
            concurrency=int(os.environ.get("LLM_CONCURRENCY", "4")),
        )

        cfg = LLMConfig.from_env()
        if cfg.mock or cfg.is_usable():
            llm = build_client(cfg)
        if self.mock:
            return
        if not self.base_url or not self.model:
            raise ValueError("未配置模型：请在 .env 里填 LLM_BASE_URL 和 LLM_MODEL（本地 llama-server / vLLM 均可）")


@dataclass
class AppConfig:
    data_dir: Path = Path("data")
    chunk_chars: int = 8000
    chunk_overlap: int = 800
    allow_private_urls: bool = False
    allow_file_urls: bool = False
    max_document_bytes: int = 5 * 1024 * 1024  # 强约束：5M 上限；256K 是目标下限，不是拒收下限

    @classmethod
    def from_env(cls) -> "AppConfig":
        load_dotenv()
        return cls(
            data_dir=Path(os.environ.get("SLOTFILL_DATA_DIR", "data")),
            chunk_chars=int(os.environ.get("SLOTFILL_CHUNK_CHARS", "8000")),
            chunk_overlap=int(os.environ.get("SLOTFILL_CHUNK_OVERLAP", "800")),
            allow_private_urls=os.environ.get("ALLOW_PRIVATE_URLS", "0") == "1",
            allow_file_urls=os.environ.get("ALLOW_FILE_URLS", "0") == "1",
        )
