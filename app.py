"""WSGI-приложение для Vercel (точка входа app.py → переменная app).

GET /result (и /) → {"clients": [...], "stats": {...}}. Каждый запрос заново забирает оба источника
и пересчитывает результат: он всегда соответствует текущим данным, повторные вызовы идемпотентны.
"""
import json

from merge import build_result

RESULT_PATHS = {"/", "/result", "/result/", "/api/result"}


def app(environ, start_response):
    path = environ.get("PATH_INFO") or "/"
    if environ.get("REQUEST_METHOD", "GET") not in ("GET", "HEAD"):
        status, body = "405 Method Not Allowed", {"error": "only GET"}
    elif path not in RESULT_PATHS:
        status, body = "404 Not Found", {"error": "use GET /result"}
    else:
        try:
            status, body = "200 OK", build_result()
        except Exception as e:  # noqa: BLE001 — отдаём причину вместо пустого 500
            status, body = "502 Bad Gateway", {"error": f"{type(e).__name__}: {e}"}
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    start_response(status, [
        ("Content-Type", "application/json; charset=utf-8"),
        ("Content-Length", str(len(data))),
        ("Cache-Control", "no-store"),
        ("Access-Control-Allow-Origin", "*"),
    ])
    return [data]
