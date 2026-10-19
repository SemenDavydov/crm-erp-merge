from merge.core import merge
from merge.fetch import fetch_all, get_token


def build_result() -> dict:
    token = get_token()
    return merge(fetch_all("crm", token), fetch_all("erp", token))
