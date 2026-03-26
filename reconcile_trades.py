#!/usr/bin/env python3
"""
reconcile_trades.py
Epic Trading — Trade Reconciliation Tool

Matching logic:
    expected_settlement = (quantity * price) + fee   [from internal_ledger.json]
    actual_settlement   = amount_settled             [from bank_settlement.csv]

Checks both directions:
    1. Ledger → Bank  (missing in bank, amount mismatch)
    2. Bank → Ledger  (present in bank but not in ledger)
"""

import json
import csv
import sys
from pathlib import Path

LEDGER_FILE = Path(__file__).parent / "internal_ledger.json"
BANK_FILE   = Path(__file__).parent / "bank_settlement.csv"

# ── ANSI colours (disabled if not a tty) ────────────────────────────────────
USE_COLOUR = sys.stdout.isatty()
RED    = "\033[91m" if USE_COLOUR else ""
YELLOW = "\033[93m" if USE_COLOUR else ""
GREEN  = "\033[92m" if USE_COLOUR else ""
CYAN   = "\033[96m" if USE_COLOUR else ""
BOLD   = "\033[1m"  if USE_COLOUR else ""
RESET  = "\033[0m"  if USE_COLOUR else ""

SEPARATOR = "─" * 72


def load_ledger(path: Path) -> dict[str, dict]:
    with open(path) as f:
        records = json.load(f)
    ledger = {}
    for r in records:
        tid = r["trade_id"]
        expected = round(r["quantity"] * r["price"] + r["fee"], 2)
        ledger[tid] = {
            "symbol":   r["symbol"],
            "quantity": r["quantity"],
            "price":    r["price"],
            "fee":      r["fee"],
            "expected": expected,
        }
    return ledger


def load_bank(path: Path) -> dict[str, float]:
    bank = {}
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            bank[row["trade_id"]] = round(float(row["amount_settled"]), 2)
    return bank


def reconcile(ledger: dict, bank: dict) -> list[dict]:
    issues = []

    # ── Pass 1: Ledger → Bank ────────────────────────────────────────────────
    for tid, data in sorted(ledger.items()):
        if tid not in bank:
            issues.append({
                "type":     "MISSING_IN_BANK",
                "trade_id": tid,
                "symbol":   data["symbol"],
                "expected": data["expected"],
                "actual":   None,
                "delta":    None,
            })
        else:
            actual = bank[tid]
            delta  = round(actual - data["expected"], 2)
            if delta != 0:
                issues.append({
                    "type":     "AMOUNT_MISMATCH",
                    "trade_id": tid,
                    "symbol":   data["symbol"],
                    "expected": data["expected"],
                    "actual":   actual,
                    "delta":    delta,
                })

    # ── Pass 2: Bank → Ledger ────────────────────────────────────────────────
    for tid, actual in sorted(bank.items()):
        if tid not in ledger:
            issues.append({
                "type":     "MISSING_IN_LEDGER",
                "trade_id": tid,
                "symbol":   "—",
                "expected": None,
                "actual":   actual,
                "delta":    None,
            })

    return issues


def fmt_usd(value) -> str:
    if value is None:
        return "N/A"
    return f"${value:>10,.2f}"


def print_report(issues: list[dict], ledger: dict, bank: dict) -> None:
    mismatches      = [i for i in issues if i["type"] == "AMOUNT_MISMATCH"]
    missing_in_bank = [i for i in issues if i["type"] == "MISSING_IN_BANK"]
    missing_in_led  = [i for i in issues if i["type"] == "MISSING_IN_LEDGER"]

    print(f"\n{BOLD}{SEPARATOR}")
    print("  EPIC TRADING — RECONCILIATION REPORT")
    print(f"{SEPARATOR}{RESET}")
    print(f"  Ledger trades : {len(ledger)}")
    print(f"  Bank records  : {len(bank)}")
    print(f"  Total issues  : {BOLD}{len(issues)}{RESET}\n")

    # ── Amount Mismatches ────────────────────────────────────────────────────
    print(f"{BOLD}{CYAN}[AMOUNT MISMATCHES]  ({len(mismatches)} found){RESET}")
    print(SEPARATOR)
    if mismatches:
        print(f"  {'Trade ID':<12} {'Symbol':<8} {'Expected':>12} {'Bank Settled':>14} {'Delta':>12}")
        print(f"  {'─'*12} {'─'*8} {'─'*12} {'─'*14} {'─'*12}")
        for i in mismatches:
            colour = RED if i["delta"] < 0 else YELLOW
            print(
                f"  {i['trade_id']:<12} {i['symbol']:<8} "
                f"{fmt_usd(i['expected']):>12} {fmt_usd(i['actual']):>14} "
                f"{colour}{fmt_usd(i['delta']):>12}{RESET}"
            )
    else:
        print(f"  {GREEN}No amount mismatches found.{RESET}")

    # ── Missing in Bank ──────────────────────────────────────────────────────
    print(f"\n{BOLD}{YELLOW}[MISSING IN BANK]  ({len(missing_in_bank)} found){RESET}")
    print(SEPARATOR)
    if missing_in_bank:
        print(f"  {'Trade ID':<12} {'Symbol':<8} {'Expected Settlement':>20}")
        print(f"  {'─'*12} {'─'*8} {'─'*20}")
        for i in missing_in_bank:
            print(f"  {i['trade_id']:<12} {i['symbol']:<8} {fmt_usd(i['expected']):>20}")
    else:
        print(f"  {GREEN}All ledger trades present in bank file.{RESET}")

    # ── Missing in Ledger ────────────────────────────────────────────────────
    print(f"\n{BOLD}{RED}[MISSING IN LEDGER]  ({len(missing_in_led)} found){RESET}")
    print(SEPARATOR)
    if missing_in_led:
        print(f"  {'Trade ID':<12} {'Bank Amount Settled':>20}")
        print(f"  {'─'*12} {'─'*20}")
        for i in missing_in_led:
            print(f"  {i['trade_id']:<12} {fmt_usd(i['actual']):>20}")
    else:
        print(f"  {GREEN}All bank records present in ledger.{RESET}")

    # ── Summary ──────────────────────────────────────────────────────────────
    print(f"\n{BOLD}{SEPARATOR}")
    print("  SUMMARY")
    print(SEPARATOR + RESET)
    if issues:
        total_exposure = sum(
            abs(i["delta"]) for i in mismatches if i["delta"] is not None
        )
        print(f"  Amount mismatches      : {len(mismatches)}")
        print(f"  Missing in bank        : {len(missing_in_bank)}")
        print(f"  Missing in ledger      : {len(missing_in_led)}")
    else:
        print(f"  {GREEN}{BOLD}✓ Files are fully reconciled. No discrepancies found.{RESET}")
    print(SEPARATOR + "\n")


def main():
    for path in (LEDGER_FILE, BANK_FILE):
        if not path.exists():
            print(f"ERROR: required file not found → {path}", file=sys.stderr)
            sys.exit(1)

    ledger = load_ledger(LEDGER_FILE)
    bank   = load_bank(BANK_FILE)
    issues = reconcile(ledger, bank)
    print_report(issues, ledger, bank)
    sys.exit(1 if issues else 0)


if __name__ == "__main__":
    main()
