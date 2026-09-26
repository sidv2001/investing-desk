# Roadmap

I want an investing harness that looks beyond the big-tech stocks, ETFs, and
index funds I already know. Agents with tools should investigate long- and
short-term opportunities and bring me analyst-style one-pagers to review like
a portfolio manager. I want independent workers running continuously and in
parallel, monitoring positions, learning from outcomes and strategy
performance, and using market sentiment to guide decisions. Eventually, I
want the system to make and execute authorized portfolio decisions, including
shorter-term, higher-frequency ones, without a manual click for every trade.
These stages are capabilities to build, not promises of returns or a delivery
date.

**Now — offline fictional starter, not the destination.** Python 3.12 and
standard-library-only runtime; two local fictional companies;
timestamp-checked, cited one-page memos from bounded read-only workers;
manual approve/reject/defer of a hashed, expiring PAPER proposal; risk- and
cost-bounded SQLite entries; manual invented-price monitoring; retrospectives
that surface the original catalyst and countercase. The live-order adapter
only raises. There is no market feed, model call, broker, order client, or
background watcher. Per-proposal human approval is how this demo works, not
the intended trading model.

**Broaden research with tools and evidence.** I want agents to investigate a
variety of opportunities across time horizons, challenge each other's theses,
and deliver dated, cited one-pagers with a countercase and uncertainty. Before
connecting outside sources, check collection, AI-processing, and redistribution
rights; retain publication, availability, revision, and as-of times; test
missing and contradictory evidence. The current workers do not have external
tools or a model.

**Orchestrate parallel work and test decisions.** I want workers to look for
new opportunities and monitor holdings independently and continuously, with
an orchestrator handling handoffs, scheduling, and stale or missing evidence.
Before relying on their decisions, test with permitted point-in-time data,
out-of-sample periods, and paper execution that accounts for spreads, fees,
splits, dividends, partial fills, and delayed data. A paper-broker connection
would be a separate integration, not a switch on the local ledger.

**Learn and adapt from results.** I want retrospectives to track what worked
and what didn't across decisions and strategies, alongside market sentiment.
Use that evidence to adjust research priorities and decision rules, and check
changes against out-of-sample results and costs rather than treating a price
move as proof of a thesis. This feedback loop should begin in paper evaluation
and continue if live execution is authorized.

**Execute autonomously within authorized limits.** I eventually want agents
to invest money in the market, monitor positions, and make shorter-term,
higher-frequency adjustments without per-order approval when actions fall
within authority I have explicitly granted. That requires identity-bound
authorization, independent hard risk limits, test and reconciliation evidence,
audit trails, failure handling, a kill switch, and applicable legal/compliance
review before any broker connection. Actions outside that authority need new
authorization. The current `DisabledLiveOrderAdapter` cannot submit, cancel,
or replace live orders and has no configuration switch to enable them.

Today's synthetic data and local ledger are described in the
[data policy](data-policy.md); source considerations are in
[research sources](research.md).
