"""
Step 1 — segment a continuous event stream into individual executions of
business processes.

Model
-----
An *execution* is a contiguous episode of work inside one process context,
where the process context is the (system, route) pair resolved in
`process_context.py`. This matches the shape of the ground-truth schema
described in DATA_SCHEMA.md, which records `process_started` /
`process_switched_out` / `process_suspended` / `process_resumed` — i.e. GT
tracks *process episodes* and treats an interruption as a suspend/resume
pair, not as two unrelated units. So a worker who leaves a process and comes
back produces two episodes of the same label, which is exactly what the
deliverable asks for ("use the same label for the same process").

Why not idle gaps: measured on Day 1 — the 99.9th percentile inter-event gap
is 10.1s and only 7 of 20,477 events exceed 30s, because the README says
waiting time was compressed in the test recording. Idle time carries no
boundary information here.

Why not case IDs as the unit: also measured. The only genuine per-item case
IDs in dataset B are the 72 `INV-2026-nnnn` invoice references, which cover
one process (financial invoice approval) out of thirteen. The
`P<n>-<digits>-<digits>` strings that Day 1 mistook for case IDs are UIA row
names whose numeric body is constant within a session — they identify the
*process*, not the case. Case IDs are therefore used for sub-counting inside
`fin_invoice_approval` (Step 2) rather than as the segmentation unit.

The flicker problem and how it is handled
-----------------------------------------
Raw contiguous runs on (system, route) are badly fragmented: 88% of them
hold <=2 events and 89% last <5s. The cause is tab context, not real work —
`active_browser_tab` reports whichever tab the extension last saw, and 41%
of Edge events carry an "and N more page" title, so the reported route
oscillates between open tabs while the worker stays on one task.

So a run is only promoted to a segment if it shows evidence of actual work:
at least `MIN_SUBSTANTIVE` substantive events (click/keystroke/clipboard/
form input — not screenshots, scrolls or window-state noise) **and** at
least `MIN_DURATION_S` of wall-clock. Runs that fail are absorbed into the
neighbouring segment rather than discarded, so no time goes missing, and
adjacent runs that end up with the same label are then coalesced.

Episodes are then split into per-case **executions** by `executions.py`,
because an episode routinely contains several cases worked back-to-back
without leaving the screen (measured: a median of 3-4 completion markers per
episode, 588 across 162 episodes). The README asks for "individual executions
of business processes", and dataset A's `gt_manifest.json` confirms the
granularity — `executions[]` is "one entry per execution of that process".
Emitting episodes alone under-segments by roughly 3x.

Output is one non-overlapping segment per line, in the schema the README
specifies for `segments.jsonl`.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from executions import completion_markers, split_segment
from process_context import annotate

# Thresholds. Chosen from the measured run-length distribution: genuine
# per-process episodes have a 30-65s median duration, while the tab-flicker
# artefacts cluster at <2s with 1-2 events. Both are deliberately loose so
# that the boundary decision is driven by "was there work here", not by a
# finely-tuned constant.
MIN_SUBSTANTIVE = 3
MIN_DURATION_S = 2.0


def _runs(g: pd.DataFrame) -> list[dict]:
    """Contiguous runs of identical process_label within one session."""
    lab = g["process_label"].fillna("__none__")
    run_id = (lab != lab.shift()).cumsum()
    out = []
    for _, rg in g.groupby(run_id, sort=True):
        out.append({
            "label": rg["process_label"].iloc[0],
            "start_ms": int(rg["timestamp_ms"].iloc[0]),
            "end_ms": int(rg["timestamp_ms"].iloc[-1]),
            "n_events": len(rg),
            "n_substantive": int(rg["is_substantive"].sum()),
            "n_non_process": int(rg["is_non_process"].sum()),
            "p_codes": [c for c in rg["p_code"].dropna().unique()],
            "apps": [a for a in rg["app_name"].dropna().unique()],
        })
    return out


def _is_substantial(r: dict) -> bool:
    if r["label"] is None:
        return False
    dur = (r["end_ms"] - r["start_ms"]) / 1000.0
    return r["n_substantive"] >= MIN_SUBSTANTIVE and dur >= MIN_DURATION_S


def _absorb(runs: list[dict]) -> list[dict]:
    """Absorb insubstantial runs into the nearest substantial neighbour, then
    coalesce adjacent runs sharing a label. Time is conserved: every run's
    span ends up inside exactly one emitted segment."""
    if not runs:
        return []

    keep = [i for i, r in enumerate(runs) if _is_substantial(r)]
    if not keep:
        # Nothing in this session qualifies; fall back to the single longest
        # run so the session is still represented rather than dropped.
        best = max(range(len(runs)), key=lambda i: runs[i]["end_ms"] - runs[i]["start_ms"])
        keep = [best]

    # Assign every run to the nearest kept run (ties -> earlier), so that
    # insubstantial stretches extend whichever segment they sit next to.
    owner: list[int] = []
    for i in range(len(runs)):
        j = min(keep, key=lambda k: (abs(k - i), k))
        owner.append(j)

    merged: list[dict] = []
    for j in keep:
        members = [runs[i] for i in range(len(runs)) if owner[i] == j]
        anchor = runs[j]
        merged.append({
            "label": anchor["label"],
            "start_ms": min(m["start_ms"] for m in members),
            "end_ms": max(m["end_ms"] for m in members),
            "n_events": sum(m["n_events"] for m in members),
            "n_substantive": sum(m["n_substantive"] for m in members),
            "n_non_process": sum(m["n_non_process"] for m in members),
            "p_codes": sorted({c for m in members for c in m["p_codes"]}),
            "apps": sorted({a for m in members for a in m["apps"]}),
        })

    merged.sort(key=lambda r: r["start_ms"])

    # Coalesce neighbours that now carry the same label.
    out = [merged[0]]
    for r in merged[1:]:
        prev = out[-1]
        if r["label"] == prev["label"]:
            prev["end_ms"] = max(prev["end_ms"], r["end_ms"])
            prev["n_events"] += r["n_events"]
            prev["n_substantive"] += r["n_substantive"]
            prev["n_non_process"] += r["n_non_process"]
            prev["p_codes"] = sorted(set(prev["p_codes"]) | set(r["p_codes"]))
            prev["apps"] = sorted(set(prev["apps"]) | set(r["apps"]))
        else:
            out.append(r)
    return out


def segment(events: pd.DataFrame, split_executions: bool = True) -> pd.DataFrame:
    """Segment every session in `events`. Returns one row per segment.

    With `split_executions` (the default) each process episode is further
    split into individual case executions at its completion markers. Pass
    False to get the coarser episode view, which is what the internal
    consistency checks in `evaluate.py` are calibrated against.
    """
    if "process_label" not in events.columns:
        events = annotate(events)

    markers = completion_markers(events) if split_executions else None

    rows = []
    for sid, g in events.groupby("session_id", sort=True):
        g = g.sort_values("timestamp_ms")
        for seg in _absorb(_runs(g)):
            seg["session_id"] = sid
            if markers is not None:
                rows.extend(split_segment(seg, markers))
            else:
                rows.append(seg)

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["duration_s"] = (df["end_ms"] - df["start_ms"]) / 1000.0
    df["start"] = pd.to_datetime(df["start_ms"], unit="ms", utc=True)
    df["end"] = pd.to_datetime(df["end_ms"], unit="ms", utc=True)
    return df.sort_values(["session_id", "start_ms"]).reset_index(drop=True)


def write_segments_jsonl(segs: pd.DataFrame, path: Path) -> None:
    """Write the deliverable: one JSON object per line, exactly the four
    fields the README specifies."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in segs.itertuples():
            f.write(json.dumps({
                "session_id": r.session_id,
                "start": r.start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "end": r.end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "label": r.label,
            }, ensure_ascii=False) + "\n")


