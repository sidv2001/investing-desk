# Investing Desk

![A decision loop: fictional evidence feeds three cited workers, a human gate controls PAPER entries, and later snapshots feed retrospectives; live orders stay disabled.](docs/decision-loop.svg)
[Read the decision loop as text](docs/decision-loop.md).

If your investing map starts with familiar big-tech names, ETFs, and index funds, an unfamiliar company is easier to examine when every claim has a date and a source. Investing Desk proposes a repeatable set of questions: What does the business do? What might change? What is the strongest reason the story could fail? The person reading the answers keeps the decision, including the choice to wait or walk away.

**What works now:** This Python 3.12 starter runs entirely offline. Two fictional companies, invented notes, and invented price snapshots live in `fixtures/scenario.json`. Three small, read-only workers select context, catalyst, and skeptic notes; each accepts at most two sources. The one-page Markdown memo repeats those claims with fixture IDs, publication and availability times, an as-of timestamp, a price citation, and a countercase. Future-dated evidence fails rather than quietly appearing in an earlier memo. There is no model call or data feed in this version.

**Hypothetical example:** Orchid Relay Works has an invented board-certification review and an invented supplier delay that might undercut it. Its March fixture quote is $48. A person can inspect a three-share PAPER proposal and choose approve, reject, or defer; an invented April $44 snapshot then gives an approved position a retrospective question to revisit. Neither price is from a market.

From the repository root:

```sh
export PYTHONPATH=src
python3.12 -m investing_desk memo --company SIM-ORC
python3.12 -m investing_desk propose --company SIM-ORC --shares 3
# Copy the ID and full hash printed by propose:
ID='P-...'
HASH='...'
python3.12 -m investing_desk show --id "$ID"
python3.12 -m investing_desk decide --id "$ID" --hash "$HASH" --action approve --actor "Your label"
python3.12 -m investing_desk monitor --id "$ID" --through 2026-04-15T20:05:00Z
python3.12 -m investing_desk retrospective --id "$ID"
```

`decide` requires an interactive terminal and a typed confirmation; `reject` and `defer` record a decision without a position. Proposals expire after 24 hours. Approved PAPER entries live only in `.investing-desk/paper.sqlite3` (git-ignored), with a $10,000 invented starting balance, at most $500 committed per fictional company and $2,000 total, plus explicit assumed fees and slippage. The hash binds a decision to the reviewed memo and proposal; it does not authenticate a person or protect an editable local database.

The next work is source-rights review, timestamped evidence ingestion, stronger simulation, and more useful monitoring. Any real-money integration would need its own authorization and controls; the included `DisabledLiveOrderAdapter` has no enable switch. See the [roadmap](docs/roadmap.md), [research sources](docs/research.md), and [data policy](docs/data-policy.md). Original code and artwork are MIT-licensed under [LICENSE](LICENSE). Run `PYTHONPATH=src python3.12 -m unittest discover -s tests -v` to check the starter. GitHub Actions runs the same offline suite on pushes and pull requests.
