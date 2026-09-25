"""Bounded, read-only workers that repeat fixture claims with source IDs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256

from .scenario import (
    MAX_NOTES_PER_ROLE, Company, Evidence, Price, Role, Scenario,
    display_stamp, latest_price, stamp,
)


def _worker(role: Role, notes: tuple[Evidence, ...], as_of: datetime) -> tuple[Evidence, ...]:
    if not notes or len(notes) > MAX_NOTES_PER_ROLE:
        raise ValueError(f"{role} worker needs 1–{MAX_NOTES_PER_ROLE} sources")
    for note in notes:
        if note.role != role or note.published_at > as_of or note.available_at > as_of:
            raise ValueError(f"{role} evidence {note.id} is wrong-role or future-dated at {stamp(as_of)}")
    return tuple(sorted(notes, key=lambda note: note.id))


def context_worker(notes: tuple[Evidence, ...], as_of: datetime) -> tuple[Evidence, ...]:
    return _worker("context", notes, as_of)


def catalyst_worker(notes: tuple[Evidence, ...], as_of: datetime) -> tuple[Evidence, ...]:
    return _worker("catalyst", notes, as_of)


def skeptic_worker(notes: tuple[Evidence, ...], as_of: datetime) -> tuple[Evidence, ...]:
    return _worker("skeptic", notes, as_of)


@dataclass(frozen=True, slots=True)
class Memo:
    company_id: str
    company_name: str
    as_of: datetime
    quote: Price
    context: tuple[Evidence, ...]
    catalysts: tuple[Evidence, ...]
    countercase: tuple[Evidence, ...]

    def render(self) -> str:
        def claims(notes: tuple[Evidence, ...]) -> str:
            return "\n".join(f"- {note.summary} [{note.id}]" for note in notes)

        sources = self.context + self.catalysts + self.countercase
        register = "\n".join(
            f"- [{note.id}] {note.title}; published {display_stamp(note.published_at)}, "
            f"available {display_stamp(note.available_at)}; {note.source}"
            for note in sources
        )
        return (
            f"# Research memo: {self.company_name} ({self.company_id})\n\n"
            f"**As of:** {display_stamp(self.as_of)}. **Fictional, synthetic evidence; "
            "not investment advice.**\n\n"
            "## Context\n"
            f"{claims(self.context)}\n\n"
            "## Catalysts to watch\n"
            f"{claims(self.catalysts)}\n\n"
            "## Countercase\n"
            f"{claims(self.countercase)}\n\n"
            "## Paper-only question\n"
            f"Fixture quote ${self.quote.price:.2f} [{self.quote.id}]. "
            "What observation would weaken the catalyst or support the countercase "
            "before a human tests the thesis in a bounded PAPER ledger?\n\n"
            "## Source register\n"
            f"{register}\n"
            f"- [{self.quote.id}] Synthetic price; observed {display_stamp(self.quote.observed_at)}, "
            f"available {display_stamp(self.quote.available_at)}; {self.quote.source}\n"
        )

    @property
    def digest(self) -> str:
        return sha256(self.render().encode("utf-8")).hexdigest()


def build_memo(scenario: Scenario, company_id: str) -> Memo:
    company: Company = scenario.company(company_id)
    as_of = scenario.as_of
    notes = company.evidence
    return Memo(
        company.id,
        company.name,
        as_of,
        latest_price(company.prices, as_of),
        context_worker(tuple(note for note in notes if note.role == "context"), as_of),
        catalyst_worker(tuple(note for note in notes if note.role == "catalyst"), as_of),
        skeptic_worker(tuple(note for note in notes if note.role == "skeptic"), as_of),
    )
