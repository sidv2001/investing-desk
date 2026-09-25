import json
import tempfile
import unittest
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

from investing_desk.research import build_memo, context_worker
from investing_desk.scenario import latest_price, load_scenario, money, parse_instant

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "scenario.json"


class ResearchTests(unittest.TestCase):
    def setUp(self):
        self.scenario = load_scenario(FIXTURE)

    def test_memo_is_deterministic_cited_and_as_of(self):
        memo = build_memo(self.scenario, "SIM-ORC")
        text = memo.render()
        self.assertEqual(text, build_memo(self.scenario, "SIM-ORC").render())
        self.assertIn("2026-03-15T20:00:00", text)
        for source in ("ORC-C1", "ORC-K1", "ORC-S1", "ORC-P0"):
            self.assertIn(f"[{source}]", text)
            self.assertIn(f"fixture://starter/{source.lower()}", text)
        self.assertIn("## Countercase", text)
        self.assertIn("available 2026-03-13T14:00:00", text)
        self.assertNotIn("ORC-P1", text)
        self.assertNotIn("ORC-P2", text)
        self.assertEqual(len(memo.digest), 64)

    def test_future_dated_evidence_is_rejected_not_silently_skipped(self):
        company = self.scenario.company("SIM-ORC")
        note = company.evidence[0]
        for change in (
            {"available_at": self.scenario.as_of + timedelta(microseconds=1)},
            {
                "published_at": self.scenario.as_of + timedelta(seconds=1),
                "available_at": self.scenario.as_of + timedelta(seconds=1),
            },
        ):
            with self.subTest(change=change):
                modified = replace(note, **change)
                scenario = replace(
                    self.scenario,
                    companies=(
                        replace(company, evidence=(modified,) + company.evidence[1:]),
                        self.scenario.company("SIM-TID"),
                    ),
                )
                with self.assertRaisesRegex(ValueError, "future-dated"):
                    build_memo(scenario, "SIM-ORC")

    def test_prices_are_not_visible_before_available_time(self):
        prices = self.scenario.company("SIM-ORC").prices
        self.assertEqual(
            latest_price(prices, parse_instant("2026-04-15T20:00:00Z")).id, "ORC-P0"
        )
        self.assertEqual(
            latest_price(prices, parse_instant("2026-04-15T20:05:00Z")).id, "ORC-P1"
        )

    def test_workers_are_bounded_and_need_a_countercase(self):
        company = self.scenario.company("SIM-ORC")
        with self.assertRaisesRegex(ValueError, "1–2 sources"):
            context_worker((company.evidence[0],) * 3, self.scenario.as_of)
        without_skeptic = replace(
            self.scenario,
            companies=(replace(company, evidence=company.evidence[:2]),),
        )
        with self.assertRaisesRegex(ValueError, "skeptic worker"):
            build_memo(without_skeptic, "SIM-ORC")

    def test_naive_timestamp_and_external_input_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "timezone"):
            parse_instant("2026-03-15T20:00:00")
        with self.assertRaisesRegex(ValueError, "positive, finite"):
            money("1e999")
        data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "scenario.json"
            data["dataset_type"] = "external"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "explicitly synthetic"):
                load_scenario(path)
            data["dataset_type"] = "synthetic"
            data["companies"][0]["evidence"][0]["source"] = "https://example.org/data"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "fixture://"):
                load_scenario(path)


if __name__ == "__main__":
    unittest.main()
