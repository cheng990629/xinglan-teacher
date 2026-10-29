"""启动：python run.py [--port 8000] [--host 127.0.0.1]，先在同目录放 .env。"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from slotfill.server import serve

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--data-dir", default="data")
    a = ap.parse_args()
    serve(host=a.host, port=a.port, data_dir=a.data_dir)
