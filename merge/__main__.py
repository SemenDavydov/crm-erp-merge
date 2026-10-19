"""Локальный запуск: OOOBS_TOKEN=... python -m merge  → JSON в stdout и result.json."""
import json
import sys
from pathlib import Path

from merge.core import merge_with_details
from merge.fetch import fetch_all, get_token

token = get_token()
result, service = merge_with_details(fetch_all("crm", token), fetch_all("erp", token))
text = json.dumps(result, ensure_ascii=False, indent=2)
Path("result.json").write_text(text, encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8")
print(text)
print(f"\nслужебные контакты (не объединяем, не выводим): {', '.join(sorted(service))}", file=sys.stderr)
