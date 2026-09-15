"""
Day 6 — how much of the observed work would the tool actually cover?

This is the number a client cares about, and it is easy to inflate. Three
different things get called "coverage" and only the first is measured here:

  1. **Executions the tool would draft.** Measurable exactly: run the drafting
     rules over the real records and count.
  2. **Time saved.** *Not measurable from this data* — see below.
  3. **Headcount.** Not derivable from 3 hours of recording, and not
     attempted.

Why time saved is not measurable
--------------------------------
An execution boundary *is* the completion marker, by construction of the Day 2
segmentation — the median gap from marker to segment end is 0.0s. So the
recorded duration of an execution spans everything the operator did from
opening the record to writing the comment, with no seam between "checking" and
"composing".

Attempts to find that seam from event structure do not survive inspection. The
gap from the first clipboard event to the marker is bimodal — a median of 0.1s
on some processes and 8-15s on others — which reflects whether the operator
copied before or after composing, not how long composing took. And the README
states waiting time was compressed in the recording, so even a clean
decomposition would not transfer to production.

What can honestly be said is a **bound**: the tool removes the composition and
entry of the comment, which is *part* of a median 8-14s execution, and leaves
the reading and checking. Anything more precise would be invented.

So this module reports execution coverage, the share of observed process time
those executions represent, and an explicit account of what is left — and
declines to convert any of it into minutes saved.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
PROCESS_DIR = REPO_ROOT / "portal" / "processes"

_AMOUNT_RE = re.compile(r"([\d,]+)\s*円")


def load_definitions() -> dict:
    out = {}
    for f in sorted(PROCESS_DIR.glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        out[d["label"]] = d
    return out


def classify(ex: pd.DataFrame, defs: dict, records: dict | None = None) -> pd.DataFrame:
    """Per execution, what the tool would do with it and why.

    Applied to the **executions that actually happened**, not to the harvested
    pending queue, so the answer is about observed work rather than about a
    snapshot of whatever happened to be outstanding.

    Each execution is linked back to its portal record, because the field that
    routes an exception is not always the one the comment names. For
    `hr_expense_settlement` the comment's variant is the 費目 (交通費精算,
    出張旅費 …) while the exception turns on 種別 (定常 / 調整), which exists
    only on the record. Classifying from the comment alone reported **zero**
    exceptions for a process that routes 45% of its records to a person.
    """
    from replay import link_records

    linker = link_records(records, defs) if records else None

    rows = []
    for r in ex.itertuples():
        defn = defs.get(r.label_final)
        if defn is None:
            outcome, reason = "not_configured", "process not in scope"
        elif defn.get("variant_source") == "record_detail":
            if defn.get("detail_source"):
                outcome, reason = "needs_fetch", "draftable once the specified fetch exists"
            else:
                outcome, reason = "blocked", "needs a fetch with no known contract"
        else:
            # Exceptions route to a person by design.
            exc_field = defn.get("exception_field")
            exc_vals = defn.get("exception_values") or []
            variant = r.variant if isinstance(r.variant, str) else None
            raw = variant
            if variant and defn.get("variant_map"):
                inv = {v.rstrip("。"): k for k, v in defn["variant_map"].items()}
                raw = inv.get(variant.rstrip("。"), variant)
            # Prefer the record's own value for the exception field.
            rec = linker(r) if linker else None
            exc_value = rec.get(exc_field) if (rec and exc_field) else raw
            if exc_field and exc_value in exc_vals:
                raw = exc_value
                outcome, reason = "exception", f"{exc_field}={raw} routes to a person"
            elif raw and raw not in defn["variants"]:
                outcome, reason = "exception", f"variant {raw!r} not in the definition"
            else:
                outcome, reason = "drafted", "comment drafted from list fields"
        rows.append({
            "process": r.label_final,
            "duration_s": r.duration_s,
            "outcome": outcome,
            "reason": reason,
        })
    return pd.DataFrame(rows)


def summarise(cl: pd.DataFrame) -> pd.DataFrame:
    tot_n, tot_s = len(cl), cl.duration_s.sum()
    g = cl.groupby("outcome").agg(
        executions=("outcome", "size"),
        total_s=("duration_s", "sum"),
    ).reset_index()
    g["share_of_executions"] = (g.executions / tot_n).round(3)
    g["share_of_time"] = (g.total_s / tot_s).round(3)
    order = {"drafted": 0, "exception": 1, "needs_fetch": 2, "blocked": 3,
             "not_configured": 4}
    return g.assign(_o=g.outcome.map(order)).sort_values("_o").drop(columns="_o")


def main() -> None:
    from analyze_day3 import build_executions
    from data_loader import DATASET_B_ROOTS, load_events
    from process_context import annotate
    from segment import segment

    ev = annotate(load_events(DATASET_B_ROOTS))
    ex = build_executions(ev, segment(ev))
    defs = load_definitions()
    records = json.loads(
        (REPO_ROOT / "portal" / "records.json").read_text(encoding="utf-8"))
    cl = classify(ex, defs, records)
    s = summarise(cl)

    print(f"\nexecutions observed: {len(cl)}   "
          f"total attributed time: {cl.duration_s.sum():.0f}s")
    print("\n=== what the tool would do with the work that actually happened ===")
    print(s.to_string(index=False))

    scoped = cl[cl.outcome != "not_configured"]
    drafted = cl[cl.outcome == "drafted"]
    print(f"\nin-scope executions          : {len(scoped)} "
          f"({len(scoped) / len(cl):.0%} of all observed work)")
    print(f"drafted by the tool          : {len(drafted)} "
          f"({len(drafted) / len(scoped):.0%} of in-scope, "
          f"{len(drafted) / len(cl):.0%} of all)")
    print(f"  their share of in-scope time: "
          f"{drafted.duration_s.sum() / scoped.duration_s.sum():.0%}")

    print("\n=== per configured process ===")
    per = (cl[cl.process.isin(defs)]
           .groupby(["process", "outcome"]).size().unstack(fill_value=0))
    print(per.to_string())

    print("\n=== what remains a person's job ===")
    for outcome in ("exception", "needs_fetch", "blocked"):
        part = cl[cl.outcome == outcome]
        if part.empty:
            continue
        print(f"\n{outcome}: {len(part)} executions, {part.duration_s.sum():.0f}s")
        for reason, g in part.groupby("reason"):
            print(f"    {len(g):3d}  {reason}")


if __name__ == "__main__":
    main()
