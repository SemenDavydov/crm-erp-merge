import json
from pathlib import Path

import pytest

from merge import fetch
from merge.core import find_service_contacts, from_crm, merge, merge_with_details, normalize_email, normalize_phone

FIX = Path(__file__).parent / "fixtures"
CRM = json.loads((FIX / "crm.json").read_text(encoding="utf-8"))
ERP = json.loads((FIX / "erp.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("8 999 123 45 67", "+79991234567"),
        ("+7 (999) 123-45-67", "+79991234567"),
        ("9005551212", "+79005551212"),
        ("8 (916) 445 56 67", "+79164455667"),
        ("+74951234567", "+74951234567"),
        ("123", None),
        ("не указан", None),
        ("abc", None),
        ("", None),
        (None, None),
        ("+1 650 253 00 00", None),
    ],
)
def test_normalize_phone(raw, expected):
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize("raw, expected", [("  BOB@site.ru ", "bob@site.ru"), ("", None), ("не почта", None)])
def test_normalize_email(raw, expected):
    assert normalize_email(raw) == expected


@pytest.fixture(scope="module")
def result():
    return merge(CRM, ERP)


def by_name(result, name):
    return next(c for c in result["clients"] if c["name"] == name)


def test_schema_is_strict(result):
    assert set(result) == {"clients", "stats"}
    assert all(set(c) == {"name", "phones", "emails", "amount", "sources"} for c in result["clients"])


def test_stats(result):
    assert result["stats"] == {
        "crm_fetched": 15, "erp_fetched": 11, "records_dropped": 3, "unique_clients": 16, "duplicates_merged": 7,
    }


def test_service_contacts():
    _, service = merge_with_details(CRM, ERP)
    assert service == {"+74951234567", "info@bestcompany.ru"}


def test_same_person_in_three_records_is_not_service():
    """ivan@x.ru встречается в 3 записях, но L1 и C1 связаны ещё и телефоном — это 2 «клиента», не 3."""
    records = [from_crm(i) for i in CRM if i["id"] in {"L1", "L11"}] + []
    from merge.core import from_erp
    records += [from_erp(i) for i in ERP if i["code"] == "C1"]
    assert find_service_contacts(records) == set()


def test_ivan_merged_across_sources_with_freshest_name(result):
    ivan = by_name(result, "Иван Петров (актуальн)")  # L11 — самый свежий updated_at
    assert ivan == {"name": "Иван Петров (актуальн)", "phones": ["+79991234567"], "emails": ["ivan@x.ru"],
                    "amount": 1650, "sources": ["crm", "erp"]}


def test_anna_transitive_chain(result):
    """L3 —телефон 1— C2 —телефон 2— L4: один человек по цепочке."""
    anna = by_name(result, "Анна (рабочий)")
    assert anna["phones"] == ["+79160000001", "+79165550000"]
    assert anna["emails"] == ["anna.work@corp.ru", "anna@mail.ru"] and anna["amount"] == 1900


def test_merged_by_email_case_and_phone_formats(result):
    assert by_name(result, "Сайтов Б.")["amount"] == 1000  # bob@site.ru == BOB@site.ru
    assert by_name(result, "Морозова Е.")["amount"] == 1500  # +7 926 … == 8 926 …
    assert by_name(result, "Пётр (CRM)")["emails"] == ["petr@erp.ru"]


def test_service_contacts_not_merged_and_not_shown(result):
    workers = [c for c in result["clients"] if c["name"].startswith("Сотрудник")]
    guests = [c for c in result["clients"] if c["name"].startswith("Гость")]
    assert len(workers) == 4 and all(c["phones"] == [] for c in workers)
    assert len(guests) == 3 and all(c["emails"] == [] for c in guests)
    dumped = json.dumps(result, ensure_ascii=False)
    assert "+74951234567" not in dumped and "info@bestcompany.ru" not in dumped


def test_dropped_records_not_in_result(result):
    names = {c["name"] for c in result["clients"]}
    assert not names & {"Без контактов", "Мусор", "Битый клиент"}


def test_idempotent(result):
    assert merge(CRM, ERP) == result
    assert merge(list(reversed(CRM)), list(reversed(ERP))) == result  # и от порядка не зависит


def test_fetch_stops_at_total_pages(monkeypatch):
    """Сервер на page > total_pages отдаёт последнюю страницу снова — листать до пустой нельзя."""
    calls = []

    def fake_get(url, token):
        page = int(url.rsplit("page=", 1)[1])
        calls.append(page)
        return {"page": min(page, 3), "total_pages": 3, "items": [{"p": min(page, 3)}]}

    monkeypatch.setattr(fetch, "_get", fake_get)
    assert fetch.fetch_all("crm", "t") == [{"p": 1}, {"p": 2}, {"p": 3}] and calls == [1, 2, 3]
