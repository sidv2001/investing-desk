"""Human-operated command line for the offline PAPER loop."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from .paper import Decision, PaperLedger, Proposal
from .research import build_memo
from .scenario import display_stamp, load_scenario, parse_instant


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fictional, offline research and PAPER ledger")
    parser.add_argument("--fixture", type=Path, default=Path("fixtures/scenario.json"))
    parser.add_argument("--db", type=Path, default=Path(".investing-desk/paper.sqlite3"))
    commands = parser.add_subparsers(dest="command", required=True)
    memo = commands.add_parser("memo", help="Print a cited one-page memo")
    memo.add_argument("--company", required=True)
    propose = commands.add_parser("propose", help="Save an undecided PAPER proposal")
    propose.add_argument("--company", required=True)
    propose.add_argument("--shares", type=int, required=True)
    show = commands.add_parser("show", help="Review a saved PAPER proposal")
    show.add_argument("--id", required=True)
    decide = commands.add_parser("decide", help="Interactively approve, reject or defer PAPER")
    decide.add_argument("--id", required=True)
    decide.add_argument("--hash", required=True, help="Full hash shown with the reviewed proposal")
    decide.add_argument("--action", choices=[choice.value for choice in Decision], required=True)
    decide.add_argument("--actor", required=True, help="Local human decision label")
    monitor = commands.add_parser("monitor", help="Record a later fictional price snapshot")
    monitor.add_argument("--id", required=True)
    monitor.add_argument("--through", type=parse_instant, required=True)
    retrospective = commands.add_parser("retrospective", help="Review a PAPER position and snapshot")
    retrospective.add_argument("--id", required=True)
    return parser


def _proposal_text(proposal: Proposal) -> str:
    estimate = proposal.estimate
    return (
        f"{proposal.memo_markdown}\n"
        f"## PAPER proposal {proposal.id}\n"
        f"Shares: {proposal.shares}; assumed buy fill ${estimate.assumed_fill_price:.2f} "
        f"(0.10% slippage), fee ${estimate.fee:.2f}; total ${estimate.total_cost:.2f}.\n"
        f"Proposal SHA-256: {proposal.proposal_hash}\n"
        f"Created: {display_stamp(proposal.created_at)}; "
        f"expires: {display_stamp(proposal.expires_at)}."
    )


def _run(args: argparse.Namespace) -> int:
    if args.command == "memo":
        print(build_memo(load_scenario(args.fixture), args.company).render())
        return 0

    ledger = PaperLedger(args.db)
    if args.command == "propose":
        memo = build_memo(load_scenario(args.fixture), args.company)
        proposal = ledger.create_proposal(memo, args.shares, _now())
        print(_proposal_text(proposal))
        print("Status: pending human decision; no PAPER entry booked.")
        return 0
    if args.command == "show":
        proposal = ledger.get_proposal(args.id)
        print(_proposal_text(proposal))
        decision = ledger.get_decision(args.id)
        if decision is not None:
            print(
                f"Decision: {decision.action.value} by {decision.actor} "
                f"at {display_stamp(decision.decided_at)}"
            )
        elif _now() >= proposal.expires_at:
            print("Status: expired without decision; create a new proposal.")
        else:
            print("Status: pending human decision; no PAPER entry booked.")
        return 0
    if args.command == "decide":
        proposal = ledger.get_proposal(args.id)
        if args.hash != proposal.proposal_hash:
            raise ValueError("Approval hash does not match the reviewed PAPER proposal")
        if not sys.stdin.isatty():
            raise ValueError("A human must confirm in an interactive terminal; no decision recorded")
        print(_proposal_text(proposal))
        phrase = f"PAPER {args.action.upper()} {proposal.id} {proposal.proposal_hash[:12]}"
        try:
            response = input(f"\nType '{phrase}' to record this decision: ")
        except EOFError as exc:
            raise ValueError("Confirmation input closed; no decision recorded") from exc
        if response != phrase:
            raise ValueError("Confirmation did not match; no decision recorded")
        decision = ledger.decide(
            proposal.id, proposal.proposal_hash, Decision(args.action), args.actor, _now()
        )
        print(f"PAPER {decision.action.value} recorded by {decision.actor}.")
        return 0
    if args.command == "monitor":
        quote = ledger.record_observation(
            args.id, load_scenario(args.fixture), args.through
        )
        print(
            f"Recorded synthetic ${quote.price:.2f} [{quote.id}] "
            f"at {display_stamp(quote.observed_at)} "
            f"(available {display_stamp(quote.available_at)}); "
            f"run retrospective --id {args.id}."
        )
        return 0
    print(ledger.render_retrospective(args.id))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        return _run(args)
    except (ValueError, FileNotFoundError, sqlite3.Error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