def main() -> None:
    from data_loader import DATASET_A_ROOTS, DATASET_B_ROOTS, load_events

    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", choices=["a", "b"], default="b")
    ap.add_argument("--out", default="segments/segments.jsonl")
    ap.add_argument("--episodes-only", action="store_true",
                    help="emit process episodes without splitting into "
                         "per-case executions")
    ap.add_argument("--raw-labels", action="store_true",
                    help="skip the Day 3 correction that relabels an "
                         "execution from its own completion comment")
    args = ap.parse_args()

    roots = DATASET_B_ROOTS if args.dataset == "b" else DATASET_A_ROOTS
    events = annotate(load_events(roots))
    segs = segment(events, split_executions=not args.episodes_only)

    # The completion comment names its own process; a forward-filled screen
    # context does not. Applied by default — it moves 37 of 601 executions,
    # almost all of them comments written in Notepad or Excel where no URL
    # was available to inherit from. See reports/day3_findings.md.
    if not args.raw_labels and "case_comment" in segs.columns:
        from case_parser import template_label
        corrected = [
            template_label(c) if isinstance(c, str) else None
            for c in segs["case_comment"]
        ]
        n = sum(1 for c, old in zip(corrected, segs["label"])
                if c is not None and c != old)
        segs["label"] = [c or old for c, old in zip(corrected, segs["label"])]
        print(f"[segment] labels corrected from completion comment: {n}")

    out = Path(args.out)
    write_segments_jsonl(segs, out)

    print(f"\nsegments: {len(segs)} across {segs.session_id.nunique()} sessions")
    print(f"written to {out}")
    print("\n=== segments per label ===")
    print(segs.groupby("label").agg(
        n=("label", "size"),
        median_s=("duration_s", "median"),
        total_s=("duration_s", "sum"),
    ).round(1).sort_values("total_s", ascending=False).to_string())
    print("\n=== per session ===")
    print(segs.groupby("session_id").agg(
        n_segments=("label", "size"),
        n_labels=("label", "nunique"),
        total_s=("duration_s", "sum"),
    ).to_string())


if __name__ == "__main__":
    main()
