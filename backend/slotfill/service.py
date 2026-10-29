"""任务服务：URL 入参 -> 后台跑 pipeline -> 结果 JSON 的 URL 出参（非 SSE）。

API 契约（强约束原样落地）：
  入参：{"document_url": "...", "slots_url": "...", "extractor": "auto|python|agent"}
        也接受 inline 形式 {"document_text": "...", "slots": {...}}，只用于本地测试，
        不改变 URL 契约。
  出参：{"job_id", "status", "result_url", "trace_url", "job_url"}
        result_url 指向的永远是一份纯填槽 JSON（不混 trace、不混 meta），
        处理中 GET 它返回 202，完成后返回 200，失败返回 job 里的 error。
  为什么不用 SSE：5M 文档一次跑几分钟，SSE 长连接在网关/浏览器里最先断；
  job + 轮询结果 URL 是后端批处理最稳的形态，前端要进度轮询 job_url 即可。

安全：默认拒绝 file:// 和内网/回环地址；本地联调把 ALLOW_PRIVATE_URLS=1 /
ALLOW_FILE_URLS=1 写进 .env 再开，不要直接改代码放宽。
"""
from __future__ import annotations

import ipaddress
import json
import socket
import threading
import urllib.parse
import urllib.request
from pathlib import Path
from uuid import uuid4

from .config import AppConfig, LLMConfig
from .llm import LLMClient, build_client
from .pipeline import run_pipeline


def _is_private_host(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return True  # 解析不出来也当成不可信，宁可拒收
    for _, _, _, _, sockaddr in infos:
        try:
            ip = ipaddress.ip_address(sockaddr[0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                return True
        except ValueError:
            continue
    return False


def fetch_url(url: str, cfg: AppConfig, max_bytes: int | None = None) -> tuple[bytes, str]:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme in ("http", "https"):
        if not cfg.allow_private_urls and parsed.hostname and _is_private_host(parsed.hostname):
            raise ValueError(f"拒绝内网/回环地址：{parsed.hostname}（本地联调请在 .env 设 ALLOW_PRIVATE_URLS=1）")
    elif parsed.scheme == "file":
        if not cfg.allow_file_urls:
            raise ValueError("拒绝 file:// 地址（本地联调请在 .env 设 ALLOW_FILE_URLS=1）")
        path = urllib.parse.unquote(parsed.path)
        return Path(path).read_bytes(), path
    else:
        raise ValueError(f"不支持的 URL scheme：{parsed.scheme!r}，只支持 http(s)://")
    req = urllib.request.Request(url, headers={"User-Agent": "slotfill/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read((max_bytes or cfg.max_document_bytes) + 1)
    if len(raw) > (max_bytes or cfg.max_document_bytes):
        raise ValueError("文档超过 5M 上限")
    return raw, parsed.path


class JobStore:
    """job 落盘：data/jobs/<job_id>/{status.json,result.json,trace.json}。

    内存 dict 只做进行中标记，真正的状态以 status.json 为准，服务重启后
    已完成的 job 仍能通过 result_url 取到。
    """

    def __init__(self, data_dir: Path):
        self.dir = Path(data_dir) / "jobs"
        self.dir.mkdir(parents=True, exist_ok=True)

    def _job_dir(self, job_id: str) -> Path:
        d = self.dir / job_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def create(self) -> str:
        job_id = uuid4().hex[:16]
        d = self._job_dir(job_id)
        (d / "status.json").write_text(json.dumps({"job_id": job_id, "status": "processing"}, ensure_ascii=False), encoding="utf-8")
        return job_id

    def finish(self, job_id: str, result: dict, trace: dict) -> None:
        d = self._job_dir(job_id)
        (d / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        (d / "trace.json").write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")
        (d / "status.json").write_text(
            json.dumps({"job_id": job_id, "status": "done", "missing": trace.get("missing", []), "warnings": trace.get("warnings", [])}, ensure_ascii=False),
            encoding="utf-8",
        )

    def fail(self, job_id: str, error: str) -> None:
        d = self._job_dir(job_id)
        (d / "status.json").write_text(json.dumps({"job_id": job_id, "status": "failed", "error": error}, ensure_ascii=False), encoding="utf-8")

    def status(self, job_id: str) -> dict | None:
        p = self.dir / job_id / "status.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def result(self, job_id: str) -> dict | None:
        p = self.dir / job_id / "result.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def trace(self, job_id: str) -> dict | None:
        p = self.dir / job_id / "trace.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def run_job_sync(
    payload: dict,
    store: JobStore,
    app_cfg: AppConfig,
    llm: LLMClient | None = None,
) -> tuple[dict, dict]:
    """同步跑一次 pipeline：URL 入参先取回，再按 inline/bytes 分流。"""
    extractor = payload.get("extractor", "auto")
    # code 模式零 LLM：不要因为没配 .env 就拒收；其它模式在 pipeline 里按需建客户端
    if llm is None and extractor in ("code",):
        llm_client = None
    else:
        llm_client = llm or build_client(LLMConfig.from_env())
    if "document_url" in payload:
        raw, path = fetch_url(payload["document_url"], app_cfg)
        slots_raw, _ = fetch_url(payload["slots_url"], app_cfg, max_bytes=1024 * 1024)
        slots_payload = json.loads(slots_raw.decode("utf-8"))
        result, trace = run_pipeline(
            document_bytes=raw, document_filename=path, slots_payload=slots_payload,
            extractor=extractor, llm=llm_client,
            chunk_chars=app_cfg.chunk_chars, chunk_overlap=app_cfg.chunk_overlap,
            output_format=payload.get("llm_output_format", "yaml"), concurrency=int(payload.get("llm_concurrency", 4)),
        )
    elif "document_text" in payload:
        result, trace = run_pipeline(
            document_text=payload["document_text"], slots_payload=payload.get("slots"),
            extractor=extractor, llm=llm_client,
            chunk_chars=app_cfg.chunk_chars, chunk_overlap=app_cfg.chunk_overlap,
            output_format=payload.get("llm_output_format", "yaml"), concurrency=int(payload.get("llm_concurrency", 4)),
        )
    else:
        raise ValueError("入参缺少 document_url 或 document_text，且 slots_url / slots 也要对应提供")
    return result, trace


def submit_job(payload: dict, store: JobStore, app_cfg: AppConfig, llm: LLMClient | None = None) -> str:
    job_id = store.create()

    def _run():
        try:
            result, trace = run_job_sync(payload, store, app_cfg, llm=llm)
            store.finish(job_id, result, trace)
        except Exception as e:  # 后台任务异常必须落盘，不能静默丢 job
            store.fail(job_id, str(e))

    threading.Thread(target=_run, daemon=True).start()
    return job_id
