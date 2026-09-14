"""
Day 5 — rebuild the automation ranking with the two components Day 4 proved
were wrong.

Day 3 scored:

    opportunity = (volume + time_share)/2 x determinism x data_access
                  ----------------------------------------------------
                                    branch_cost

Day 4 found two faults, both by building the thing and watching it fail:

1. **`data_access` measured the wrong subject.** It was the share of
   executions that stayed inside the browser — i.e. how the *human* did the
   work. For `fin_invoice_matching` that share is 25%, because the operator
   detoured through Excel and Word to perform the check. But the outcome is
   already determined by a field on the record, so that detour is precisely
   the work the tool removes. Penalising a process for the manual effort you
   intend to delete is backwards.

2. **Field visibility was missing entirely.** Nothing asked whether the field
   that decides the branch is on the screen the tool reads.
   `fin_purchase_order_management` ranked **first** and is **0 of 81**
   automatable for exactly this reason.

So `data_access` is replaced by `draftable`, measured by `field_audit.py`:
the share of a process's completion-comment slots that resolve from a list
row. That is the condition `server/assist.js` actually applies, so the score
and the tool now answer the same question.

`determinism` keeps the Day 3 meaning — judgement exceptions cost, predictable
ones do not — with one correction carried from Day 4: `fin_invoice_matching`'s
exceptions are predictable, not judgement, because 種別 decides them and is
set before the work begins.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACT = REPO_ROOT / "portal" / "contract.json"

# Corrected on Day 4 §4/§10: 種別 predicts fin_invoice_matching's outcome
# 64/64 and is an input, so its exceptions are predictable rather than
# judgement. No process in dataset B is left with genuine judgement
# exceptions — which is itself worth stating in the report.
EXCEPTION_NATURE = {
    "fin_purchase_order_management": "predictable",   # 緊急発注
    "fin_invoice_matching": "predictable",            # 種別 = 調整
    "hr_expense_settlement": "predictable",           # 種別 = 調整
    "inv_stock_adjustment": "predictable",            # 種別 = 調整
}


def draftable_share(audit: pd.DataFrame) -> dict[str, float]:
    """Share of each process's comment slots that resolve from a list row."""
    out = {}
    for r in audit.itertuples():
        if not r.slots:
            out[r.process] = 0.0
            continue
        from_list = 0 if r.from_list == "—" else len(r.from_list.split(","))
        out[r.process] = round(from_list / r.slots, 3)
    return out


def rescore(stats: pd.DataFrame, audit: pd.DataFrame) -> pd.DataFrame:
    df = stats.copy()
    draft = draftable_share(audit)
    df["draftable"] = df.label_final.map(draft).fillna(0.0)
    df["exception_nature"] = df.label_final.map(EXCEPTION_NATURE).fillna("none")

    def norm(s):
        rng = s.max() - s.min()
        return (s - s.min()) / rng if rng else pd.Series(1.0, index=s.index)

    df["volume"] = norm(df.executions)
    df["time_share"] = norm(df.total_s)
    df["determinism"] = 1 - df.exception_rate.where(
        df.exception_nature == "judgement", 0.0)
    df["branch_cost"] = 1 + norm(df.variants)

    # Floor at 0.05 rather than 0: a fully blocked process is not worthless,
    # it is worth one integration away.
    df["access"] = df.draftable.clip(lower=0.05)

    df["opportunity"] = (
        (df.volume + df.time_share) / 2
        * df.determinism
        * df.access
        / df.branch_cost
    ).round(3)
    return df.sort_values("opportunity", ascending=False).reset_index(drop=True)


def main() -> None:
    from analyze_day3 import build_executions, per_process, score, app_surface, systems_per_process
    from data_loader import DATASET_B_ROOTS, load_events
    from field_audit import audit as run_audit
    from process_context import annotate
    from segment import segment

    ev = annotate(load_events(DATASET_B_ROOTS))
    ex = build_executions(ev, segment(ev))
    stats = per_process(ex)
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    a = run_audit(ex, contract)

    old = score(stats, systems_per_process(ev, ex), app_surface(ev, ex))
    new = rescore(stats, a)

    old_rank = {r.label_final: i + 1 for i, r in enumerate(old.itertuples())}
    new_rank = {r.label_final: i + 1 for i, r in enumerate(new.itertuples())}

    real = new[new.executions >= 5]
    print("\n=== corrected ranking ===")
    print("| # | process | exec | total s | draftable | determinism | opportunity | was |")
    for i, r in enumerate(real.itertuples(), 1):
        was = old_rank.get(r.label_final, "-")
        move = "" if was == i else f"  ({'↑' if isinstance(was, int) and was > i else '↓'}{abs(was - i) if isinstance(was, int) else ''})"
        print(f"{i:2d}  {r.label_final:32s} {r.executions:4d} {r.total_s:8.0f} "
              f"{r.draftable:9.2f} {r.determinism:11.3f} {r.opportunity:11.3f}"
              f"   was #{was}{move}")

    print("\n=== biggest moves ===")
    moves = []
    for lab in new_rank:
        if lab in old_rank:
            moves.append((lab, old_rank[lab], new_rank[lab], old_rank[lab] - new_rank[lab]))
    moves.sort(key=lambda m: -abs(m[3]))
    for lab, o, n, d in moves[:5]:
        if d:
            print(f"  {lab:32s} #{o} -> #{n}  ({'+' if d > 0 else ''}{d})")

    print("\n=== exception nature after the Day 4 correction ===")
    print(new.groupby("exception_nature").agg(
        processes=("label_final", "size"),
        executions=("executions", "sum")).to_string())


if __name__ == "__main__":
    main()
