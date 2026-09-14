"""
Harvest real portal records out of the recorded screen dumps.

The mock portal the Step 3 tool runs against is not invented data. Every
record below was on a real operator's screen during the July 2026 recording
and was parsed out of `context.extracted_text` by `portal_contract.py`.

Using real records matters for more than realism. The rule logic, the comment
templates and the variant handling all have to cope with the actual
distribution — the amounts that really occur, the categories that really
appear, the proportion of records already completed — and synthetic data would
quietly smooth over exactly the cases that break things.

Records are keyed by their portal ID (`P2-07047510-001`). Where the same ID is
seen in several dumps at different times, the **earliest** observed status is
kept, so the mock starts in the state the operator found it in rather than
the state they left it in. That is what makes the tool's work reproducible:
re-running it re-processes the same pending queue.

Detail panes count as status observations too. `P10-07054374-004` is the case
that forced this: its earliest *list* capture already showed 完了, while the
detail pane caught it at 未確認 a few minutes earlier. Harvesting from list
views alone dropped it out of the pending queue and, with it, the only record
for which a detail fetch could be demonstrated.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT = REPO_ROOT / "portal" / "records.json"

# Screen title -> the process definition that drives it.
SCREEN_TO_PROCESS = {
    "勤怠・休暇申請": "hr_leave_application",
    "経費精算・給与変更": "hr_expense_settlement",
    "発注管理": "fin_purchase_order_management",
    "請求書承認・経費精算": "fin_invoice_matching",
    "契約管理": "inv_contract_management",
}


def harvest(events) -> dict:
    from detail_panes import PREFIX_PROCESS, harvest_details
    from portal_contract import RECORD_ID_RE, parse_screen, _screen_blocks

    # record_id -> (first_seen_ms, row, screen)
    best: dict[str, tuple[int, dict, str]] = {}

    # Statuses seen on detail panes, which can predate the earliest list view.
    detail_status: dict[str, tuple[int, str]] = {}
    for d in harvest_details(events):
        st = d["fields"].get("ステータス")
        if st:
            detail_status[d["record_id"]] = (d["timestamp_ms"], st)
    for blk in _screen_blocks(events):
        parsed = parse_screen(blk["text"])
        if not parsed or not parsed["rows"]:
            continue
        screen = parsed["title"]
        if screen not in SCREEN_TO_PROCESS:
            continue
        for row in parsed["rows"]:
            rid = row.get("ID")
            status = row.get("ステータス")
            if not rid or not RECORD_ID_RE.match(rid):
                continue
            if not status or RECORD_ID_RE.match(status):
                continue
            prev = best.get(rid)
            if prev is None or blk["timestamp_ms"] < prev[0]:
                best[rid] = (blk["timestamp_ms"], row, screen)

    out: dict[str, list[dict]] = {p: [] for p in SCREEN_TO_PROCESS.values()}
    n_from_detail = 0
    for rid, (ts, row, screen) in sorted(best.items()):
        process = SCREEN_TO_PROCESS[screen]
        rec = {k: v for k, v in row.items()}
        rec["_first_seen_ms"] = ts
        # A detail pane observed earlier than the first list row is the better
        # record of where this case started.
        d = detail_status.get(rid)
        if d and d[0] < ts:
            rec["ステータス"] = d[1]
            rec["_first_seen_ms"] = d[0]
            rec["_status_from"] = "detail_pane"
            n_from_detail += 1
        out[process].append(rec)
    if n_from_detail:
        print(f"[harvest] {n_from_detail} record(s) took their starting "
              f"status from a detail pane observed before the first list view")
    for p in out:
        out[p].sort(key=lambda r: r["ID"])
    return out


def main() -> None:
    from data_loader import DATASET_B_ROOTS, load_events
    from process_context import annotate
    from process_defs import DEFINITIONS

    ev = annotate(load_events(DATASET_B_ROOTS))
    records = harvest(ev)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(records, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print(f"\nharvested -> {OUT.relative_to(REPO_ROOT)}")
    for process, recs in records.items():
        defn = DEFINITIONS[process]
        pending = defn["states"]["pending"]
        n_pending = sum(1 for r in recs if r.get("ステータス") == pending)
        statuses = {}
        for r in recs:
            statuses[r.get("ステータス")] = statuses.get(r.get("ステータス"), 0) + 1
        print(f"\n{process}")
        print(f"    records : {len(recs)}")
        print(f"    pending : {n_pending}  (status {pending!r})")
        print(f"    statuses: {statuses}")
        if recs:
            print(f"    sample  : {json.dumps({k: v for k, v in recs[0].items() if not k.startswith('_')}, ensure_ascii=False)}")


if __name__ == "__main__":
    main()
