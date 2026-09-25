"""Local PAPER proposals, human decisions and invented-price observations."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from enum import StrEnum
from hashlib import sha256
from pathlib import Path

from .research import Memo, build_memo
from .scenario import (
    CENT, Price, Scenario, display_stamp, latest_price, money, parse_instant, stamp,
)

STARTING_CASH = Decimal("10000.00")
MAX_COMPANY_COST = Decimal("500.00")
MAX_TOTAL_COST = Decimal("2000.00")
SLIPPAGE = Decimal("0.001")
FEE = Decimal("1.00")
PROPOSAL_TTL = timedelta(hours=24)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS proposals (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    company_name TEXT NOT NULL,
    as_of TEXT NOT NULL,
    quote_price TEXT NOT NULL,
    shares INTEGER NOT NULL CHECK (shares > 0),
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    memo_markdown TEXT NOT NULL,
    memo_hash TEXT NOT NULL,
    proposal_hash TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS decisions (
    proposal_id TEXT PRIMARY KEY REFERENCES proposals(id),
    action TEXT NOT NULL CHECK (action IN ('approve', 'reject', 'defer')),
    actor TEXT NOT NULL CHECK (length(trim(actor)) > 0),
    decided_at TEXT NOT NULL,
    proposal_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS paper_entries (
    proposal_id TEXT PRIMARY KEY REFERENCES decisions(proposal_id),
    opened_at TEXT NOT NULL,
    assumed_fill_price TEXT NOT NULL,
    fee TEXT NOT NULL,
    total_cost TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS observations (
    proposal_id TEXT NOT NULL REFERENCES paper_entries(proposal_id),
    source_id TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    available_at TEXT NOT NULL,
    price TEXT NOT NULL,
    source TEXT NOT NULL,
    PRIMARY KEY (proposal_id, observed_at)
);
CREATE TRIGGER IF NOT EXISTS decision_integrity_gate
BEFORE INSERT ON decisions
BEGIN
    SELECT RAISE(ABORT, 'decision hash or expiry mismatch')
    WHERE NOT EXISTS (
        SELECT 1 FROM proposals p
        WHERE p.id = NEW.proposal_id AND p.proposal_hash = NEW.proposal_hash
          AND NEW.decided_at >= p.created_at AND NEW.decided_at < p.expires_at
    );
END;
CREATE TRIGGER IF NOT EXISTS paper_entry_approval_gate
BEFORE INSERT ON paper_entries
BEGIN
    SELECT RAISE(ABORT, 'approved, unexpired PAPER decision required')
    WHERE NOT EXISTS (
        SELECT 1 FROM proposals p
        JOIN decisions d ON d.proposal_id = p.id
        WHERE p.id = NEW.proposal_id AND d.action = 'approve'
          AND d.proposal_hash = p.proposal_hash
          AND d.decided_at >= p.created_at AND d.decided_at < p.expires_at
          AND NEW.opened_at = d.decided_at
    );
END;
CREATE TRIGGER IF NOT EXISTS proposals_no_update BEFORE UPDATE ON proposals
BEGIN SELECT RAISE(ABORT, 'proposals are immutable'); END;
CREATE TRIGGER IF NOT EXISTS proposals_no_delete BEFORE DELETE ON proposals
BEGIN SELECT RAISE(ABORT, 'proposals are immutable'); END;
CREATE TRIGGER IF NOT EXISTS decisions_no_update BEFORE UPDATE ON decisions
BEGIN SELECT RAISE(ABORT, 'decisions are immutable'); END;
CREATE TRIGGER IF NOT EXISTS decisions_no_delete BEFORE DELETE ON decisions
BEGIN SELECT RAISE(ABORT, 'decisions are immutable'); END;
CREATE TRIGGER IF NOT EXISTS paper_entries_no_update BEFORE UPDATE ON paper_entries
BEGIN SELECT RAISE(ABORT, 'paper entries are immutable'); END;
CREATE TRIGGER IF NOT EXISTS paper_entries_no_delete BEFORE DELETE ON paper_entries
BEGIN SELECT RAISE(ABORT, 'paper entries are immutable'); END;
"""


