"""
Reconstruct the portal's data contract from recorded screen text.

Why this is needed
------------------
Day 4's first task was to verify the submit path against the real systems.
That is not possible: the three portals ran on the client's Windows machines
at `127.0.0.1:5132/5133/5134` during the July 2026 recording and are not
reachable from here (checked — nothing is listening). So the contract has to
be reconstructed from evidence, and the tool built against a mock that honours
it, with the real integration left as an explicit open risk.

The evidence turned out to be far better than Day 3 assumed. `context.
extracted_text` carries **full screen dumps** — 939 of them, 633,859
characters — including list headers, every visible row, and the confirmation
toast after an action. That is enough to recover the record schema, the status
vocabulary, and the state transition for each screen.

The bug that hid this
---------------------
`extracted_text` is a **dict** (`{"text": ..., "source": ..., "char_count":
...}`), not a string. Every `isinstance(x, str)` guard written against it from
Day 1 onwards silently matched nothing, so all 939 dumps were invisible. Day 3
concluded on that basis that the 種別 column "never appears in the event log at
all" and that the invoice discrepancy branch was unpredictable judgement. Both
claims were artefacts of the bug — see `reports/day4_findings.md`.
`data_loader` now exposes a flattened `screen_text` column so the same mistake
cannot recur.

What a dump looks like
----------------------
Newline-separated, in reading order: brand, system name, department, clock,
operator, sidebar entries with pending counts, breadcrumb, screen title, a
count line, the table caption, the column headers, then one line per cell,
then any toast::

    人事 / HR人事給与システム / 2026年度 · 人事部門 / ...
    ダッシュボード / 勤怠・休暇申請 / 勤怠・休暇申請 / 12 件 · 8 件申請中 / 申請一覧
    ID / 社員ID / 氏名 / 申請種別 / 期間・詳細 / 部署 / ステータス
    P2-07047510-001 / E2003 / 上野 大樹 / 半日有給申請 / 2026-07-13 / 経理部 / 承認
    ...
    P2-07047510-004: 申請を承認しました
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent

# Column header rows seen in the dumps, per screen. Detected rather than
# assumed: any line sequence starting with "ID" and ending "ステータス".
HEADER_RE = re.compile(r"^ID\n(.+?\n)?ステータス$", re.M | re.S)

RECORD_ID_RE = re.compile(r"^P\d{1,2}-\d{8}-\d{3}$")
TOAST_RE = re.compile(r"^([A-Z0-9\-]{6,}(?:-\d{3})?)[:：]\s*(.+)$")

# Terminal confirmations, and the status each screen moves a record into.
KNOWN_TOASTS = {
    "申請を承認しました": "承認",
    "登録確定しました": "登録済み",
    "照合完了しました": "完了",
    "処理完了しました": "完了",
    "完了しました": "完了",
}


def _screen_blocks(events: pd.DataFrame) -> list[dict]:
    """One entry per screen dump, with its process label and timestamp."""
    out = []
    for r in events.itertuples():
        t = getattr(r, "screen_text", None)
        if isinstance(t, str) and len(t) > 200:
            out.append({
                "session_id": r.session_id,
                "timestamp_ms": r.timestamp_ms,
                "label": r.process_label,
                "system": r.system,
                "text": t,
            })
    return out


def parse_screen(text: str) -> dict | None:
    """Recover caption, column headers and rows from one dump."""
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    try:
        hdr_start = next(i for i, ln in enumerate(lines) if ln == "ID")
    except StopIteration:
        return None
    try:
        hdr_end = next(i for i in range(hdr_start, len(lines))
                       if lines[i] == "ステータス")
    except StopIteration:
        return None

    columns = lines[hdr_start:hdr_end + 1]
    width = len(columns)
    caption = lines[hdr_start - 1] if hdr_start else None
    title = lines[hdr_start - 3] if hdr_start >= 3 else None

    # Rows are split on record-id boundaries rather than by fixed width.
    # A blank cell (発注管理 leaves 金額 empty) disappears when empty lines
    # are stripped, so a fixed stride desynchronises every subsequent row and
    # silently produced a screen with no statuses at all.
    starts = [i for i in range(hdr_end + 1, len(lines))
              if RECORD_ID_RE.match(lines[i])]
    # The toast follows the table immediately and would otherwise be pulled
    # in as the last row's status cell.
    toast_at = next((i for i in range(hdr_end + 1, len(lines))
                     if TOAST_RE.match(lines[i])), len(lines))
    starts = [i for i in starts if i < toast_at]
    rows = []
    for n, start in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else toast_at
        cells = lines[start:end][:width]
        if len(cells) < width:
            # Short row: a blank cell was dropped. The status is the last
            # cell and the leading cells are positional, so pad in the middle
            # rather than at the end.
            cells = cells[:-1] + [""] * (width - len(cells)) + cells[-1:]
        rows.append(dict(zip(columns, cells)))
    toasts = []
    for ln in lines[toast_at:]:
        m = TOAST_RE.match(ln)
        if m:
            toasts.append({"record_id": m.group(1), "message": m.group(2)})

    return {"title": title, "caption": caption, "columns": columns,
            "rows": rows, "toasts": toasts}


def build_contract(events: pd.DataFrame) -> dict:
    """Per process: column schema, status vocabulary, observed transitions,
    confirmation messages, and the reference data behind each field."""
    per: dict[str, dict] = defaultdict(lambda: {
        "columns": Counter(), "statuses": Counter(), "toasts": Counter(),
        "values": defaultdict(Counter), "record_ids": set(), "screens": 0,
    })
    # record_id -> list of (ts, status) so transitions can be recovered
    history: dict[str, list[tuple[int, str, str]]] = defaultdict(list)

    for blk in _screen_blocks(events):
        parsed = parse_screen(blk["text"])
        if not parsed or not parsed["rows"]:
            continue
        # Key on the screen's own title, not the forward-filled process
        # label. A dump captured moments after a navigation still carries the
        # previous screen's label, which mixed unrelated status vocabularies
        # into a single contract on the first attempt (hr_welfare_application
        # came back titled 契約管理). The title is printed by the screen
        # itself and cannot drift.
        lab = parsed["title"] or blk["label"]
        p = per[lab]
        p["screens"] += 1
        p["columns"][" | ".join(parsed["columns"])] += 1
        p["title"] = parsed["title"]
        for row in parsed["rows"]:
            rid = row.get("ID")
            status = row.get("ステータス")
            p["record_ids"].add(rid)
            # A truncated dump can cut a row mid-way, which shifts the
            # remaining cells and lands a record id in the status column.
            # Those are dropped rather than recorded as statuses.
            if status and not RECORD_ID_RE.match(status):
                p["statuses"][status] += 1
                history[rid].append((blk["timestamp_ms"], status, lab))
            for col, val in row.items():
                if col in ("ID", "ステータス") or not val:
                    continue
                if len(val) < 40:
                    p["values"][col][val] += 1
        for t in parsed["toasts"]:
            p["toasts"][t["message"]] += 1

    transitions: dict[str, Counter] = defaultdict(Counter)
    for rid, hist in history.items():
        hist.sort()
        for (_, a, lab), (_, b, _) in zip(hist, hist[1:]):
            if a != b:
                transitions[lab][f"{a} -> {b}"] += 1

    out = {}
    for lab, p in per.items():
        if not lab or p["screens"] < 2:
            continue
        if lab.startswith("P") and RECORD_ID_RE.match(lab):
            continue
        cols = p["columns"].most_common(1)[0][0].split(" | ")
        out[lab] = {
            "screen_title": p.get("title"),
            "screens_observed": p["screens"],
            "columns": cols,
            "distinct_records": len(p["record_ids"]),
            "statuses": dict(p["statuses"].most_common()),
            "transitions": dict(transitions[lab].most_common()),
            "confirmations": dict(p["toasts"].most_common()),
            "field_values": {
                c: dict(v.most_common(12))
                for c, v in p["values"].items()
                if len(v) <= 30  # enumerable field, not free text/ids
            },
        }
    return out


def main() -> None:
    from data_loader import DATASET_B_ROOTS, load_events
    from process_context import annotate

    ev = annotate(load_events(DATASET_B_ROOTS))
    contract = build_contract(ev)

    out = REPO_ROOT / "portal/contract.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(contract, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print(f"\nreconstructed {len(contract)} screen contracts -> "
          f"{out.relative_to(REPO_ROOT)}")
    for lab, c in sorted(contract.items()):
        print(f"\n### {lab}  ({c['screens_observed']} screens, "
              f"{c['distinct_records']} records)")
        print(f"    title   : {c['screen_title']}")
        print(f"    columns : {' | '.join(c['columns'])}")
        print(f"    statuses: {c['statuses']}")
        if c["transitions"]:
            print(f"    moves   : {c['transitions']}")
        if c["confirmations"]:
            print(f"    confirms: {c['confirmations']}")


if __name__ == "__main__":
    main()
