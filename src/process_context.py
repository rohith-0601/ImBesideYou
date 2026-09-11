"""
Per-event business-process context.

Day 2 correction to a Day 1 mistake
-----------------------------------
Day 1 labelled processes from the SPA route alone (`#/payroll-items` ->
"payroll_change"). That was wrong, and the error mattered.

Dataset B contains **three different business systems**, served on three
ports, and they *reuse the same route names*:

    127.0.0.1:5132  HR人事給与システム        HR / payroll
    127.0.0.1:5133  財務会計システム          financial accounting
    127.0.0.1:5134  受発注在庫管理システム    order / inventory management

`browser_navigation` payloads carry both `url` and `page_title`, which is how
the mapping is established. The same route means unrelated work on different
systems — `#/social-insurance` is welfare applications on HR, **budget
variance analysis** on Finance, and **IT equipment requests** on Inventory.

So the process identity is the **(system, route)** pair, never the route
alone. Route-only labelling merged invoice approval, HR payroll changes and
inventory work into one bogus "payroll_change" class — the real reason Day 1
saw 96 payroll "cases" at a 6.7s median. It was not list-view rendering, as
Day 1 guessed.

The pair is forward-filled **atomically** (port and route taken from the same
URL string and carried together). Filling them independently lets a stale
route from one system attach to a newly-focused other system, which
manufactured three phantom processes in the first Day 2 run
(`hr_resident_tax`, `inv_order_check`, `inv_inventory_review` — each a
handful of events, no `p_code` support, no business vocabulary).

Independent confirmation of the taxonomy
----------------------------------------
Clicked UIA rows carry names of the form ``P<n>-<8 digits>-<3 digits>``
(control_type ``DataItem``). These are *not* case IDs — the 8-digit body is
constant within a session and the 3-digit tail is ``012`` for 90% of them.
But the ``P<n>`` prefix maps essentially 1:1 onto (system, route):

    P2 -> HR leave         P6  -> Fin invoice      P11 -> Inv product
    P3 -> HR onboarding    P7  -> Fin payment      P12 -> Inv contract
    P4 -> HR expense       P9  -> Fin expense      P13 -> Inv IT request
    P5 -> HR welfare       P10 -> Fin bank recon

11 of 12 P-numbers sit in exactly one (system, route) at 82-100%. Two
independently-produced signals agreeing is the strongest evidence available
without ground truth, so `p_code` is carried through and scored in
`evaluate.py` rather than used as the primary label.

Signal availability (measured, per session)
-------------------------------------------
- `browser_url` is populated on only 37-66% of events, and on **0%** of
  `ses_20260701-192455-NEELA9BAF`, which recorded no L3 events at all
  (the browser extension never connected). URL alone is not enough.
- `window_title` names the system on 96.6-100% of Edge events in *every*
  session, including that one, and agrees with the URL port 96.5% of the
  time (n=9,362). It gives the system but never the route, so it is used to
  validate the URL-derived system and to label the L3-less session at
  system granularity only.
"""

from __future__ import annotations

import re

import pandas as pd

PORT_SYSTEM = {
    "5132": "hr_payroll",
    "5133": "financial_accounting",
    "5134": "order_inventory",
}

TITLE_SYSTEM = [
    ("財務会計", "financial_accounting"),
    ("受発注在庫管理", "order_inventory"),
    ("人事給与", "hr_payroll"),
]

# (port, route) -> process label.
#
# Each label is named from the business vocabulary that actually appears on
# that screen's clicked elements and typed comments, NOT from the route
# string. Japanese evidence for each is in reports/day2_processes.md.
PROCESS_LABELS = {
    # --- HR人事給与システム ---
    ("5132", "#/payroll-items"):      "hr_expense_and_payroll_change",
    ("5132", "#/leave-applications"): "hr_leave_application",
    ("5132", "#/onboarding"):         "hr_onboarding_verification",
    ("5132", "#/social-insurance"):   "hr_welfare_application",
    # --- 財務会計システム ---
    ("5133", "#/payroll-items"):      "fin_invoice_matching",
    ("5133", "#/onboarding"):         "fin_payment_processing",
    ("5133", "#/leave-applications"): "fin_expense_approval",
    ("5133", "#/resident-tax"):       "fin_bank_reconciliation",
    ("5133", "#/social-insurance"):   "fin_budget_variance_analysis",
    # --- 受発注在庫管理システム ---
    ("5134", "#/leave-applications"): "inv_contract_management",
    ("5134", "#/payroll-items"):      "inv_stock_adjustment",
    ("5134", "#/social-insurance"):   "inv_it_request_processing",
}

# Dashboard is a landing/overview screen, not a unit of work. Kept out of the
# label map so it is absorbed into the surrounding process rather than
# emitted as a segment.
IGNORED_ROUTES = {"#/dashboard", "#/"}

NON_PROCESS_APPS = {
    "procmine-desktop-agent",  # the recording agent itself
    "prl_cc",                  # Parallels control centre (VM chrome)
    "ms-teams",                # comms
    "WindowsTerminal",
}
NON_PROCESS_URL_HINTS = ("slack.com",)

