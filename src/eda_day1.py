"""
Day 1 exploratory analysis on dataset_b (the only fully-loadable dataset
right now). Goal: surface the signals Step 1 segmentation will have to use
- idle-time gaps, app/URL switch frequency, session shape - and write them
out as a markdown report under reports/.

This is throwaway-quality by design: it exists to inform the segmentation
heuristic built on Day 2, not to be a polished analysis in its own right.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from data_loader import DATASET_B_ROOTS, load_events

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORT_PATH = REPO_ROOT / "reports" / "day1_eda.md"


def route(url: str | None) -> str | None:
    """Collapse a full localhost URL down to its hash-route, e.g.
    'http://127.0.0.1:5132/#/payroll-items?x=1' -> '#/payroll-items'.
    None if there's no hash route (bare host, non-portal URL, etc.)."""
    if not isinstance(url, str) or "#/" not in url:
        return None
    return "#/" + url.split("#/", 1)[1].split("?")[0]


def main() -> None:
    df = load_events(DATASET_B_ROOTS)

    lines = ["# Day 1 EDA — dataset_b", ""]
    lines.append(f"Loaded **{len(df):,}** events across "
                  f"**{df['session_id'].nunique()}** sessions.\n")

    # --- 1. Session shape --------------------------------------------------
    lines.append("## 1. Session shape\n")
    per_session = df.groupby("session_id").agg(
        n_events=("event_id", "count"),
        start=("timestamp_iso", "min"),
        end=("timestamp_iso", "max"),
        machine=("machine_id", "first"),
    )
    per_session["duration_min"] = (
        (per_session["end"] - per_session["start"]).dt.total_seconds() / 60
    )
    lines.append(per_session[["machine", "n_events", "duration_min"]]
                 .round(1).to_markdown())
    lines.append(f"\nTotal wall-clock across sessions: "
                 f"{per_session['duration_min'].sum():.0f} min "
                 f"(sessions do not overlap in time per machine, but do "
                 f"across the 4 operators).\n")

    # --- 2. Gap distribution (ms_since_last_event) — segmentation signal ---
    lines.append("## 2. Inter-event gap distribution (candidate idle threshold)\n")
    gaps = df["ms_since_last_event"].dropna()
    gaps = gaps[gaps >= 0]
    pct = gaps.quantile([0.5, 0.75, 0.9, 0.95, 0.99, 0.995, 0.999])
    lines.append("Percentiles of `ms_since_last_event` (all events, session-internal "
                  "gaps only; first event of each chunk has no prior gap):\n")
    lines.append((pct / 1000).round(2).rename("seconds").to_markdown())

    n_gt_30s = (gaps > 30_000).sum()
    n_gt_60s = (gaps > 60_000).sum()
    n_gt_120s = (gaps > 120_000).sum()
    lines.append(f"\n- gaps > 30s: {n_gt_30s} ({100*n_gt_30s/len(gaps):.2f}%)")
    lines.append(f"- gaps > 60s: {n_gt_60s} ({100*n_gt_60s/len(gaps):.2f}%)")
    lines.append(f"- gaps > 120s: {n_gt_120s} ({100*n_gt_120s/len(gaps):.2f}%)\n")
    lines.append("Note: per README, waiting time in this test environment is "
                 "compressed vs. production, so an idle-gap threshold alone "
                 "will likely under-segment — cross-checked against app/URL "
                 "switches below, not used in isolation.\n")

    # --- 3. App switch frequency -------------------------------------------
    lines.append("## 3. Application usage\n")
    app_counts = df["app_name"].value_counts(dropna=True)
    lines.append(app_counts.rename("event_count").to_markdown())

    switches = df[df["event_type"] == "app_switch"]
    lines.append(f"\n`app_switch` events: {len(switches)} total, "
                 f"{len(switches) / df['session_id'].nunique():.1f} per session on average.\n")

    # --- 4. Browser route usage (portal navigation) ------------------------
    lines.append("## 4. Portal route usage (from active_browser_tab.url)\n")
    df["route"] = df["browser_url"].apply(route)
    df["portal_host"] = df["browser_url"].str.extract(r"(127\.0\.0\.1:\d+)")
    route_counts = (
        df.dropna(subset=["route"])
        .groupby(["portal_host", "route"])
        .size()
        .rename("event_count")
        .sort_values(ascending=False)
    )
    lines.append(route_counts.to_markdown())
    lines.append(f"\nDistinct portal hosts seen: "
                 f"{sorted(df['portal_host'].dropna().unique())}\n")

    # --- 5. Repetition signal: same route revisited within a session -------
    lines.append("## 5. Route-revisit pattern (evidence of interleaved work)\n")
    revisit_rows = []
    for sid, g in df.dropna(subset=["route"]).groupby("session_id"):
        route_seq = g.sort_values("timestamp_ms")["route"].tolist()
        # count how many times the route changes and back again
        # (A -> B -> A pattern = interleaving, not just sequential progress)
        distinct_routes = len(set(route_seq))
        transitions = sum(1 for a, b in zip(route_seq, route_seq[1:]) if a != b)
        revisit_rows.append({
            "session_id": sid,
            "distinct_routes": distinct_routes,
            "route_transitions": transitions,
        })
    lines.append(pd.DataFrame(revisit_rows).set_index("session_id").to_markdown())
    lines.append("\nMultiple distinct routes with many transitions per session "
                 "is the interleaving pattern the README warns about "
                 "('a person switches to a different task partway through "
                 "one, then returns to it later') — segmentation cannot "
                 "assume one route = one contiguous block.\n")

    REPORT_PATH.write_text("\n".join(str(x) for x in lines), encoding="utf-8")
    print(f"Wrote {REPORT_PATH}")


if __name__ == "__main__":
    main()
