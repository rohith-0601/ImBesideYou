"""
Screenshot spot-check for predicted segment boundaries.

The point of this module: dataset A's ground truth never arrived, so the only
way to check a boundary against reality is to look at what was on screen when
the algorithm says the work changed. Dataset B ships 4,746 screenshots, so
that is actually possible.

For each sampled boundary it resolves the nearest `screenshot_smart` capture
before and after, via `payload.file_reference` (as DATA_SCHEMA.md instructs —
not by parsing filenames), and writes a markdown table of image paths with
the predicted label either side. A human then opens a handful and confirms
the screen really did change from one process to another.

Missing images are reported as "no capture available" rather than raised, per
the schema note that a referenced file is absent in rare cases.

Why the offsets matter (learned the hard way)
---------------------------------------------
The first version of this tool took the *nearest* capture either side of a
boundary and appeared to show a false positive: both frames showed the same
Finance invoice screen. Reading the raw events around that boundary showed
the segmentation was right — there was a real `browser_navigation` to the HR
system — and the tool was wrong. Two lags cause it:

- a capture taken 0.1s after a navigation still shows the *old* page, because
  the new one has not rendered yet (the pre-navigation frame even has the
  browser loading bar visible);
- `window_title` trails the actual navigation by ~2.3s, so titles agree with
  the old screen for a moment too.

So captures are taken at a deliberate standoff: at least `LEAD_S` before and
`LAG_S` after the boundary. Comparing frames closer than that measures
rendering latency, not segmentation quality.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent

# Standoff from the boundary. LAG_S must exceed both page-render time and the
# ~2.3s window_title lag measured in dataset B.
LEAD_S = 2.0
LAG_S = 4.0


def _shot_index(events: pd.DataFrame) -> pd.DataFrame:
    """One row per screenshot event with its resolved on-disk path."""
    shots = events[events.event_type == "screenshot_smart"].copy()
    rows = []
    for r in shots.itertuples():
        p = r.payload if isinstance(r.payload, dict) else {}
        fr = p.get("file_reference") or {}
        fname = fr.get("filename")
        if not fname:
            continue
        rows.append({
            "session_id": r.session_id,
            "chunk_id": r.chunk_id,
            "timestamp_ms": r.timestamp_ms,
            "filename": fname,
        })
    idx = pd.DataFrame(rows)
    if idx.empty:
        return idx

    # Resolve to a real path by searching the dataset roots for the chunk dir.
    cache: dict[tuple[str, str], Path | None] = {}

    def resolve(sid: str, cid: str, fname: str) -> str | None:
        key = (sid, cid)
        if key not in cache:
            hit = None
            for root in REPO_ROOT.glob("dataset_*"):
                cand = root / sid / cid / "screenshots"
                if cand.is_dir():
                    hit = cand
                    break
            cache[key] = hit
        base = cache[key]
        if base is None:
            return None
        f = base / fname
        return str(f.relative_to(REPO_ROOT)) if f.exists() else None

    idx["path"] = [resolve(r.session_id, r.chunk_id, r.filename)
                   for r in idx.itertuples()]
    return idx


def boundary_shots(segs: pd.DataFrame, events: pd.DataFrame,
                   per_session: int = 2) -> pd.DataFrame:
    """For sampled boundaries, the nearest capture before and after."""
    idx = _shot_index(events)
    rows = []
    for sid, g in segs.groupby("session_id"):
        g = g.sort_values("start_ms").reset_index(drop=True)
        sidx = idx[idx.session_id == sid].sort_values("timestamp_ms")
        if sidx.empty or len(g) < 2:
            continue
        # Only sample boundaries where the *label* changes. Within-process
        # case boundaries are real but not visually checkable — the screen
        # looks the same either side, only the selected row differs — so
        # they would make the check look like it was failing when it wasn't.
        picks = [i for i in range(1, len(g))
                 if g.loc[i, "label"] != g.loc[i - 1, "label"]]
        if not picks:
            continue
        step = max(1, len(picks) // max(1, per_session))
        for i in picks[::step][:per_session]:
            t = g.loc[i, "start_ms"]
            before = sidx[sidx.timestamp_ms <= t - LEAD_S * 1000].tail(1)
            after = sidx[sidx.timestamp_ms >= t + LAG_S * 1000].head(1)
            # Keep the capture inside the segment it is meant to represent.
            seg_end = g.loc[i, "end_ms"]
            after = after[after.timestamp_ms <= seg_end]
            rows.append({
                "session_id": sid,
                "boundary_iso": pd.to_datetime(t, unit="ms", utc=True).strftime("%H:%M:%S"),
                "label_before": g.loc[i - 1, "label"],
                "label_after": g.loc[i, "label"],
                "shot_before": (before.path.iloc[0] if len(before) else None)
                               or "no capture available",
                "shot_after": (after.path.iloc[0] if len(after) else None)
                              or "no capture available",
                "dt_before_s": round((t - before.timestamp_ms.iloc[0]) / 1000, 1) if len(before) else None,
                "dt_after_s": round((after.timestamp_ms.iloc[0] - t) / 1000, 1) if len(after) else None,
            })
    return pd.DataFrame(rows)


def main() -> None:
    from data_loader import DATASET_B_ROOTS, load_events
    from process_context import annotate
    from segment import segment

    ap = argparse.ArgumentParser()
    ap.add_argument("--per-session", type=int, default=2)
    ap.add_argument("--out", default="reports/day2_boundary_spotcheck.md")
    args = ap.parse_args()

    ev = annotate(load_events(DATASET_B_ROOTS))
    segs = segment(ev)
    bs = boundary_shots(segs, ev, per_session=args.per_session)

    out = REPO_ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        f.write("# Day 2 — boundary screenshot spot-check\n\n")
        f.write("Generated by `src/spot_check.py`. Each row is a predicted "
                "process boundary with the nearest screen capture either "
                "side. Open the two images: the screen should show a "
                "different system or screen after the boundary than before.\n\n")
        f.write(f"Sampled {len(bs)} boundaries "
                f"({args.per_session} per session). Only boundaries where the "
                f"process label changes are sampled — within-process case "
                f"boundaries are real but look identical on screen, since "
                f"only the selected table row differs.\n\n")
        f.write("| session | at | before | after | shot before | shot after |\n")
        f.write("|---|---|---|---|---|---|\n")
        for r in bs.itertuples():
            f.write(f"| `{r.session_id[4:22]}` | {r.boundary_iso} | "
                    f"`{r.label_before}` | `{r.label_after}` | "
                    f"[{r.dt_before_s}s]({r.shot_before}) | "
                    f"[{r.dt_after_s}s]({r.shot_after}) |\n")

    print(f"{len(bs)} boundaries sampled -> {args.out}")
    missing = (bs.shot_before == "no capture available").sum() + \
              (bs.shot_after == "no capture available").sum()
    print(f"unresolved captures: {missing} / {2 * len(bs)}")
    print(f"median |dt| before: {bs.dt_before_s.median()}s, "
          f"after: {bs.dt_after_s.median()}s")
    print("\nsample:")
    print(bs[["session_id", "boundary_iso", "label_before", "label_after"]]
          .head(8).to_string(index=False))


if __name__ == "__main__":
    main()
