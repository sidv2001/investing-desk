import io
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from investing_desk.cli import main
from investing_desk.paper import PaperLedger
from investing_desk.research import build_memo
from investing_desk.scenario import load_scenario

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "scenario.json"
NOW = datetime(2026, 9, 25, 19, 0, tzinfo=timezone.utc)


class InteractiveInput(io.StringIO):
    def isatty(self):
        return True


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "paper.sqlite3"
        self.args = ["--fixture", str(FIXTURE), "--db", str(self.db)]

    def run_cli(self, *arguments):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(self.args + list(arguments))
        return code, out.getvalue(), err.getvalue()

    def test_noninteractive_or_mismatched_confirmation_never_decides(self):
        with patch("investing_desk.cli._now", return_value=NOW):
            code, receipt, _ = self.run_cli(
                "propose", "--company", "SIM-ORC", "--shares", "3"
            )
        self.assertEqual(code, 0)
        ledger = PaperLedger(self.db)
        proposal_id = receipt.split("## PAPER proposal ", 1)[1].splitlines()[0]
        self.assertIn("Status: pending human decision", receipt)
        proposal = ledger.get_proposal(proposal_id)
        params = (
            "decide", "--id", proposal.id, "--hash", proposal.proposal_hash,
            "--action", "approve", "--actor", "Human Tester",
        )
        with patch("sys.stdin", io.StringIO("")):
            code, _, error = self.run_cli(*params)
        self.assertEqual(code, 2)
        self.assertIn("interactive terminal", error)
        with patch("sys.stdin", InteractiveInput("YES\n")):
            code, _, error = self.run_cli(*params)
        self.assertEqual(code, 2)
        self.assertIn("Confirmation did not match", error)
        self.assertIsNone(ledger.get_decision(proposal.id))
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM paper_entries").fetchone()[0], 0)

        phrase = f"PAPER APPROVE {proposal.id} {proposal.proposal_hash[:12]}\n"
        with (
            patch("sys.stdin", InteractiveInput(phrase)),
            patch("investing_desk.cli._now", return_value=NOW + timedelta(minutes=1)),
        ):
            code, output, error = self.run_cli(*params)
        self.assertEqual((code, error), (0, ""))
        self.assertIn("PAPER approve recorded", output)
        self.assertEqual(ledger.get_decision(proposal.id).actor, "Human Tester")
        code, reviewed, error = self.run_cli("show", "--id", proposal.id)
        self.assertEqual((code, error), (0, ""))
        self.assertIn("Decision: approve", reviewed)
        self.assertNotIn("Status: pending", reviewed)

    def test_memo_command_does_not_create_database(self):
        code, text, error = self.run_cli("memo", "--company", "SIM-TID")
        self.assertEqual((code, error), (0, ""))
        self.assertIn("## Countercase", text)
        self.assertFalse(self.db.exists())
        self.assertEqual(
            text, build_memo(load_scenario(FIXTURE), "SIM-TID").render() + "\n"
        )

    def test_research_and_proposal_never_open_a_network_connection(self):
        with (
            patch("socket.socket.connect", side_effect=AssertionError("network attempted")),
            patch("investing_desk.cli._now", return_value=NOW),
        ):
            self.assertEqual(self.run_cli("memo", "--company", "SIM-ORC")[0], 0)
            self.assertEqual(
                self.run_cli("propose", "--company", "SIM-ORC", "--shares", "3")[0], 0
            )


if __name__ == "__main__":
    unittest.main()
