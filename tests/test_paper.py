import sqlite3
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from investing_desk.live import DisabledLiveOrderAdapter, LiveOrdersDisabledError
from investing_desk.paper import Decision, PaperLedger, PROPOSAL_TTL, estimate_buy
from investing_desk.research import build_memo
from investing_desk.scenario import load_scenario, parse_instant, stamp

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "scenario.json"
NOW = datetime(2026, 9, 25, 19, 0, tzinfo=timezone.utc)


class PaperLedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "paper.sqlite3"
        self.ledger = PaperLedger(self.db)
        self.scenario = load_scenario(FIXTURE)
        self.memo = build_memo(self.scenario, "SIM-ORC")
        self.proposal = self.ledger.create_proposal(self.memo, 3, NOW)

    def count(self, table):
        with sqlite3.connect(self.db) as conn:
            return conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]

    def test_pending_rejected_and_deferred_proposals_never_book_entries(self):
        self.assertEqual(self.count("paper_entries"), 0)
        self.ledger.decide(
            self.proposal.id, self.proposal.proposal_hash, Decision.REJECT, "Reviewer", NOW
        )
        deferred = self.ledger.create_proposal(self.memo, 4, NOW + timedelta(seconds=1))
        self.ledger.decide(
            deferred.id, deferred.proposal_hash, Decision.DEFER, "Reviewer",
            NOW + timedelta(seconds=2),
        )
        self.assertEqual(self.count("paper_entries"), 0)
        self.assertEqual(self.count("decisions"), 2)
        with self.assertRaisesRegex(ValueError, "already decided"):
            self.ledger.decide(
                self.proposal.id, self.proposal.proposal_hash, Decision.APPROVE,
                "Reviewer", NOW + timedelta(minutes=1),
            )

    def test_sqlite_refuses_an_entry_without_approval(self):
        with sqlite3.connect(self.db) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            with self.assertRaisesRegex(sqlite3.IntegrityError, "hash or expiry mismatch"):
                conn.execute(
                    "INSERT INTO decisions VALUES (?, ?, ?, ?, ?)",
                    (self.proposal.id, "approve", "Forged", stamp(NOW), "0" * 64),
                )
            with self.assertRaisesRegex(sqlite3.IntegrityError, "approved"):
                conn.execute(
                    "INSERT INTO paper_entries VALUES (?, ?, ?, ?, ?)",
                    (self.proposal.id, stamp(NOW), "48.05", "1.00", "145.15"),
                )
        self.assertEqual(self.count("paper_entries"), 0)

    def test_hash_and_expiry_gate_approval(self):
        with self.assertRaisesRegex(ValueError, "hash does not match"):
            self.ledger.decide(self.proposal.id, "0" * 64, Decision.APPROVE, "Reviewer", NOW)
        with self.assertRaisesRegex(ValueError, "expired or not yet created"):
            self.ledger.decide(
                self.proposal.id, self.proposal.proposal_hash, Decision.APPROVE,
                "Reviewer", NOW + PROPOSAL_TTL,
            )
        with self.assertRaisesRegex(ValueError, "expired or not yet created"):
            self.ledger.decide(
                self.proposal.id, self.proposal.proposal_hash, Decision.APPROVE,
                "Reviewer", NOW - timedelta(seconds=1),
            )
        self.assertEqual(self.count("decisions"), 0)
        self.assertEqual(self.count("paper_entries"), 0)
        with self.assertRaisesRegex(ValueError, "printable characters"):
            self.ledger.decide(
                self.proposal.id, self.proposal.proposal_hash, Decision.APPROVE,
                "Fake\nActor", NOW,
            )
        self.ledger.decide(
            self.proposal.id, self.proposal.proposal_hash, Decision.APPROVE,
            "Reviewer", NOW + PROPOSAL_TTL - timedelta(microseconds=1),
        )
        self.assertEqual(self.count("paper_entries"), 1)
        self.assertEqual(self.ledger.get_decision(self.proposal.id).actor, "Reviewer")

    def test_cost_model_and_per_company_exposure(self):
        estimate = estimate_buy(Decimal("48.00"), 3)
        self.assertEqual(estimate.assumed_fill_price, Decimal("48.05"))
        self.assertEqual(estimate.total_cost, Decimal("145.15"))
        with self.assertRaisesRegex(ValueError, "positive whole number"):
            estimate_buy(Decimal("48.00"), True)
        with self.assertRaisesRegex(ValueError, "exceeds"):
            self.ledger.create_proposal(self.memo, 11, NOW + timedelta(seconds=1))
        self.ledger.decide(
            self.proposal.id, self.proposal.proposal_hash, Decision.APPROVE,
            "Reviewer", NOW + timedelta(minutes=1),
        )
        second = self.ledger.create_proposal(self.memo, 8, NOW + timedelta(minutes=2))
        with self.assertRaisesRegex(ValueError, "company exposure"):
            self.ledger.decide(
                second.id, second.proposal_hash, Decision.APPROVE,
                "Reviewer", NOW + timedelta(minutes=3),
            )
        self.assertIsNone(self.ledger.get_decision(second.id))
        self.assertEqual(self.count("paper_entries"), 1)

    def test_total_portfolio_exposure_is_rechecked_at_approval(self):
        for index in range(4):
            memo = replace(
                self.memo, company_id=f"SIM-TEST-{index}",
                company_name=f"Fictional test company {index}",
            )
            proposal = self.ledger.create_proposal(
                memo, 10, NOW + timedelta(minutes=index + 1)
            )
            self.ledger.decide(
                proposal.id, proposal.proposal_hash, Decision.APPROVE,
                "Reviewer", NOW + timedelta(minutes=index + 2),
            )
        fifth = self.ledger.create_proposal(
            replace(self.memo, company_id="SIM-TEST-4", company_name="Fictional test company 4"),
            10, NOW + timedelta(minutes=8),
        )
        with self.assertRaisesRegex(ValueError, "portfolio exposure"):
            self.ledger.decide(
                fifth.id, fifth.proposal_hash, Decision.APPROVE,
                "Reviewer", NOW + timedelta(minutes=9),
            )
        self.assertIsNone(self.ledger.get_decision(fifth.id))
        self.assertEqual(self.count("paper_entries"), 4)

    def test_monitor_and_retrospective_only_use_later_available_snapshots(self):
        with self.assertRaisesRegex(ValueError, "approved PAPER entry"):
            self.ledger.record_observation(
                self.proposal.id, self.scenario, parse_instant("2026-04-15T20:05:00Z")
            )
        self.ledger.decide(
            self.proposal.id, self.proposal.proposal_hash, Decision.APPROVE,
            "Reviewer", NOW + timedelta(minutes=1),
        )
        with self.assertRaisesRegex(ValueError, "No synthetic observation"):
            self.ledger.render_retrospective(self.proposal.id)
        with self.assertRaisesRegex(ValueError, "No synthetic price available"):
            self.ledger.record_observation(
                self.proposal.id, self.scenario, parse_instant("2026-04-15T20:00:00Z")
            )
        quote = self.ledger.record_observation(
            self.proposal.id, self.scenario, parse_instant("2026-04-15T20:05:00Z")
        )
        self.assertEqual(quote.id, "ORC-P1")
        report = self.ledger.render_retrospective(self.proposal.id)
        self.assertIn("ORC-P1", report)
        self.assertIn("ORC-K1", report)
        self.assertIn("ORC-S1", report)
        self.assertIn("$-14.27 (-9.83%", report)
        self.assertIn("not a live fill", report)
        with self.assertRaises(sqlite3.IntegrityError):
            self.ledger.record_observation(
                self.proposal.id, self.scenario, parse_instant("2026-04-15T20:05:00Z")
            )
        later = self.ledger.record_observation(
            self.proposal.id, self.scenario, parse_instant("2026-05-15T20:05:00Z")
        )
        self.assertEqual(later.id, "ORC-P2")
        self.assertIn("ORC-P2", self.ledger.render_retrospective(self.proposal.id))
        self.assertEqual(self.count("observations"), 2)

    def test_changed_memo_or_database_record_cannot_be_approved_silently(self):
        changed = replace(
            self.scenario.company("SIM-ORC").evidence[0], summary="Different invented context."
        )
        company = self.scenario.company("SIM-ORC")
        altered = replace(
            self.scenario,
            companies=(replace(company, evidence=(changed,) + company.evidence[1:]),),
        )
        with self.assertRaisesRegex(ValueError, "no longer matches"):
            self.ledger.record_observation(
                self.proposal.id, altered, parse_instant("2026-04-15T20:05:00Z")
            )
        with sqlite3.connect(self.db) as conn:
            with self.assertRaisesRegex(sqlite3.IntegrityError, "immutable"):
                conn.execute(
                    "UPDATE proposals SET shares = 100 WHERE id = ?", (self.proposal.id,)
                )
        self.assertEqual(self.count("paper_entries"), 0)

    def test_live_adapter_always_fails_closed(self):
        adapter = DisabledLiveOrderAdapter()
        for method in (adapter.submit_order, adapter.cancel_order, adapter.replace_order):
            with self.subTest(method=method.__name__):
                with self.assertRaises(LiveOrdersDisabledError):
                    method(self.proposal.id, enabled=True, credentials="ignored")


if __name__ == "__main__":
    unittest.main()
