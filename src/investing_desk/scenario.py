"""Load explicitly synthetic, local-only evidence and price snapshots."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal, Mapping

Role = Literal["context", "catalyst", "skeptic"]
ROLES: tuple[Role, ...] = ("context", "catalyst", "skeptic")
MAX_NOTES_PER_ROLE = 2
CENT = Decimal("0.01")


def parse_instant(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("Timestamp must be an ISO 8601 string with a timezone")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Invalid timestamp: {value}") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError(f"Timestamp must include a timezone: {value}")
    return result.astimezone(timezone.utc)


def stamp(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timestamp must include a timezone")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def display_stamp(value: datetime) -> str:
    return stamp(value).replace(".000000Z", "Z")


def money(value: object) -> Decimal:
    if not isinstance(value, str):
        raise ValueError("Price must be a decimal string")
    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid price: {value}") from exc
    if not amount.is_finite() or amount <= 0:
        raise ValueError(f"Price must be positive, finite and in cents: {value}")
    try:
        if amount != amount.quantize(CENT):
            raise ValueError(f"Price must be positive, finite and in cents: {value}")
    except InvalidOperation as exc:
        raise ValueError(f"Price must be positive, finite and in cents: {value}") from exc
    return amount


def _object(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _items(value: object, label: str) -> list[object]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label} must be a nonempty list")
    return value


def _text(item: Mapping[str, object], key: str, limit: int = 240) -> str:
    value = item.get(key)
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
        or len(value) > limit
        or "\n" in value
        or "\r" in value
        or not value.isprintable()
    ):
        raise ValueError(f"{key} must be a nonempty single line of at most {limit} characters")
    return value


def _id(item: Mapping[str, object]) -> str:
    value = _text(item, "id", 40)
    if re.fullmatch(r"[A-Z0-9-]+", value) is None:
        raise ValueError(f"Invalid fixture ID: {value}")
    return value


def _source(item: Mapping[str, object]) -> str:
    value = _text(item, "source", 160)
    if not value.startswith("fixture://") or any(char.isspace() for char in value):
        raise ValueError("Sources must be local synthetic fixture:// identifiers")
    return value


def _role(value: object) -> Role:
    if value == "context":
        return "context"
    if value == "catalyst":
        return "catalyst"
    if value == "skeptic":
        return "skeptic"
    raise ValueError(f"Invalid evidence role: {value}")


@dataclass(frozen=True, slots=True)
class Evidence:
    id: str
    role: Role
    title: str
    summary: str
    published_at: datetime
    available_at: datetime
    source: str


@dataclass(frozen=True, slots=True)
class Price:
    id: str
    observed_at: datetime
    available_at: datetime
    price: Decimal
    source: str


@dataclass(frozen=True, slots=True)
class Company:
    id: str
    name: str
    evidence: tuple[Evidence, ...]
    prices: tuple[Price, ...]


@dataclass(frozen=True, slots=True)
class Scenario:
    as_of: datetime
    companies: tuple[Company, ...]

    def company(self, company_id: str) -> Company:
        for company in self.companies:
            if company.id == company_id:
                return company
        raise ValueError(f"Unknown fictional company: {company_id}")


def load_scenario(path: Path) -> Scenario:
    data = _object(json.loads(Path(path).read_text(encoding="utf-8")), "scenario")
    if data.get("dataset_type") != "synthetic":
        raise ValueError("Only explicitly synthetic scenarios are supported")
    as_of = parse_instant(data.get("as_of"))
    companies: list[Company] = []
    company_ids: set[str] = set()
    for raw_company in _items(data.get("companies"), "companies"):
        item = _object(raw_company, "company")
        company_id = _id(item)
        if company_id in company_ids or item.get("fictional") is not True:
            raise ValueError(f"Company {company_id} must be unique and explicitly fictional")
        company_ids.add(company_id)
        evidence: list[Evidence] = []
        note_ids: set[str] = set()
        for raw_note in _items(item.get("evidence"), "evidence"):
            note = _object(raw_note, "evidence")
            note_id = _id(note)
            if note_id in note_ids:
                raise ValueError(f"Duplicate evidence ID: {note_id}")
            role = _role(note.get("role"))
            note_ids.add(note_id)
            published = parse_instant(note.get("published_at"))
            available = parse_instant(note.get("available_at"))
            if available < published:
                raise ValueError(f"Evidence {note_id} predates its publication")
            evidence.append(
                Evidence(
                    note_id, role, _text(note, "title", 100),
                    _text(note, "summary"), published, available, _source(note),
                )
            )
        if any(sum(note.role == role for note in evidence) > MAX_NOTES_PER_ROLE for role in ROLES):
            raise ValueError(f"Company {company_id} exceeds the per-worker evidence limit")

        prices: list[Price] = []
        price_ids: set[str] = set()
        for raw_price in _items(item.get("prices"), "prices"):
            quote = _object(raw_price, "price")
            quote_id = _id(quote)
            if quote_id in price_ids or quote_id in note_ids:
                raise ValueError(f"Duplicate source ID: {quote_id}")
            price_ids.add(quote_id)
            observed = parse_instant(quote.get("observed_at"))
            available = parse_instant(quote.get("available_at"))
            if available < observed:
                raise ValueError(f"Price {quote_id} predates its observation")
            prices.append(
                Price(quote_id, observed, available, money(quote.get("price")), _source(quote))
            )
        companies.append(
            Company(company_id, _text(item, "name", 100), tuple(evidence), tuple(prices))
        )
    return Scenario(as_of, tuple(companies))


def latest_price(
    prices: tuple[Price, ...], cutoff: datetime, *, after: datetime | None = None
) -> Price:
    stamp(cutoff)
    if after is not None:
        stamp(after)
    eligible = [
        price for price in prices
        if price.observed_at <= cutoff
        and price.available_at <= cutoff
        and (after is None or price.observed_at > after)
    ]
    if not eligible:
        raise ValueError(f"No synthetic price available at {stamp(cutoff)}")
    return max(eligible, key=lambda price: (price.observed_at, price.available_at, price.id))
