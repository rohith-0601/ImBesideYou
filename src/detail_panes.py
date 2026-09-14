"""
Record detail panes, recovered from the recorded screen text.

Day 4 concluded that `fin_purchase_order_management` — top of the Day 3
ranking — was 0 of 81 automatable, because the order type that decides its
branch is not on the list screen. That conclusion was right about the list and
wrong about the portal.

When an operator opens a record, the portal renders a detail pane, and eight
of those were captured in `context.extracted_text`. They carry the missing
fields outright:

    詳細 — P10-07054374-004
    未確認
    name          沖縄物流センター
    emp_id        V3008
    variant       V1_routine_po
    procedure     発注管理 PO-2026-5097
    target_month  2026-07
    reason        定期発注：電子基板ユニット　数量 176　合計 842,336円　通常

`reason` is not merely *a* missing field. It is the entire body of the
completion comment the operator goes on to write:

    発注管理処理。定期発注：電子基板ユニット　数量 176　合計 842,336円　通常。発注書確認・登録完了。
                  └──────────────── reason, verbatim ─────────────────┘

So the process is draftable after all — from the detail view rather than the
list. What this module establishes is the **contract** for that fetch: which
fields come back, under which names, for which processes. Only 8 panes were
captured, so this does not populate a full mock; it specifies the endpoint a
real integration has to call, with evidence.

Two incidental findings worth recording:

* the DOM leaks an internal variant code (`V1_routine_po`) alongside the
  human-readable text, which is a cleaner key than the Japanese label if the
  endpoint ever exposes it;
* one row carries a `⚠` marker the list view does not explain, which is the
  kind of thing that only surfaces once you look at real records.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT = REPO_ROOT / "portal" / "detail_contract.json"

_HEAD_RE = re.compile(r"詳細\s*[—―-]\s*(P\d{1,2}-\d{6,9}-\d{2,4})([^\n]*)")

# Labels observed inside a detail pane. The portal mixes English DOM keys with
# Japanese labels depending on the screen, so both are matched.
_FIELD_LABELS = {
    "name", "emp_id", "variant", "procedure", "target_month", "reason",
    "管理ID", "社員ID", "氏名", "申請種別", "対象年月", "期間", "詳細",
    "所属部署", "ステータス", "参照書類", "承認コメント", "処理メモ",
    "コメント", "区分", "金額", "種別", "期日",
}


def parse_detail(text: str) -> dict | None:
    """Extract one detail pane from a screen dump, if present."""
    m = _HEAD_RE.search(text)
    if not m:
        return None
    record_id = m.group(1)

    # The pane runs from its header until the list's column row begins again.
    tail = text[m.end():]
    stop = re.search(r"\nID\n社員ID\n", tail)
    body = tail[: stop.start()] if stop else tail

    lines = [l.strip() for l in body.split("\n") if l.strip()]
    fields: dict[str, str] = {}
    i = 0
    # First line after the header is the status, unlabelled.
    if lines and lines[0] not in _FIELD_LABELS:
        fields["ステータス"] = lines[0]
        i = 1
    while i < len(lines) - 1:
        label = lines[i]
        if label in _FIELD_LABELS:
            value = lines[i + 1]
            if value not in _FIELD_LABELS:
                fields.setdefault(label, value)
                i += 2
                continue
        i += 1
    return {"record_id": record_id, "fields": fields}


def harvest_details(events) -> list[dict]:
    from portal_contract import _screen_blocks

    out, seen = [], set()
    for blk in _screen_blocks(events):
        d = parse_detail(blk["text"])
        if not d or d["record_id"] in seen:
            continue
        seen.add(d["record_id"])
        d["timestamp_ms"] = blk["timestamp_ms"]
        d["process_prefix"] = d["record_id"].split("-")[0]
        out.append(d)
    return sorted(out, key=lambda d: d["record_id"])


# Which P-prefix belongs to which process (established on Day 2).
PREFIX_PROCESS = {
    "P1": "hr_expense_settlement", "P2": "hr_leave_application",
    "P3": "hr_onboarding_verification", "P4": "hr_payroll_change",
    "P5": "hr_welfare_application", "P6": "fin_invoice_matching",
    "P7": "fin_payment_processing", "P9": "fin_expense_approval",
    "P10": "fin_purchase_order_management", "P11": "inv_stock_adjustment",
    "P12": "inv_contract_management", "P13": "inv_it_request_processing",
}


def build_contract(details: list[dict]) -> dict:
    """What a per-record fetch must return, per process, with evidence."""
    per: dict[str, dict] = {}
    for d in details:
        process = PREFIX_PROCESS.get(d["process_prefix"])
        if not process:
            continue
        entry = per.setdefault(process, {
            "process": process,
            "panes_observed": 0,
            "fields": Counter(),
            "example": None,
        })
        entry["panes_observed"] += 1
        entry["fields"].update(d["fields"].keys())
        if entry["example"] is None:
            entry["example"] = {"record_id": d["record_id"], **d["fields"]}
    for e in per.values():
        e["fields"] = sorted(e["fields"])
    return per


def main() -> None:
    from data_loader import DATASET_B_ROOTS, load_events
    from process_context import annotate

    ev = annotate(load_events(DATASET_B_ROOTS))
    details = harvest_details(ev)
    contract = build_contract(details)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(
        {"panes_observed": len(details), "per_process": contract,
         "details": details}, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\ndetail panes recovered: {len(details)} -> "
          f"{OUT.relative_to(REPO_ROOT)}")
    print("\n=== per process ===")
    for process, e in sorted(contract.items()):
        print(f"\n{process}  ({e['panes_observed']} pane(s))")
        print(f"    fields: {', '.join(e['fields'])}")
        ex = e["example"]
        for k, v in list(ex.items())[:8]:
            if k != "record_id":
                print(f"      {k:14s} {v[:62]}")


if __name__ == "__main__":
    main()
