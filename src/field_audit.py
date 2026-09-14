"""
Can the tool see what it needs to decide?

Day 4 built the prototype and found that `fin_purchase_order_management` —
the top-ranked candidate from Day 3 — is **0 of 81 automatable**, because the
field that decides its branch (the order type: 年間契約 / スポット発注 /
定期発注 / 緊急発注) is not on the list screen the tool reads. It appears only
in the completion comment, i.e. after a human has opened the record.

That is a gap in the Day 3 scoring model, not just in one process. The score
weighed volume, time, determinism, integration surface and branch count — but
never asked whether the *deciding field is visible on the screen the tool
reads*. A process can score well on every other axis and still be
un-automatable for this reason alone.

What the check has to compare
-----------------------------
The first version of this module compared each process's *variant* values
against the list columns, and got two processes wrong, because "the variant"
and "the field that decides" are not always the same thing:

* `fin_invoice_matching`'s variants are 差異なし承認 / 差異あり要確認 — the
  **outcome**, not an input. Its predictor is the 種別 column (定常 / 調整),
  which *is* on the list. Comparing outcomes against columns reported it
  `detail_only`, which is wrong.
* `inv_stock_adjustment` matched at 0.55 against 氏名, because its variant
  regex returns a product name for portal-form records and a 区分 code for
  Notepad-memo ones. Both are visible columns; the partial score was an
  artefact of the regex, not a real gap.

So the check is per **comment slot** instead. A process is automatable from
the list exactly when every slot its completion template needs can be filled
from a list row — which is precisely the condition `server/assist.js` applies
when it decides whether to draft. Grounding the audit in the same condition
the tool uses keeps the two from disagreeing.

Outcomes per slot:

  visible      resolvable from a list column
  detail_only  exists in the completion comments but never on the list screen
  derived      computed rather than read (e.g. the amount, already numeric)

Day 5 addendum: "needs the record opened" is not the same as "cannot be
automated", and the first version of this module blurred them. When an
operator opens a record the portal renders a detail pane, and eight of those
were captured in the screen text. For `fin_purchase_order_management` the pane
carries a `reason` field that is the entire body of the completion comment, so
one fetch turns a process scored 0-of-81 into a string substitution. The
audit now reports whether a process's fetch contract is **specified** (a
`detail_source` block backed by an observed pane) or still **unknown**.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACT = REPO_ROOT / "portal" / "contract.json"
PROCESS_DIR = REPO_ROOT / "portal" / "processes"

# Process -> the list screen it is worked on. Two processes share one screen
# (Day 3 §2), which the mapping preserves.
PROCESS_SCREEN = {
    "fin_invoice_matching": "請求書承認・経費精算",
    "fin_expense_approval": "経費承認（管理職）",
    "fin_payment_processing": "支払処理",
    "fin_purchase_order_management": "発注管理",
    "fin_budget_variance_analysis": "予算差異分析",
    "hr_leave_application": "勤怠・休暇申請",
    "hr_onboarding_verification": "入社手続き",
    "hr_welfare_application": "福利厚生申請",
    "hr_payroll_change": "経費精算・給与変更",
    "hr_expense_settlement": "経費精算・給与変更",
    "inv_contract_management": "契約管理",
    "inv_it_request_processing": "IT申請",
    "inv_stock_adjustment": "在庫管理",
}


# The slots each process's completion template needs, and where each is
# resolvable from. A slot maps to a list column, or to "detail" when the value
# only ever appears in the completion comment, or "derived" when it is
# computed from a column rather than read off one.
#
# Taken from case_parser.TEMPLATES and checked against the columns recovered
# in portal/contract.json.
SLOT_SOURCES: dict[str, dict[str, str]] = {
    "hr_leave_application":          {"variant": "申請種別", "date": "期間・詳細"},
    "hr_expense_settlement":         {"variant": "区分", "amount": "金額"},
    "hr_payroll_change":             {"variant": "区分", "date": "detail"},
    "fin_invoice_matching":          {"case": "区分", "amount": "金額",
                                      "decision": "種別"},
    "fin_expense_approval":          {"variant": "申請種別", "amount": "detail"},
    "fin_payment_processing":        {"amount": "detail", "variant": "detail"},
    "fin_purchase_order_management": {"variant": "detail", "item": "detail",
                                      "qty": "detail", "amount": "detail",
                                      "urgency": "detail"},
    "fin_budget_variance_analysis":  {"variant": "氏名", "detail": "詳細"},
    "hr_onboarding_verification":    {"variant": "detail"},
    "hr_welfare_application":        {"variant": "申請種別", "target": "詳細"},
    "inv_contract_management":       {"variant": "申請種別", "date": "期間・詳細"},
    "inv_it_request_processing":     {"variant": "申請種別",
                                      "applicant": "detail"},
    "inv_stock_adjustment":          {"variant": "区分", "item": "氏名",
                                      "qty": "detail"},
}


def fetch_status(process: str) -> str:
    """Is the per-record fetch this process needs actually specified?

    A process that needs the record opened is only blocked while nobody knows
    what opening it returns. Where a detail pane was captured, the contract is
    written into the process definition and the work becomes an integration
    task with a known shape.
    """
    f = PROCESS_DIR / f"{process}.json"
    if not f.exists():
        return "not configured"
    d = json.loads(f.read_text(encoding="utf-8"))
    if d.get("variant_source") != "record_detail":
        return "not needed"
    ds = d.get("detail_source")
    return "specified" if ds else "unknown"


def audit(ex: pd.DataFrame, contract: dict) -> pd.DataFrame:
    """One row per process: can every comment slot be filled from a list row?"""
    rows = []
    for process, screen in PROCESS_SCREEN.items():
        g = ex[ex.label_final == process]
        c = contract.get(screen) or {}
        columns = set(c.get("columns", []))
        slots = SLOT_SOURCES.get(process, {})

        visible, detail = [], []
        for slot, source in slots.items():
            if source == "detail":
                detail.append(slot)
            elif source in columns:
                visible.append(slot)
            else:
                # Named a column that this screen does not have — a mapping
                # error rather than a data finding, so surface it loudly.
                detail.append(f"{slot}(!{source})")

        if not slots:
            verdict = "no_template"
        elif not detail:
            verdict = "list_sufficient"
        elif len(detail) == len(slots):
            verdict = "detail_required"
        else:
            verdict = "partial"

        rows.append({
            "process": process,
            "screen": screen,
            "executions": len(g),
            "slots": len(slots),
            "from_list": ",".join(visible) or "—",
            "needs_detail": ",".join(detail) or "—",
            "verdict": verdict,
            "fetch": fetch_status(process),
        })
    order = {"list_sufficient": 0, "partial": 1, "detail_required": 2,
             "no_template": 3}
    df = pd.DataFrame(rows)
    return (df.assign(_o=df.verdict.map(order))
              .sort_values(["_o", "executions"], ascending=[True, False])
              .drop(columns="_o").reset_index(drop=True))


def field_is_an_input(events, screen: str, field: str) -> dict:
    """Is `field` known before the work, or set by it?

    A field that perfectly predicts an outcome is only useful if it exists
    *before* someone does the work. Otherwise it is a record of the decision,
    not a basis for it, and automating against it is circular.

    Two tests, both from the recorded screens:
      1. is the field populated on rows still in the pending state?
      2. does a record's value ever change between observations?
    """
    from portal_contract import RECORD_ID_RE, _screen_blocks, parse_screen

    rows = []
    for blk in _screen_blocks(events):
        parsed = parse_screen(blk["text"])
        if not parsed or parsed.get("title") != screen:
            continue
        for r in parsed["rows"]:
            if not RECORD_ID_RE.match(r.get("ID", "")):
                continue
            rows.append({"id": r["ID"], "ts": blk["timestamp_ms"],
                         "value": r.get(field), "status": r.get("ステータス")})
    df = pd.DataFrame(rows)
    if df.empty:
        return {"screen": screen, "field": field, "verdict": "not observed"}

    by_status = df.dropna(subset=["value"]).groupby("status").value.count().to_dict()
    changed = sum(1 for _, g in df.groupby("id")
                  if g.value.dropna().nunique() > 1)
    repeated = sum(1 for _, g in df.groupby("id") if len(g) > 1)
    pending_populated = sum(v for k, v in by_status.items()
                            if k in ("未処理", "申請中", "処理待ち", "未確認", "照合中"))
    return {
        "screen": screen,
        "field": field,
        "observations": len(df),
        "populated_on_pending": pending_populated,
        "records_seen_twice": repeated,
        "records_whose_value_changed": changed,
        "verdict": ("input — known before the work"
                    if pending_populated and changed == 0
                    else "output — set by the work"),
    }


def main() -> None:
    from analyze_day3 import build_executions
    from data_loader import DATASET_B_ROOTS, load_events
    from process_context import annotate
    from segment import segment

    ev = annotate(load_events(DATASET_B_ROOTS))
    ex = build_executions(ev, segment(ev))
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))

    a = audit(ex, contract)
    print("\n=== can the tool see the field it needs to decide? ===")
    print(a.to_string(index=False))

    print("\n=== summary ===")
    for verdict, g in a.groupby("verdict"):
        print(f"{verdict:20s} {len(g):2d} processes, "
              f"{g.executions.sum():4d} executions")

    ok = a[a.verdict == "list_sufficient"]
    blocked = a[a.verdict.isin(["detail_required", "partial"])]
    tot = a.executions.sum()
    print(f"\ndraftable from the list alone : {ok.executions.sum():4d} "
          f"({100 * ok.executions.sum() / tot:.0f}%)")
    print(f"needs a per-record fetch      : {blocked.executions.sum():4d} "
          f"({100 * blocked.executions.sum() / tot:.0f}%)")
    full = a[a.verdict == "detail_required"]
    if len(full):
        print("\nevery slot needs the record opened:")
        for r in full.itertuples():
            print(f"    {r.process:32s} fetch contract: {r.fetch}")
        spec = full[full.fetch == "specified"]
        if len(spec):
            print(f"\n{spec.executions.sum()} of those "
                  f"{full.executions.sum()} executions are on a process whose "
                  f"fetch contract is specified — an integration task with a "
                  f"known shape, not a blocked process.")

    print("\n=== is the deciding field an input or an output? ===")
    for screen, field in [("請求書承認・経費精算", "種別"),
                          ("経費精算・給与変更", "種別"),
                          ("在庫管理", "種別")]:
        r = field_is_an_input(ev, screen, field)
        print(f"{screen} / {field}: {r['verdict']}")
        print(f"    populated on pending rows: {r.get('populated_on_pending')}, "
              f"changed in {r.get('records_whose_value_changed')} of "
              f"{r.get('records_seen_twice')} records seen twice")


if __name__ == "__main__":
    main()