class Decision(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    DEFER = "defer"


@dataclass(frozen=True, slots=True)
class BuyEstimate:
    assumed_fill_price: Decimal
    fee: Decimal
    total_cost: Decimal


def estimate_buy(quote: Decimal, shares: int) -> BuyEstimate:
    if isinstance(shares, bool) or not isinstance(shares, int) or shares <= 0:
        raise ValueError("PAPER shares must be a positive whole number")
    if not quote.is_finite() or quote <= 0 or quote != quote.quantize(CENT):
        raise ValueError("PAPER quote must be a positive price in cents")
    fill = (quote * (1 + SLIPPAGE)).quantize(CENT, rounding=ROUND_HALF_UP)
    return BuyEstimate(fill, FEE, fill * shares + FEE)


def _proposal_digest(proposal: Proposal) -> str:
    payload = {
        "kind": "PAPER-v1",
        "company_id": proposal.company_id,
        "company_name": proposal.company_name,
        "as_of": stamp(proposal.as_of),
        "quote_price": f"{proposal.quote_price:.2f}",
        "shares": proposal.shares,
        "created_at": stamp(proposal.created_at),
        "expires_at": stamp(proposal.expires_at),
        "memo_hash": proposal.memo_hash,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class Proposal:
    id: str
    company_id: str
    company_name: str
    as_of: datetime
    quote_price: Decimal
    shares: int
    created_at: datetime
    expires_at: datetime
    memo_markdown: str
    memo_hash: str
    proposal_hash: str

    @property
    def estimate(self) -> BuyEstimate:
        return estimate_buy(self.quote_price, self.shares)


@dataclass(frozen=True, slots=True)
class DecisionRecord:
    action: Decision
    actor: str
    decided_at: datetime


def _from_row(row: sqlite3.Row) -> Proposal:
    proposal = Proposal(
        row["id"], row["company_id"], row["company_name"], parse_instant(row["as_of"]),
        money(row["quote_price"]), row["shares"], parse_instant(row["created_at"]),
        parse_instant(row["expires_at"]), row["memo_markdown"], row["memo_hash"],
        row["proposal_hash"],
    )
    if (
        sha256(proposal.memo_markdown.encode("utf-8")).hexdigest() != proposal.memo_hash
        or _proposal_digest(proposal) != proposal.proposal_hash
        or proposal.id != f"P-{proposal.proposal_hash[:16].upper()}"
        or proposal.expires_at - proposal.created_at != PROPOSAL_TTL
    ):
        raise ValueError(f"Stored PAPER proposal {proposal.id} failed integrity checks")
    return proposal


class PaperLedger:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def create_proposal(self, memo: Memo, shares: int, now: datetime) -> Proposal:
        created_at = parse_instant(stamp(now))
        if created_at < memo.as_of:
            raise ValueError("Cannot propose from evidence that is future-dated at creation")
        estimate = estimate_buy(memo.quote.price, shares)
        if estimate.total_cost > MAX_COMPANY_COST:
            raise ValueError(f"Estimated PAPER cost exceeds ${MAX_COMPANY_COST:.2f} per company")
        memo_markdown = memo.render()
        draft = Proposal(
            "", memo.company_id, memo.company_name, memo.as_of, memo.quote.price, shares,
            created_at, created_at + PROPOSAL_TTL, memo_markdown, memo.digest, "",
        )
        digest = _proposal_digest(draft)
        proposal = Proposal(
            f"P-{digest[:16].upper()}", draft.company_id, draft.company_name, draft.as_of,
            draft.quote_price, shares, draft.created_at, draft.expires_at, memo_markdown,
            draft.memo_hash, digest,
        )
        with closing(self._connect()) as conn, conn:
            conn.execute(
                """
                INSERT INTO proposals VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    proposal.id, proposal.company_id, proposal.company_name, stamp(proposal.as_of),
                    f"{proposal.quote_price:.2f}", proposal.shares, stamp(proposal.created_at),
                    stamp(proposal.expires_at), proposal.memo_markdown, proposal.memo_hash,
                    proposal.proposal_hash,
                ),
            )
        return proposal

    def get_proposal(self, proposal_id: str) -> Proposal:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,)).fetchone()
        if row is None:
            raise ValueError(f"Unknown PAPER proposal: {proposal_id}")
        return _from_row(row)

    def get_decision(self, proposal_id: str) -> DecisionRecord | None:
        proposal = self.get_proposal(proposal_id)
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT action, actor, decided_at, proposal_hash FROM decisions WHERE proposal_id = ?",
                (proposal_id,),
            ).fetchone()
        if row is None:
            return None
        decided_at = parse_instant(row["decided_at"])
        if (
            row["proposal_hash"] != proposal.proposal_hash
            or not proposal.created_at <= decided_at < proposal.expires_at
        ):
            raise ValueError(f"Stored PAPER decision {proposal_id} failed integrity checks")
        return DecisionRecord(Decision(row["action"]), row["actor"], decided_at)

    def _check_risk(
        self, conn: sqlite3.Connection, proposal: Proposal, estimate: BuyEstimate
    ) -> None:
        rows = conn.execute(
            """
            SELECT p.company_id, e.total_cost FROM paper_entries e
            JOIN proposals p ON p.id = e.proposal_id
            """
        ).fetchall()
        company_cost = sum(
            (Decimal(row["total_cost"]) for row in rows if row["company_id"] == proposal.company_id),
            Decimal("0"),
        )
        total_cost = sum((Decimal(row["total_cost"]) for row in rows), Decimal("0"))
        if company_cost + estimate.total_cost > MAX_COMPANY_COST:
            raise ValueError(f"PAPER company exposure exceeds ${MAX_COMPANY_COST:.2f}")
        if total_cost + estimate.total_cost > MAX_TOTAL_COST:
            raise ValueError(f"PAPER portfolio exposure exceeds ${MAX_TOTAL_COST:.2f}")
        if total_cost + estimate.total_cost > STARTING_CASH:
            raise ValueError("PAPER cash would be negative; borrowing is disabled")

    def decide(
        self, proposal_id: str, expected_hash: str, action: Decision, actor: str, now: datetime
    ) -> DecisionRecord:
        if not isinstance(action, Decision):
            raise ValueError("Decision must be approve, reject or defer")
        if (
            not isinstance(actor, str)
            or not actor
            or actor != actor.strip()
            or len(actor) > 80
            or not actor.isprintable()
        ):
            raise ValueError("Human actor label must be 1-80 printable characters without outer spaces")
        when = parse_instant(stamp(now))
        with closing(self._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,)).fetchone()
            if row is None:
                raise ValueError(f"Unknown PAPER proposal: {proposal_id}")
            proposal = _from_row(row)
            if expected_hash != proposal.proposal_hash:
                raise ValueError("Approval hash does not match the reviewed PAPER proposal")
            if when < proposal.created_at or when >= proposal.expires_at:
                raise ValueError(f"PAPER proposal expired or not yet created: {proposal.id}")
            if conn.execute(
                "SELECT 1 FROM decisions WHERE proposal_id = ?", (proposal_id,)
            ).fetchone():
                raise ValueError(f"PAPER proposal already decided: {proposal.id}")
            estimate = proposal.estimate
            if action is Decision.APPROVE:
                self._check_risk(conn, proposal, estimate)
            conn.execute(
                "INSERT INTO decisions VALUES (?, ?, ?, ?, ?)",
                (proposal.id, action.value, actor, stamp(when), proposal.proposal_hash),
            )
            if action is Decision.APPROVE:
                conn.execute(
                    "INSERT INTO paper_entries VALUES (?, ?, ?, ?, ?)",
                    (
                        proposal.id, stamp(when), f"{estimate.assumed_fill_price:.2f}",
                        f"{estimate.fee:.2f}", f"{estimate.total_cost:.2f}",
                    ),
                )
        return DecisionRecord(action, actor, when)

    def record_observation(
        self, proposal_id: str, scenario: Scenario, through: datetime
    ) -> Price:
        proposal = self.get_proposal(proposal_id)
        if build_memo(scenario, proposal.company_id).digest != proposal.memo_hash:
            raise ValueError("Scenario no longer matches the approved memo")
        quote = latest_price(
            scenario.company(proposal.company_id).prices, through, after=proposal.as_of
        )
        with closing(self._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            if conn.execute(
                "SELECT 1 FROM paper_entries WHERE proposal_id = ?", (proposal_id,)
            ).fetchone() is None:
                raise ValueError("Monitoring requires an approved PAPER entry")
            conn.execute(
                "INSERT INTO observations VALUES (?, ?, ?, ?, ?, ?)",
                (
                    proposal.id, quote.id, stamp(quote.observed_at), stamp(quote.available_at),
                    f"{quote.price:.2f}", quote.source,
                ),
            )
        return quote

    def render_retrospective(self, proposal_id: str) -> str:
        proposal = self.get_proposal(proposal_id)
        decision = self.get_decision(proposal_id)
        with closing(self._connect()) as conn:
            entry = conn.execute(
                "SELECT * FROM paper_entries WHERE proposal_id = ?", (proposal_id,)
            ).fetchone()
            observation = conn.execute(
                """
                SELECT * FROM observations WHERE proposal_id = ?
                ORDER BY observed_at DESC LIMIT 1
                """,
                (proposal_id,),
            ).fetchone()
        if entry is None or decision is None or decision.action is not Decision.APPROVE:
            raise ValueError("Only approved PAPER entries have position retrospectives")
        if observation is None:
            raise ValueError("No synthetic observation recorded; run monitor first")

        def section(start: str, end: str) -> str:
            if start not in proposal.memo_markdown or end not in proposal.memo_markdown:
                raise ValueError("Stored memo has no required thesis sections")
            return proposal.memo_markdown.split(start, 1)[1].split(end, 1)[0].strip()

        catalyst = section("## Catalysts to watch\n", "\n## Countercase")
        countercase = section("## Countercase\n", "\n## Paper-only question")
        mark = money(observation["price"])
        assumed_exit = (mark * (1 - SLIPPAGE)).quantize(CENT, rounding=ROUND_HALF_UP)
        sale_proceeds = assumed_exit * proposal.shares - FEE
        paid = Decimal(entry["total_cost"])
        net_difference = sale_proceeds - paid
        pct = (net_difference / paid * 100).quantize(CENT, rounding=ROUND_HALF_UP)
        return (
            f"# PAPER retrospective: {proposal.company_name}\n\n"
            f"Proposal {proposal.id} | memo SHA-256 {proposal.memo_hash} | "
            f"approved by {decision.actor} at {display_stamp(decision.decided_at)}\n\n"
            f"**As-of at decision:** {display_stamp(proposal.as_of)}. "
            f"Invented quote ${proposal.quote_price:.2f}; {proposal.shares} whole shares; "
            f"hypothetical buy fill ${money(entry['assumed_fill_price']):.2f} plus "
            f"${money(entry['fee']):.2f} fee = ${paid:.2f} paid.\n\n"
            f"**Latest recorded synthetic snapshot:** ${mark:.2f} [{observation['source_id']}], "
            f"observed {observation['observed_at']}, available {observation['available_at']}; "
            f"{observation['source']}.\n\n"
            f"**If sold at that invented quote:** ${assumed_exit:.2f} per share after 0.10% "
            f"assumed exit slippage, minus ${FEE:.2f} fee; estimated net difference "
            f"${net_difference:+.2f} ({pct:+.2f}% of paid cost).\n\n"
            f"**Original catalyst to check:**\n{catalyst}\n\n"
            f"**Original countercase to check:**\n{countercase}\n\n"
            "What actually changed in the thesis? The price movement alone cannot establish "
            "whether either claim occurred. This is a fictional what-if, not a live fill, "
            "real return or recommendation.\n"
        )
