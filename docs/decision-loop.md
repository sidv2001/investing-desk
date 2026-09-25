# Decision loop (text alternative)

1. **Read local fictional evidence.** Each note has a fixture citation,
   publication time, and availability time. Invented price snapshots have
   observation and availability times. The as-of cutoff excludes later prices;
   future-dated memo evidence causes an error.
2. **Build a cited memo.** Separate context, catalyst, and skeptic workers
   each see at most two notes for their role. They repeat fixture claims with
   source IDs and do not access the ledger.
3. **Keep the decision human.** Review the one-page memo, price citation,
   proposal costs, hash, and expiry. A person interactively approves, rejects,
   or defers a PAPER proposal. Rejecting or deferring creates no position.
4. **Record an approved PAPER entry locally.** SQLite enforces the approval
   gate. The application checks modeled costs, per-company and total exposure,
   available virtual cash, and proposal expiry before booking.
5. **Monitor and reflect.** A human records a later, available invented price.
   The retrospective compares the cost-aware hypothetical exit with the
   original catalyst and countercase. The price change cannot prove why it
   happened.

**Separate boundary:** `DisabledLiveOrderAdapter` always raises on submit,
cancel, or replace; no arrow in the diagram leads to a broker or live order.
