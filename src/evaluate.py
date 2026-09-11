"""
Evaluation for Step 1 without ground truth.

Dataset A's `gt.jsonl` never arrived (see reports/day1_findings.md), so
boundary accuracy cannot be measured against truth. This module substitutes
four *internal* checks. They are weaker evidence than a measured F1 and are
reported as such, but each one can fail, which is what makes them worth
running.

1. `check_tiling` — do segments tile their session without overlap, and how
   much of each session's wall-clock is covered? Catches the Day 1 failure
   mode directly: naive case spans summed to 1.45-3.32x session wall-clock.

2. `check_pcode_purity` — the portal stamps a process code `P<n>` into
   clicked UIA row names, produced independently of the URL the label comes
   from. Within a segment, do all observed `p_code`s agree with the label?
   This is the closest thing to an external check available.

3. `check_boundary_alignment` — a true process switch should coincide with
   the worker actually navigating. What fraction of segment boundaries sit
   within `window_s` of a `browser_navigation` or `app_switch` event?

4. `check_label_stability` — the deliverable requires the same process to
   always get the same label. Verifies each label maps to exactly one
   (system, route) pair and reports the business vocabulary behind it, so a
   human can confirm the label means one thing.

`score_against_gt` is written but unused: if dataset A's JSON parts turn up,
it computes boundary precision/recall directly, so the harness does not need
rewriting.
"""

from __future__ import annotations

import pandas as pd

TOLERANCE_S = 5.0


