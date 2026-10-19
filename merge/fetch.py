"""Постраничная загрузка источников. Только стандартная библиотека — без зависимостей на хостинге."""
import json
import os
import urllib.request

BASE_URL = os.environ.get("OOOBS_BASE_URL", "https://test.ooobs.ru/api/v2")
MAX_PAGES = 1000  # предохранитель от бесконечного цикла


def get_token() -> str:
    token = os.environ.get("OOOBS_TOKEN")
    if not token:
        raise RuntimeError("не задана переменная окружения OOOBS_TOKEN")
    return token


def _get(url: str, token: str) -> dict:
    req = urllib.request.Request(url, headers={"X-Auth-Token": token, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp)


def fetch_all(source: str, token: str) -> list[dict]:
    """Все страницы по total_pages. Сервер на page > total_pages отдаёт последнюю страницу ещё раз,
    поэтому «листать до пустой» нельзя — получились бы дубли."""
    first = _get(f"{BASE_URL}/{source}?page=1", token)
    items = list(first.get("items") or [])
    total_pages = min(int(first.get("total_pages") or 1), MAX_PAGES)
    for page in range(2, total_pages + 1):
        items += _get(f"{BASE_URL}/{source}?page={page}", token).get("items") or []
    return items
