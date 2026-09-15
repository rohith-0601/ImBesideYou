"""
Replay the tool against the work that actually happened.

Every evaluation so far has been structural — does the segmentation tile the
session, does the label agree with an independent process code, can a comment
slot be filled. None of it answers the question a client would ask first:

    if this tool had been running during those 15 sessions,
    what would it have done, and would it have been right?

That question is answerable here in a way Step 1's accuracy never was,
because the operators left their answers behind. Each of the 601 recovered
executions ends with the completion comment its worker wrote. The tool drafts
a comment from the same record. So the two can be compared directly, character
for character.

This is the only place in the project with a **verifiable accuracy number**
rather than an internal consistency check. `gt.jsonl` never arrived, so
boundary accuracy stays unmeasured — but comment accuracy does not have to.

Outcomes per execution:

  exact          the drafted comment matches what the operator wrote
  exact_in_memo  the operator wrote the same sentence inside a Notepad memo,
                 wrapped in a header and the record ID
  mismatch       the tool drafted, and drafted something different
  no_draft       the tool declined (blocked slot, or a flagged exception)

A `no_draft` is not a failure. Declining to draft a 調整 invoice is the
designed behaviour; it just means that case still costs an operator the time
it costs today.

`exact_in_memo` is counted as correct, and the reason is worth stating rather
than assuming. Some operators write the completion text into Notepad first, in
the shape `精算確認メモ / P1-07109774-002 / 経費精算確認済み。費目：…`. The
business sentence inside is identical to the portal one; the header and ID are
scratch-pad scaffolding for the operator's own benefit. Counting those as
failures would have reported 0% accuracy on a tool whose output was character-
for-character right, which is exactly what the first run of this module did.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
PROCESS_DIR = REPO_ROOT / "portal" / "processes"

_AMOUNT_RE = re.compile(r"([\d,]+)\s*円")
_CASE_RE = re.compile(r"(INV-\d{4}-\d+|PO-\d{4}-\d+)")


def load_definitions() -> dict:
    out = {}
    for f in sorted(PROCESS_DIR.glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        out[d["label"]] = d
    return out


def _norm(s: str) -> str:
    """Compare on content, not whitespace.

    The recorded comments use ideographic spaces (U+3000) where the template
    does, and Notepad-written ones carry stray carriage returns. Neither is a
    difference the operator would notice, so normalising both sides keeps the
    metric honest in the strict direction — it does not let a wrong value pass.
    """
    s = unicodedata.normalize("NFKC", s)
    return re.sub(r"\s+", "", s)


# Notepad memo wrappers seen in the data: a header ending in メモ, then the
# record ID, then the same sentence the portal form would carry.
_MEMO_RE = re.compile(r"^.{0,12}メモ[\s\r]*(?:P\d{1,2}-\d{6,9}-\d{2,4})?[\s\r]*")


def strip_memo(text: str) -> str:
    return _MEMO_RE.sub("", text.strip())


def draft_for(defn: dict, rec: dict) -> tuple[str | None, list[str]]:
    """Mirror of server/assist.js draftComment, for replay in Python."""
    blockers: list[str] = []

    raw_variant = rec.get(defn["variant_field"]) if defn.get("variant_field") else None
    if raw_variant is None and defn.get("variant_source") == "record_detail":
        blockers.append("variant not on the list screen")
    elif raw_variant and raw_variant not in defn["variants"]:
        blockers.append(f"unknown variant {raw_variant!r}")

    exc_field = defn.get("exception_field")
    if exc_field and rec.get(exc_field) in (defn.get("exception_values") or []):
        blockers.append(f"{exc_field}={rec.get(exc_field)!r} is a flagged exception")

    variant = raw_variant
    if variant and defn.get("variant_map"):
        variant = defn["variant_map"].get(variant, variant)

    amount = None
    m = _AMOUNT_RE.search(rec.get("金額") or "")
    if m:
        amount = f"{int(m.group(1).replace(',', '')):,}"

    case = None
    for v in rec.values():
        if isinstance(v, str):
            cm = _CASE_RE.search(v)
            if cm:
                case = cm.group(1)
                break

    values = {
        "variant": variant,
        "amount": amount,
        "date": rec.get("期間・詳細") or rec.get("対象年月"),
        "item": rec.get("項目"),
        "case": case,
        "qty": None,
        "urgency": None,
    }
    tpl = defn["comment_template"]
    slots = re.findall(r"\{(\w+)\}", tpl)
    missing = [s for s in slots if not values.get(s)]
    if missing:
        blockers.append(f"unresolved slots: {', '.join(missing)}")
    if blockers:
        return None, blockers
    return tpl.format(**{s: values[s] for s in slots}), []


def link_records(records: dict, definitions: dict):
    """Build a function mapping one execution row to its portal record.

    Exposed because `coverage.py` needs the same linkage: the field that routes
    an exception often lives on the record rather than in the comment.
    """
    by_id: dict[str, dict] = {}
    by_key: dict[tuple, dict] = {}
    for process, recs in records.items():
        defn = definitions.get(process)
        vf = defn.get("variant_field") if defn else None
        for r in recs:
            by_id[r["ID"]] = r
            amt = _AMOUNT_RE.search(r.get("金額") or "")
            key = (
                process,
                r.get(vf) if vf else None,
                int(amt.group(1).replace(",", "")) if amt else None,
                r.get("期間・詳細") or r.get("対象年月"),
            )
            by_key.setdefault(key, r)

    def link(row) -> dict | None:
        if isinstance(getattr(row, "case_ref", None), str) and row.case_ref in by_id:
            return by_id[row.case_ref]
        defn = definitions.get(row.label_final)
        if defn is None:
            return None
        amount = row.amount_yen if pd.notna(row.amount_yen) else None
        variant = row.variant if isinstance(row.variant, str) else None
        if variant and defn.get("variant_map"):
            inv_map = {v.rstrip("。"): k for k, v in defn["variant_map"].items()}
            variant = inv_map.get(variant.rstrip("。"), variant)
        date = row.effective_date if isinstance(row.effective_date, str) else None
        return by_key.get(
            (row.label_final, variant, int(amount) if amount else None, date)
        )

    return link


def replay(ex: pd.DataFrame, records: dict, definitions: dict) -> pd.DataFrame:
    """One row per real execution: what the tool would have produced."""
    # Index the harvested records two ways. Most completion comments name the
    # case only in prose, so an ID lookup alone linked 17 of 601 executions.
    # The second index matches on (process, variant, amount), which is what
    # actually identifies a row on these screens.
    by_id: dict[str, dict] = {}
    by_key: dict[tuple, dict] = {}
    for process, recs in records.items():
        defn = definitions.get(process)
        vf = defn.get("variant_field") if defn else None
        for r in recs:
            by_id[r["ID"]] = r
            amt = _AMOUNT_RE.search(r.get("金額") or "")
            key = (
                process,
                r.get(vf) if vf else None,
                int(amt.group(1).replace(",", "")) if amt else None,
                r.get("期間・詳細") or r.get("対象年月"),
            )
            by_key.setdefault(key, r)

    def link(row) -> dict | None:
        if isinstance(row.case_ref, str) and row.case_ref in by_id:
            return by_id[row.case_ref]
        defn = definitions.get(row.label_final)
        if defn is None:
            return None
        # Rebuild the key from what the operator's own comment says.
        amount = row.amount_yen if pd.notna(row.amount_yen) else None
        variant = row.variant if isinstance(row.variant, str) else None
        # variant_map is record-value -> comment-phrase, so reverse it. The
        # phrases carry a trailing 。 that the parsed variant does not, so
        # both sides are stripped before matching - without that, every
        # invoice execution failed to link.
        if variant and defn.get("variant_map"):
            inv_map = {v.rstrip("。"): k for k, v in defn["variant_map"].items()}
            variant = inv_map.get(variant.rstrip("。"), variant)
        date = row.effective_date if isinstance(row.effective_date, str) else None
        return by_key.get(
            (row.label_final, variant, int(amount) if amount else None, date)
        )

    rows = []
    for r in ex.itertuples():
        process = r.label_final
        defn = definitions.get(process)
        actual = r.case_comment if isinstance(r.case_comment, str) else None
        rec = link(r)

        # An execution is replayable when we hold the portal record it worked
        # on. Comments that carry no portal ID (most processes reference the
        # case only in prose) cannot be matched to a row and are reported
        # separately rather than counted as failures.
        if defn is None:
            outcome, drafted, why = "not_configured", None, []
        elif rec is None:
            # A process the tool cannot draft from the list at all has nothing
            # to link against - report it as declined rather than as a gap in
            # the replay, which is what it actually is.
            if defn.get("variant_source") == "record_detail":
                outcome, drafted, why = "no_draft", None, ["variant not on the list screen"]
            else:
                outcome, drafted, why = "record_not_linked", None, []
        else:
            drafted, why = draft_for(defn, rec)
            if drafted is None:
                outcome = "no_draft"
            elif not actual:
                outcome = "no_actual"
            elif _norm(drafted) == _norm(actual):
                outcome = "exact"
            elif _norm(drafted) == _norm(strip_memo(actual)):
                outcome = "exact_in_memo"
            else:
                outcome = "mismatch"

        rows.append({
            "process": process,
            "record_id": r.case_ref,
            "outcome": outcome,
            "drafted": drafted,
            "actual": actual,
            "why": "; ".join(why),
            "duration_s": r.duration_s,
        })
    return pd.DataFrame(rows)


definitions_labels: set[str] = set()


def main() -> None:
    from analyze_day3 import build_executions
    from data_loader import DATASET_B_ROOTS, load_events
    from process_context import annotate
    from segment import segment

    ev = annotate(load_events(DATASET_B_ROOTS))
    ex = build_executions(ev, segment(ev))
    records = json.loads((REPO_ROOT / "portal" / "records.json").read_text("utf-8"))
    defs = load_definitions()

    rp = replay(ex, records, defs)
    global definitions_labels
    definitions_labels = set(defs)

    print(f"\nexecutions replayed: {len(rp)}")
    print("\n=== outcome ===")
    print(rp.outcome.value_counts().to_string())

    judged = rp[rp.outcome.isin(["exact", "exact_in_memo", "mismatch"])]
    if len(judged):
        ok = judged.outcome.isin(["exact", "exact_in_memo"]).sum()
        print(f"\ncomment accuracy where the tool drafted: "
              f"{ok}/{len(judged)} = {ok / len(judged):.1%}")
        linked = rp[~rp.outcome.isin(["not_configured", "record_not_linked"])]
        conf_total = rp[rp.process.isin(definitions_labels)].shape[0]
        print(f"executions linked to a portal record: {len(linked)} of "
              f"{conf_total} on configured processes")

    print("\n=== per configured process ===")
    conf = rp[rp.process.isin(defs)]
    tbl = conf.groupby("process").outcome.value_counts().unstack(fill_value=0)
    print(tbl.to_string())

    mism = rp[rp.outcome == "mismatch"]
    if len(mism):
        print(f"\n=== mismatches ({len(mism)}) ===")
        for m in mism.head(6).itertuples():
            print(f"\n  {m.record_id} [{m.process}]")
            print(f"    tool  : {m.drafted}")
            print(f"    actual: {m.actual}")


if __name__ == "__main__":
    main()
