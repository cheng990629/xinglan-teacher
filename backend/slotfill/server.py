"""HTTP 服务：标准库 ThreadingHTTPServer，零框架依赖。

为什么不用 FastAPI：这套程序要和本地 8b/27b 模型同机部署，离线环境 pip 装
FastAPI/uvicorn 经常是第一个卡点；核心 service/pipeline 本来就和框架无关，
以后要换 FastAPI，只要把下面三个 handler 的函数体原样搬过去即可。
路由：
  GET  /health
  POST /api/v1/fill            -> 202 {job_id, status, result_url, trace_url, job_url}
       body.sync=true 时同步跑完再返回（小文档 / curl 演示用），仍带 result_url
  GET  /api/v1/jobs/<id>       -> status
  GET  /api/v1/results/<id>.json        -> 处理中 202 / 完成 200 纯填槽 JSON / 失败 500
  GET  /api/v1/results/<id>/trace.json  -> 证据块 / 警告 / missing 清单
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from .config import AppConfig
from .model_config import public_config, save_config, test_connection
from .teacher import generate_plans, load_plans, upload_word
from .service import JobStore, run_job_sync, submit_job


def make_handler(store: JobStore, app_cfg: AppConfig):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # 不刷屏
            pass

        def _send(self, code: int, obj) -> None:
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _urls(self, job_id: str) -> dict:
            return {
                "job_id": job_id,
                "job_url": f"/api/v1/jobs/{job_id}",
                "result_url": f"/api/v1/results/{job_id}.json",
                "trace_url": f"/api/v1/results/{job_id}/trace.json",
            }

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/health":
                return self._send(200, {"status": "ok"})
            if path == "/api/v1/teacher/plans":
                return self._send(200, load_plans())
            if path == "/api/v1/config":
                return self._send(200, public_config())
            if path.startswith("/api/v1/jobs/"):
                job_id = path.rsplit("/", 1)[-1]
                st = store.status(job_id)
                return self._send(200, st) if st else self._send(404, {"error": "job 不存在"})
            if path.startswith("/api/v1/results/") and path.endswith(".json") and "/trace" not in path:
                job_id = path[len("/api/v1/results/") : -len(".json")]
                st = store.status(job_id)
                if not st:
                    return self._send(404, {"error": "job 不存在"})
                if st["status"] == "processing":
                    return self._send(202, {"status": "processing", **self._urls(job_id)})
                if st["status"] == "failed":
                    return self._send(500, {"status": "failed", "error": st.get("error")})
                return self._send(200, store.result(job_id) or {})
            if path.startswith("/api/v1/results/") and path.endswith("/trace.json"):
                job_id = path[len("/api/v1/results/") : -len("/trace.json")]
                tr = store.trace(job_id)
                return self._send(200, tr) if tr is not None else self._send(404, {"error": "trace 不存在或任务未完成"})
            return self._send(404, {"error": "未知路由"})

        def _read_json(self):
            try:
                length = int(self.headers.get("Content-Length") or 0)
                return json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            except Exception as e:
                raise ValueError(f"请求体不是合法 JSON：{e}")

        def do_POST(self):
            path = urlparse(self.path).path
            if path == "/api/v1/teacher/plans":
                return self._send(200, load_plans())
            if path == "/api/v1/config":
                try:
                    payload = self._read_json()
                except ValueError as e:
                    return self._send(400, {"error": str(e)})
                try:
                    return self._send(200, save_config(payload.get("api_key"), payload.get("base_url"), payload.get("model")))
                except ValueError as e:
                    return self._send(400, {"error": str(e)})
            if path == "/api/v1/teacher/plan":
                try:
                    payload = self._read_json()
                except ValueError as e:
                    return self._send(400, {"error": str(e)})
                try:
                    return self._send(200, generate_plans(payload.get("extraction")))
                except Exception as e:
                    return self._send(500, {"error": str(e)})
            if path == "/api/v1/teacher/upload":
                try:
                    payload = self._read_json()
                except ValueError as e:
                    return self._send(400, {"error": str(e)})
                try:
                    return self._send(200, upload_word(payload.get("filename", ""), payload.get("docx_base64", ""), payload.get("extractor", "auto")))
                except Exception as e:
                    return self._send(500, {"error": str(e)})
            if path == "/api/v1/config/test":
                try:
                    payload = self._read_json()
                except ValueError as e:
                    return self._send(400, {"error": str(e)})
                result = test_connection(payload.get("api_key"), payload.get("base_url"), payload.get("model"))
                return self._send(200 if result.get("ok") else 502, result)
            if path != "/api/v1/fill":
                return self._send(404, {"error": "未知路由"})
            try:
                payload = self._read_json()
            except ValueError as e:
                return self._send(400, {"error": str(e)})
            if not isinstance(payload, dict) or ("document_url" not in payload and "document_text" not in payload):
                return self._send(400, {"error": "入参必须含 document_url（+ slots_url）或 document_text（+ slots）"})
            if payload.get("sync"):
                try:
                    result, trace = run_job_sync(payload, store, app_cfg)
                    job_id = store.create()
                    store.finish(job_id, result, trace)
                    return self._send(200, {"status": "done", "data": result, **self._urls(job_id)})
                except Exception as e:
                    return self._send(500, {"error": str(e)})
            job_id = submit_job(payload, store, app_cfg)
            return self._send(202, {"status": "processing", **self._urls(job_id)})

    return Handler


def serve(host: str = "0.0.0.0", port: int = 8000, data_dir: str = "data") -> None:
    from pathlib import Path

    app_cfg = AppConfig.from_env()
    # .env 显式改了数据目录就用 .env 的，否则用命令行参数
    store = JobStore(app_cfg.data_dir if str(app_cfg.data_dir) != "data" else Path(data_dir))
    httpd = ThreadingHTTPServer((host, port), make_handler(store, app_cfg))
    print(f"slotfill listening on http://{host}:{port}  (data_dir={store.dir})")
    print("POST /api/v1/fill  {document_url, slots_url, extractor}  -> 202 + result_url（非 SSE）")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