# Events where the worker actively did something, as opposed to ambient
# capture. Used to decide whether an episode is real work or a glance.
SUBSTANTIVE_EVENTS = {
    "mouse_click", "mouse_double_click", "mouse_drag_drop",
    "keystroke", "shortcut", "clipboard_change",
    "browser_click", "browser_form_input", "browser_navigation",
    "text_input_complete", "dialog_opened",
}

_PORT_RE = re.compile(r"://[^/]*?:(\d{4})")
_PCODE_RE = re.compile(r"^(P\d{1,2})-(\d{6,9})-(\d{2,4})$")


def route_of(url) -> str | None:
    """'http://127.0.0.1:5132/#/payroll-items?x=1' -> '#/payroll-items'."""
    if not isinstance(url, str) or "#/" not in url:
        return None
    return "#/" + url.split("#/", 1)[1].split("?")[0]


def _port_of(url) -> str | None:
    if not isinstance(url, str):
        return None
    m = _PORT_RE.search(url)
    return m.group(1) if m else None


def _system_from_title(title) -> str | None:
    if not isinstance(title, str):
        return None
    for needle, system in TITLE_SYSTEM:
        if needle in title:
            return system
    return None


def _dig(d, *keys):
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def p_code_of(payload) -> str | None:
    """Extract the P<n> process code from a clicked UIA DataItem name."""
    if not isinstance(payload, dict):
        return None
    for path in (("target_element", "name"),
                 ("target_element", "value"),
                 ("target_field", "value")):
        v = _dig(payload, *path)
        if isinstance(v, str):
            m = _PCODE_RE.match(v.strip())
            if m:
                return m.group(1)
    return None


def annotate(df: pd.DataFrame) -> pd.DataFrame:
    """Add process-context columns to an events frame.

    Adds `port`, `route`, `pair`, `pair_ff`, `system_url`, `system_title`,
    `system`, `p_code`, `is_non_process`, `is_substantive`, `process_label`.
    """
    df = df.copy()

    df["port"] = df["browser_url"].map(_port_of)
    df["route"] = df["browser_url"].map(route_of)

    # Atomic (port, route) pair — both from the same URL, carried together.
    # NOTE: guard with isinstance, not truthiness — float('nan') is truthy,
    # which silently produced a literal "nan|nan" pair for 11,042 events on
    # the first attempt and dropped label coverage to 45%.
    df["pair"] = [
        f"{p}|{r}"
        if (isinstance(p, str) and isinstance(r, str) and r not in IGNORED_ROUTES)
        else None
        for p, r in zip(df["port"], df["route"])
    ]
    df["pair_ff"] = df.groupby("session_id", sort=False)["pair"].ffill()
    df["pair_ff"] = df.groupby("session_id", sort=False)["pair_ff"].bfill()

    df["system_title"] = df["window_title"].map(_system_from_title)
    df["system_url"] = df["port"].map(PORT_SYSTEM)
    df["p_code"] = df["payload"].map(p_code_of)

    app = df["app_name"].fillna("")
    url = df["browser_url"].fillna("")
    df["is_non_process"] = app.isin(NON_PROCESS_APPS) | url.str.contains(
        "|".join(re.escape(h) for h in NON_PROCESS_URL_HINTS), na=False
    )
    df["is_substantive"] = df["event_type"].isin(SUBSTANTIVE_EVENTS)

    def _label(pair):
        if not isinstance(pair, str):
            return None
        port, route = pair.split("|", 1)
        return PROCESS_LABELS.get((port, route))

    df["process_label"] = df["pair_ff"].map(_label)

    # Sessions with no L3 at all have no URL ever, so no route is knowable.
    # Fall back to system-only granularity from the window title, which is
    # honest about the coarser resolution instead of inventing a route.
    sys_ff = df.groupby("session_id", sort=False)["system_title"].ffill()
    sys_ff = df.groupby("session_id", sort=False)["system_title"].bfill().fillna(sys_ff)
    no_url = ~df.groupby("session_id", sort=False)["pair"].transform(
        lambda s: s.notna().any()
    )
    df.loc[no_url, "process_label"] = sys_ff[no_url].map(
        lambda s: f"{s}_unresolved" if isinstance(s, str) else None
    )
    df["system"] = df["system_title"].fillna(df["system_url"])
    df["system"] = df.groupby("session_id", sort=False)["system"].ffill()
    df["system"] = df.groupby("session_id", sort=False)["system"].bfill()
    return df


if __name__ == "__main__":
    from data_loader import DATASET_B_ROOTS, load_events

    ev = annotate(load_events(DATASET_B_ROOTS))
    print(f"\nsystem coverage : {100 * ev['system'].notna().mean():.1f}%")
    print(f"pair coverage   : {100 * ev['pair_ff'].notna().mean():.1f}%")
    print(f"label coverage  : {100 * ev['process_label'].notna().mean():.1f}%")
    print("\n=== events per process label ===")
    print(ev["process_label"].value_counts(dropna=False).to_string())
    print("\n=== window-title system vs URL-port system (cross-check) ===")
    both = ev[ev["system_title"].notna() & ev["system_url"].notna()]
    print(f"n={len(both)}  agree={100 * (both.system_title == both.system_url).mean():.1f}%")
    print("\n=== p_code vs process_label ===")
    sub = ev[ev["p_code"].notna() & ev["process_label"].notna()]
    ct = pd.crosstab(sub["p_code"], sub["process_label"])
    print(ct.to_string())
