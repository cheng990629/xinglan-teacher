"""模型配置：阿里云百炼（DashScope）OpenAI 兼容接入 + 档位选择。

百炼只改三个参数就能接 OpenAI 兼容客户端（本程序的 OpenAICompatClient
就是这个协议）：base_url、api_key、model。本模块只做这三件事：
  1. 读当前配置（GET /api/v1/config）：key 只回掩码，永不回完整 key。
  2. 保存配置（POST /api/v1/config）：写回后端目录的 .env（权限 600），
     同时更新本进程的环境变量，之后提交的提取任务无需重启即可用新配置。
  3. 测试连接（POST /api/v1/config/test）：用当前（或请求里临时给的）
     配置调一次极小请求，只回“通/不通 + 耗时”，不保存、不跑提取。

档位说明（用户原话：35b / 27b / 9b）：
  档位只是建议值，真正生效的是“模型名”框里的值，框里可自由改。
  35B 级建议 qwen3-32b，27B 级建议 gemma-2-27b-it，9B 级建议 qwen3-8b；
  百炼的千问 Plus/Max（qwen-plus、qwen-max 等）不按参数量分档，也可直接填。
  百炼默认地址：https://dashscope.aliyuncs.com/compatible-mode/v1
  （业务空间绑定的地址形如 https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1，
  key 属于哪个空间就填哪个地址，两者不要混用）。
"""
from __future__ import annotations

import os
import time
from pathlib import Path

from .config import LLMConfig

BAILIAN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

# 档位 -> 建议模型名（可改，不是白名单）
TIER_SUGGESTIONS = {
    "35B": "qwen3-32b",
    "27B": "gemma-2-27b-it",
    "9B": "qwen3-8b",
}


def mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) < 8:
        return "****"
    return f"{key[:4]}****{key[-4:]}"


def public_config() -> dict:
    cfg = LLMConfig.from_env()
    return {
        "has_api_key": bool(cfg.api_key),
        "api_key_masked": mask_key(cfg.api_key),
        "base_url": cfg.base_url,
        "model": cfg.model,
        "is_bailian": ("dashscope" in cfg.base_url or "aliyun" in cfg.base_url or "maas.aliyuncs" in cfg.base_url),
        "mock": cfg.mock,
        "bailian_default_base_url": BAILIAN_BASE_URL,
        "tier_suggestions": TIER_SUGGESTIONS,
    }


def _normalize_base_url(raw: str) -> str:
    url = raw.strip().rstrip("/")
    if url.endswith("/chat/completions"):
        url = url[: -len("/chat/completions")]
    if not url.startswith("https://"):
        raise ValueError("base_url 必须以 https:// 开头，且不要带 /chat/completions（客户端会自动拼）")
    return url


def save_config(api_key: str | None, base_url: str | None, model: str | None) -> dict:
    """更新 .env + 进程环境变量；没给的字段保持原值；key 为空字符串表示不改。"""
    updates: dict[str, str] = {}
    if base_url is not None and base_url.strip():
        updates["LLM_BASE_URL"] = _normalize_base_url(base_url)
    if model is not None and model.strip():
        updates["LLM_MODEL"] = model.strip()
    if api_key is not None and api_key.strip():
        updates["LLM_API_KEY"] = api_key.strip()
    if not updates:
        raise ValueError("没有要保存的字段：请至少填一项（Key、地址或模型名）")
    env_path = Path.cwd() / ".env"
    lines: list[str] = []
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    seen = set()
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            k = stripped.split("=", 1)[0].strip()
            if k.startswith("export "):
                k = k[7:].strip()
            if k in updates:
                out.append(f"{k}={updates[k]}")
                seen.add(k)
                continue
        out.append(line)
    for k, v in updates.items():
        if k not in seen:
            out.append(f"{k}={v}")
    env_path.write_text("\n".join(out) + "\n", encoding="utf-8")
    try:
        os.chmod(env_path, 0o600)
    except OSError:
        pass
    for k, v in updates.items():
        os.environ[k] = v
    return public_config()


def test_connection(api_key: str | None, base_url: str | None, model: str | None) -> dict:
    """用当前已保存配置（或请求里临时给的配置，不保存）调一次小请求。"""
    from .llm import build_client

    cfg = LLMConfig.from_env()
    if base_url and base_url.strip():
        cfg.base_url = _normalize_base_url(base_url)
    if model and model.strip():
        cfg.model = model.strip()
    if api_key and api_key.strip():
        cfg.api_key = api_key.strip()
    if not cfg.api_key:
        return {"ok": False, "error": "未配置 API Key：请先在模型配置里填入百炼 Key 再测试"}
    if not cfg.base_url or not cfg.model:
        return {"ok": False, "error": "未配置完整：base_url 和模型名都要填"}
    cfg.timeout = 30
    cfg.max_tokens = 10
    started = time.time()
    try:
        client = build_client(cfg)
        reply = client.chat([{"role": "user", "content": "只回复OK，不要多余文字。"}])
        return {"ok": True, "model": cfg.model, "base_url": cfg.base_url,
                "latency_ms": int((time.time() - started) * 1000), "reply": reply[:100]}
    except Exception as e:
        return {"ok": False, "model": cfg.model, "base_url": cfg.base_url,
                "latency_ms": int((time.time() - started) * 1000), "error": str(e)[:500]}