def check_tiling(segs: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    """Per session: overlap between segments, and coverage of wall-clock."""
    rows = []
    for sid, g in segs.groupby("session_id"):
        g = g.sort_values("start_ms")
        overlap_ms = 0
        prev_end = None
        for r in g.itertuples():
            if prev_end is not None and r.start_ms < prev_end:
                overlap_ms += prev_end - r.start_ms
            prev_end = max(prev_end or 0, r.end_ms)
        ses = events[events.session_id == sid]
        wall = ses.timestamp_ms.max() - ses.timestamp_ms.min()
        covered = (g.end_ms - g.start_ms).sum()
        rows.append({
            "session_id": sid,
            "n_segments": len(g),
            "wall_s": round(wall / 1000, 1),
            "covered_s": round(covered / 1000, 1),
            "coverage_pct": round(100 * covered / wall, 1) if wall else 0.0,
            "overlap_s": round(overlap_ms / 1000, 3),
        })
    return pd.DataFrame(rows)


def check_pcode_purity(segs: pd.DataFrame, events: pd.DataFrame,
                       label_to_pcode: dict[str, str] | None = None) -> dict:
    """Do the p_codes seen inside a segment agree with the segment's label?

    Builds the label->p_code mapping from the global majority, then measures
    per-segment agreement. A segment with no p_code evidence is not counted.
    """
    # Exclude `*_unresolved` labels: they come from the one session with no
    # L3 events, where no route is knowable, so a majority p_code for them is
    # meaningless. They are reported separately instead of scored here.
    ev = events[events.p_code.notna() & events.process_label.notna()
                & ~events.process_label.str.endswith("_unresolved")]
    if label_to_pcode is None:
        label_to_pcode = (
            ev.groupby("process_label").p_code
              .agg(lambda s: s.value_counts().index[0])
              .to_dict()
        )

    n_with, n_pure, mismatches, n_unresolved = 0, 0, [], 0
    for r in segs.itertuples():
        codes = [c for c in (r.p_codes or [])]
        if not codes:
            continue
        if str(r.label).endswith("_unresolved"):
            n_unresolved += 1
            continue
        n_with += 1
        expected = label_to_pcode.get(r.label)
        if expected is not None and set(codes) == {expected}:
            n_pure += 1
        else:
            mismatches.append({
                "session_id": r.session_id, "label": r.label,
                "expected": expected, "observed": codes,
                "duration_s": round(r.duration_s, 1),
            })
    return {
        "label_to_pcode": label_to_pcode,
        "segments_with_pcode": n_with,
        "segments_pure": n_pure,
        "purity_pct": round(100 * n_pure / n_with, 1) if n_with else None,
        "segments_unresolved_excluded": n_unresolved,
        "mismatches": mismatches,
    }


def check_boundary_alignment(segs: pd.DataFrame, events: pd.DataFrame,
                             window_s: float = TOLERANCE_S) -> dict:
    """Fraction of segment starts that sit within `window_s` of a real
    navigation or app switch. A boundary invented by the algorithm rather
    than by the worker would show up here as a miss."""
    sw = events[events.event_type.isin(["browser_navigation", "app_switch"])]
    by_ses = {sid: g.timestamp_ms.to_numpy() for sid, g in sw.groupby("session_id")}

    total, aligned = 0, 0
    for sid, g in segs.groupby("session_id"):
        ts = by_ses.get(sid)
        starts = g.sort_values("start_ms").start_ms.to_numpy()[1:]  # skip session open
        for s in starts:
            total += 1
            if ts is not None and len(ts) and (abs(ts - s).min() / 1000.0) <= window_s:
                aligned += 1
    return {
        "boundaries": total,
        "aligned": aligned,
        "aligned_pct": round(100 * aligned / total, 1) if total else None,
        "window_s": window_s,
    }


def check_label_stability(events: pd.DataFrame) -> pd.DataFrame:
    """Each label should correspond to exactly one (system, route) pair."""
    ev = events[events.process_label.notna() & events.pair_ff.notna()]
    rows = []
    for lab, g in ev.groupby("process_label"):
        pairs = g.pair_ff.value_counts()
        rows.append({
            "label": lab,
            "n_events": len(g),
            "n_distinct_pairs": len(pairs),
            "dominant_pair": pairs.index[0],
            "dominant_pct": round(100 * pairs.iloc[0] / len(g), 1),
        })
    return pd.DataFrame(rows).sort_values("n_events", ascending=False)


def score_against_gt(segs: pd.DataFrame, gt: pd.DataFrame,
                     tolerance_s: float = TOLERANCE_S) -> dict:
    """Boundary precision/recall against gt.jsonl, for if dataset A's JSON
    parts ever arrive. Unused today — gt is empty."""
    if gt.empty:
        return {"status": "no ground truth available"}
    truth = gt[gt.get("event") == "process_started"].copy()
    truth["ts_ms"] = pd.to_datetime(truth["ts_utc"], utc=True).astype("int64") // 10**6

    tp = fn = 0
    for sid, tg in truth.groupby("session_id"):
        pred = segs[segs.session_id == sid].start_ms.to_numpy()
        for t in tg.ts_ms:
            if len(pred) and (abs(pred - t).min() / 1000.0) <= tolerance_s:
                tp += 1
            else:
                fn += 1
    fp = len(segs) - tp
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return {"tp": tp, "fp": fp, "fn": fn,
            "precision": round(prec, 3), "recall": round(rec, 3),
            "f1": round(f1, 3), "tolerance_s": tolerance_s}


if __name__ == "__main__":
    from data_loader import DATASET_B_ROOTS, load_events
    from process_context import annotate
    from segment import segment

    ev = annotate(load_events(DATASET_B_ROOTS))
    segs = segment(ev)

    print("\n=== 1. tiling / overlap / coverage ===")
    t = check_tiling(segs, ev)
    print(t.to_string(index=False))
    print(f"\ntotal overlap across all sessions: {t.overlap_s.sum():.3f}s")
    print(f"mean coverage: {t.coverage_pct.mean():.1f}%  "
          f"(min {t.coverage_pct.min():.1f}%, max {t.coverage_pct.max():.1f}%)")

    print("\n=== 2. p_code purity (independent signal) ===")
    p = check_pcode_purity(segs, ev)
    print(f"segments carrying p_code evidence: {p['segments_with_pcode']} / {len(segs)}"
          f"  (+{p['segments_unresolved_excluded']} excluded as *_unresolved)")
    print(f"of those, label agrees with p_code: {p['segments_pure']} "
          f"({p['purity_pct']}%)")
    print("\nlabel -> majority p_code:")
    for k, v in sorted(p["label_to_pcode"].items()):
        print(f"    {v:4s}  {k}")
    if p["mismatches"]:
        print("\nmismatches:")
        for m in p["mismatches"]:
            print(f"    {m}")

    print("\n=== 3. boundary alignment with real navigation/app-switch ===")
    b = check_boundary_alignment(segs, ev)
    print(f"{b['aligned']} / {b['boundaries']} boundaries within "
          f"{b['window_s']}s of a navigation or app switch ({b['aligned_pct']}%)")

    print("\n=== 4. label stability (one label <-> one (system, route)) ===")
    print(check_label_stability(ev).to_string(index=False))
