"""Объединение клиентов CRM + 1С по графу контактов без слипания через служебные контакты."""
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

SERVICE_THRESHOLD = 3  # контакт связывает 3+ разных клиентов → служебный (общий телефон компании, info@…)

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_phone(raw) -> str | None:
    """→ +7XXXXXXXXXX. 11 цифр с 7/8 в начале или 10 цифр; всё остальное — невалидно."""
    digits = re.sub(r"\D", "", str(raw or ""))
    if len(digits) == 11 and digits[0] in "78":
        digits = digits[1:]
    return f"+7{digits}" if len(digits) == 10 else None


def normalize_email(raw) -> str | None:
    email = str(raw or "").strip().lower()
    return email if _EMAIL.match(email) else None


@dataclass
class Record:
    source: str  # "crm" | "erp"
    rid: str
    name: str
    phones: set[str]
    emails: set[str]
    amount: float
    updated: datetime

    @property
    def contacts(self) -> set[str]:
        return self.phones | self.emails


def _ts(value: str) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def from_crm(item: dict) -> Record:
    phone, email = normalize_phone(item.get("phone")), normalize_email(item.get("email"))
    return Record("crm", str(item["id"]), str(item.get("name") or "").strip(),
                  {phone} - {None}, {email} - {None}, float(item.get("amount") or 0), _ts(item["updated_at"]))


def from_erp(item: dict) -> Record:
    contacts = item.get("contacts") or {}
    phones = {normalize_phone(p) for p in contacts.get("phones") or []} - {None}
    emails = {normalize_email(e) for e in contacts.get("emails") or []} - {None}
    return Record("erp", str(item["code"]), str(item.get("full_name") or "").strip(),
                  phones, emails, float(item.get("balance") or 0), _ts(item["changed"]))


class _DSU:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        self.parent[self.find(a)] = self.find(b)


def _components(records: list[Record], usable: set[str]) -> list[int]:
    """Номер компоненты для каждой записи, если связывать только по контактам из usable."""
    dsu = _DSU(len(records))
    first_seen: dict[str, int] = {}
    for i, r in enumerate(records):
        for c in r.contacts & usable:
            if c in first_seen:
                dsu.union(i, first_seen[c])
            else:
                first_seen[c] = i
    return [dsu.find(i) for i in range(len(records))]


def find_service_contacts(records: list[Record], threshold: int = SERVICE_THRESHOLD) -> set[str]:
    """Контакт служебный, если записи с ним — это threshold+ РАЗНЫХ клиентов.

    «Разные клиенты» считаются без самого контакта: ivan@x.ru в трёх записях, но две из них
    связаны ещё и общим телефоном — это 2 клиента, а не 3, и e-mail не служебный.
    Повторяем до неподвижной точки: найденный служебный контакт перестаёт склеивать других.
    """
    holders: dict[str, list[int]] = defaultdict(list)
    for i, r in enumerate(records):
        for c in r.contacts:
            holders[c].append(i)
    service: set[str] = set()
    while True:
        found = set(service)
        for contact, idx in holders.items():
            if contact in service or len(idx) < threshold:
                continue
            comp = _components(records, set(holders) - service - {contact})
            if len({comp[i] for i in idx}) >= threshold:
                found.add(contact)
        if found == service:
            return service
        service = found


@dataclass
class Merged:
    records: list[Record] = field(default_factory=list)

    def to_json(self, service: set[str]) -> dict:
        freshest = max(self.records, key=lambda r: (r.updated, r.source, r.rid))
        amount = sum(r.amount for r in self.records)
        return {
            "name": freshest.name,
            "phones": sorted({p for r in self.records for p in r.phones} - service),
            "emails": sorted({e for r in self.records for e in r.emails} - service),
            "amount": int(amount) if amount == int(amount) else round(amount, 2),
            "sources": sorted({r.source for r in self.records}),
        }


def merge(crm_items: list[dict], erp_items: list[dict]) -> dict:
    """Результат строго по схеме задания: {clients, stats}."""
    result, _ = merge_with_details(crm_items, erp_items)
    return result


def merge_with_details(crm_items: list[dict], erp_items: list[dict]) -> tuple[dict, set[str]]:
    """То же + множество служебных контактов (для лога и README, в ответ не попадает)."""
    parsed = [from_crm(i) for i in crm_items] + [from_erp(i) for i in erp_items]
    records = [r for r in parsed if r.contacts]  # без валидного телефона И email — отбрасываем
    service = find_service_contacts(records)
    comp = _components(records, {c for r in records for c in r.contacts} - service)

    groups: dict[int, Merged] = defaultdict(Merged)
    for i, r in enumerate(records):
        groups[comp[i]].records.append(r)
    clients = sorted((g.to_json(service) for g in groups.values()),
                     key=lambda c: (c["phones"][:1], c["emails"][:1], c["name"]))
    result = {
        "clients": clients,
        "stats": {
            "crm_fetched": len(crm_items),
            "erp_fetched": len(erp_items),
            "records_dropped": len(parsed) - len(records),
            "unique_clients": len(clients),
            "duplicates_merged": len(records) - len(clients),
        },
    }
    return result, service
