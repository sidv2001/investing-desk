# Data, local state, and simulation policy

The checked-in scenario is original synthetic material: `SIM-ORC` and
`SIM-TID` are fictional identifiers, the businesses and notes are invented, and
the prices are fabricated. The loader accepts only a local JSON scenario
labeled `synthetic`, explicitly fictional companies, and `fixture://` source
identifiers. Those identifiers are citations to invented fixture records, not
URLs the software fetches. The program makes no model, broker, telemetry, or
market-data network requests and has no credential configuration.

Do not commit real price histories, news, provider extracts, or credentials to
the public repository. Before using an external source in a future phase,
review its license and terms for collection, retention, redistribution, and AI
processing; record attribution, publication time, *actual availability* time,
revisions, coverage, and permitted uses. FRED hosts third-party series with
separate restrictions; its public availability does not grant blanket
redistribution or AI rights. The MIT license applies to this repository's
original code and artwork, not third-party data. See [research sources](research.md).

The CLI stores proposal Markdown, SHA-256 hashes, human-entered actor labels,
decisions, PAPER entries, and later synthetic observations in a local, ignored
SQLite file (`.investing-desk/paper.sqlite3` by default). It is not encrypted,
identity-verified, tamper-proof, or synced. Deleting that file discards the
local paper history. Hashes bind the reviewed memo and proposal fields for
accidental-change detection; they are not signatures or authorization.

The toy ledger starts with $10,000 virtual cash. It permits positive whole-share
buy entries only, caps **committed cost including the buy fee** at $500 per
fictional company and $2,000 across companies, and rejects any entry without a
matching, unexpired human decision. Buy and hypothetical exit prices each
assume 0.10% adverse slippage rounded to cents per share and a $1 fee.
Proposals expire 24 hours after creation. Monitoring is a manual request for a
later *available* invented snapshot; the retrospective estimates an exit but
does not book a sale.

These assumptions omit spread, liquidity, queueing, partial fills, market
impact, outages, dividends, corporate actions, taxes, and changing fee
schedules. The scenario's as-of time is historical; a proposal is created at
the operator's current UTC time. An invented price difference is neither a
realized return nor evidence that a catalyst occurred. Live orders are
deliberately unreachable: the adapter always raises and has no configuration
path to enable it.
