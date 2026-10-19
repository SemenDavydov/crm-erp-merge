"""Vercel Serverless Function: GET /result (и /api/result) → объединённые клиенты.

Каждый запрос заново забирает оба источника и пересчитывает результат — результат всегда
соответствует текущим данным, а повторные вызовы идемпотентны (ничего не накапливается).
"""
import json
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from merge import build_result  # noqa: E402


class handler(BaseHTTPRequestHandler):  # имя класса требует Vercel
    def do_GET(self):  # noqa: N802
        try:
            status, body = 200, build_result()
        except Exception as e:  # noqa: BLE001
            status, body = 502, {"error": f"{type(e).__name__}: {e}"}
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
