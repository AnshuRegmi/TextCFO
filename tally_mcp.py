"""MCP server for Tally Prime data access.

This server exposes a small set of tools that the orchestrator can discover
and call over stdio using the MCP protocol.
"""

from __future__ import annotations

import os
from typing import Callable
from xml.etree import ElementTree as ET

import requests
from mcp.server.fastmcp import FastMCP


mcp = FastMCP("Tally MCP")

TALLY_URL = os.getenv("TALLY_URL", "http://localhost:9000")
TALLY_TIMEOUT = float(os.getenv("TALLY_TIMEOUT", "30"))

_CACHE: dict[str, str] = {}


def _parse_xml(raw: str) -> ET.Element:
    """Parse a Tally XML response and return the root element."""
    try:
        return ET.fromstring(raw)
    except ET.ParseError:
        # Tally responses are usually well-formed, but if a response arrives
        # without a single root element, wrap it so callers still get a tree.
        return ET.fromstring(f"<ROOT>{raw}</ROOT>")


def tally_collection(name: str) -> str:
    """Fetch a Tally collection by name."""
    payload = f"""<?xml version='1.0' encoding='utf-8'?>
<ENVELOPE>
  <HEADER>
    <VERSION>1</VERSION>
    <TALLYREQUEST>Export Data</TALLYREQUEST>
    <TYPE>Collection</TYPE>
    <ID>{name}</ID>
  </HEADER>
  <BODY>
    <DESC/>
  </BODY>
</ENVELOPE>"""
    response = requests.post(TALLY_URL, data=payload, timeout=TALLY_TIMEOUT)
    response.raise_for_status()
    return response.text


def tally_report(name: str) -> str:
    """Fetch a Tally report by name."""
    payload = f"""<?xml version='1.0' encoding='utf-8'?>
<ENVELOPE>
  <HEADER>
    <VERSION>1</VERSION>
    <TALLYREQUEST>Export Data</TALLYREQUEST>
    <TYPE>Report</TYPE>
    <ID>{name}</ID>
  </HEADER>
  <BODY>
    <DESC/>
  </BODY>
</ENVELOPE>"""
    response = requests.post(TALLY_URL, data=payload, timeout=TALLY_TIMEOUT)
    response.raise_for_status()
    return response.text


def _live_or_cache(key: str, fetch: Callable[[], str], format_result: Callable[[str], str]) -> str:
    """Fetch fresh data when possible, otherwise return a cached formatted result."""
    try:
        raw = fetch()
        formatted = format_result(raw)
        _CACHE[key] = formatted
        return formatted
    except Exception as exc:
        if key in _CACHE:
            return f"⚠️ Live fetch failed, showing cached data.\n{_CACHE[key]}"
        return f"❌ Unable to fetch {key}: {exc}"


# Lines 174-177: Section Header
# ─────────────────────────────────────────────────────────
#  Parsers
#  Each matches the exact XML structure from YOUR Tally
# ─────────────────────────────────────────────────────────


# Lines 179-199: _parse_ledgers Function
def _parse_ledgers(raw: str) -> list[dict]:
    """
    Source: Collection:Ledger
    Structure: <LEDGER NAME="Cash" RESERVEDNAME="">
                 <PARENT TYPE="String">Cash-in-Hand</PARENT>
                 <CLOSINGBALANCE TYPE="Amount">...</CLOSINGBALANCE>
    """
    root = _parse_xml(raw)
    results = []
    for el in root.iter("LEDGER"):
        name = el.get("NAME")
        if not name:
            continue
        parent_el = el.find("PARENT")
        closing_el = el.find("CLOSINGBALANCE")
        results.append(
            {
                "name": name,
                "group": parent_el.text.strip() if parent_el is not None and parent_el.text else "",
                "balance": float(closing_el.text.strip()) if closing_el is not None and closing_el.text and closing_el.text.strip() else 0.0,
            }
        )
    return results


# Lines 202-208: _parse_groups Function
def _parse_groups(raw: str) -> list[str]:
    """
    Source: Collection:Group
    Structure: <GROUP NAME="Bank Accounts" RESERVEDNAME="...">
    """
    root = _parse_xml(raw)
    return [el.get("NAME") for el in root.iter("GROUP") if el.get("NAME")]


# Lines 211-217: _parse_stock_items Function
def _parse_stock_items(raw: str) -> list[str]:
    """
    Source: Collection:StockItem
    Structure: <STOCKITEM NAME="Item_1" RESERVEDNAME="">
    """
    root = _parse_xml(raw)
    return [el.get("NAME") for el in root.iter("STOCKITEM") if el.get("NAME")]


# Lines 220-260: _parse_display_report Function
def _parse_display_report(raw: str, amount_tag: str) -> list[dict]:
    """
    Generic parser for Trial Balance, P&L, Balance Sheet.
    All use <DSPDISPNAME> for account names, paired with amount tags.
    """
    root = _parse_xml(raw)
    names = [el.text for el in root.iter("DSPDISPNAME") if el.text]

    if amount_tag == "trial_balance":
        dr_els = list(root.iter("DSPCLDRAMTA"))
        cr_els = list(root.iter("DSPCLCRAMTA"))
        rows = []
        for i, name in enumerate(names):
            dr = dr_els[i].text.strip() if i < len(dr_els) and dr_els[i].text and dr_els[i].text.strip() else ""
            cr = cr_els[i].text.strip() if i < len(cr_els) and cr_els[i].text and cr_els[i].text.strip() else ""
            rows.append({"name": name, "debit": dr, "credit": cr})
        return rows

    elif amount_tag == "pnl":
        main_els = list(root.iter("BSMAINAMT"))
        sub_els = list(root.iter("PLSUBAMT"))
        rows = []
        for i, name in enumerate(names):
            main = main_els[i].text.strip() if i < len(main_els) and main_els[i].text and main_els[i].text.strip() else ""
            sub = sub_els[i].text.strip() if i < len(sub_els) and sub_els[i].text and sub_els[i].text.strip() else ""
            rows.append({"name": name, "amount": main or sub or "0"})
        return rows

    elif amount_tag == "balance_sheet":
        main_els = list(root.iter("BSMAINAMT"))
        rows = []
        for i, name in enumerate(names):
            amt = main_els[i].text.strip() if i < len(main_els) and main_els[i].text and main_els[i].text.strip() else "0"
            rows.append({"name": name, "amount": amt})
        return rows

    return []


