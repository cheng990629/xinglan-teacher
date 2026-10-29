"""命令行：不经过 HTTP 也能跑批处理，适合和本地模型同机联调。

  python -m slotfill.cli --document-url <url> --slots-url <url> --extractor python --out result.json
  python -m slotfill.cli --document-file doc.md --slots-file slots.json --extractor auto --out result.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import AppConfig, LLMConfig
from .llm import build_client
from .pipeline import run_pipeline
from .service import fetch_url


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="LLM 槽位填充")
    p.add_argument("--document-url")
    p.add_argument("--slots-url")
    p.add_argument("--document-file")
    p.add_argument("--slots-file")
    p.add_argument("--extractor", default="auto", choices=["auto", "code", "llm", "hybrid", "agent", "python"])
    p.add_argument("--llm-output-format", default="yaml", choices=["yaml", "json"])
    p.add_argument("--llm-concurrency", type=int, default=4)
    p.add_argument("--out", default="result.json")
    p.add_argument("--trace-out", default="trace.json")
    args = p.parse_args(argv)

    app_cfg = AppConfig.from_env()
    if args.document_url:
        raw, path = fetch_url(args.document_url, app_cfg)
        slots_raw, _ = fetch_url(args.slots_url, app_cfg, max_bytes=1024 * 1024)
        slots_payload = json.loads(slots_raw.decode("utf-8"))
        result, trace = run_pipeline(document_bytes=raw, document_filename=path, slots_payload=slots_payload,
                                     extractor=args.extractor, llm=(None if args.extractor == 'code' else build_client(LLMConfig.from_env())), output_format=args.llm_output_format, concurrency=args.llm_concurrency)
    elif args.document_file:
        raw = Path(args.document_file).read_bytes()
        slots_payload = json.loads(Path(args.slots_file).read_text(encoding="utf-8"))
        result, trace = run_pipeline(document_bytes=raw, document_filename=args.document_file,
                                     slots_payload=slots_payload, extractor=args.extractor, llm=(None if args.extractor == 'code' else build_client(LLMConfig.from_env())), output_format=args.llm_output_format, concurrency=args.llm_concurrency)
    else:
        print("必须给 --document-url 或 --document-file", file=sys.stderr)
        return 2
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    Path(args.trace_out).write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"done: {args.out}  missing={trace.get('missing')}  warnings={len(trace.get('warnings', []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