# Lines 345-352: _fmt_currency Function
# ─────────────────────────────────────────────────────────
#  Formatting Helpers
# ─────────────────────────────────────────────────────────


def _fmt_currency(value: float) -> str:
    """Format as Indian currency: ₹1,23,456.00"""
    return f"₹{abs(value):,.2f}"


# Lines 354-356: Section Header
# ─────────────────────────────────────────────────────────
#  MCP Tools — 11 tools
# ─────────────────────────────────────────────────────────


# Lines 358-375: get_all_ledgers Tool
@mcp.tool()
def get_all_ledgers() -> str:
    """Get all ledger accounts with their group and closing balance."""

    def fetch():
        return tally_collection("Ledger")

    def format(raw):
        ledgers = _parse_ledgers(raw)
        if not ledgers:
            return "No ledgers found."
        lines = []
        for l in ledgers:
            bal_str = _fmt_currency(l["balance"]) if l["balance"] != 0 else "0"
            lines.append(f"{l['name']} | Group: {l['group']} | Balance: {bal_str}")
        return "\n".join(lines)

    return _live_or_cache("ledgers", fetch, format)


# Lines 378-389: get_account_groups Tool
@mcp.tool()
def get_account_groups() -> str:
    """Get all account groups."""

    def fetch():
        return tally_collection("Group")

    def format(raw):
        groups = _parse_groups(raw)
        return "\n".join(groups) if groups else "No groups found."

    return _live_or_cache("groups", fetch, format)


# Lines 392-403: get_stock_items Tool
@mcp.tool()
def get_stock_items() -> str:
    """Get all inventory/stock items."""

    def fetch():
        return tally_collection("StockItem")

    def format(raw):
        items = _parse_stock_items(raw)
        return "\n".join(items) if items else "No stock items found."

    return _live_or_cache("stock_items", fetch, format)


# Lines 406-427: get_trial_balance Tool
@mcp.tool()
def get_trial_balance() -> str:
    """Get trial balance with debit/credit for all account groups."""

    def fetch():
        return tally_report("Trial Balance")

    def format(raw):
        rows = _parse_display_report(raw, "trial_balance")
        if not rows:
            return "Empty trial balance."
        lines = []
        for r in rows:
            parts = [r["name"] + ":"]
            if r["debit"]:
                parts.append(f"Dr {r['debit']}")
            if r["credit"]:
                parts.append(f"Cr {r['credit']}")
            lines.append(" ".join(parts))
        return "\n".join(lines)

    return _live_or_cache("trial_balance", fetch, format)


# Lines 430-447: get_profit_and_loss Tool
@mcp.tool()
def get_profit_and_loss() -> str:
    """Get P&L: sales, costs, expenses, net profit."""

    def fetch():
        return tally_report("Profit and Loss")

    def format(raw):
        rows = _parse_display_report(raw, "pnl")
        if not rows:
            return "Empty P&L."
        lines = []
        for r in rows:
            amt = r["amount"] if r["amount"] != "0" else "-"
            lines.append(f"{r['name']}: {amt}")
        return "\n".join(lines)

    return _live_or_cache("pnl", fetch, format)

# Lines 450-467: get_balance_sheet Tool
@mcp.tool()
def get_balance_sheet() -> str:
    """Get Balance Sheet: capital, loans, liabilities, assets."""

    def fetch():
        return tally_report("Balance Sheet")

    def format(raw):
        rows = _parse_display_report(raw, "balance_sheet")
        if not rows:
            return "Empty balance sheet."
        lines = []
        for r in rows:
            amt = r["amount"] if r["amount"] != "0" else "-"
            lines.append(f"{r['name']}: {amt}")
        return "\n".join(lines)

    return _live_or_cache("balance_sheet", fetch, format)

# Lines 470-492: get_sundry_debtors Tool
@mcp.tool()
def get_sundry_debtors() -> str:
    """Get customers who owe us money (Sundry Debtors), sorted by amount."""

    def fetch():
        return tally_collection("Ledger")

    def format(raw):
        ledgers = _parse_ledgers(raw)
        debtors = [l for l in ledgers if l["group"] == "Sundry Debtors"]
        if not debtors:
            return "No sundry debtors found."
        debtors.sort(key=lambda d: abs(d["balance"]), reverse=True)
        lines = ["RECEIVABLES (customers who owe us):\n"]
        total = 0.0
        for d in debtors:
            amt = abs(d["balance"])
            total += amt
            lines.append(f"  {d['name']}: {_fmt_currency(amt)}")
        lines.append(f"\nTotal Receivable: {_fmt_currency(total)}")
        return "\n".join(lines)

    return _live_or_cache("debtors", fetch, format)


def main() -> None:
    """Run the MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()