"""
Step 2 — process analysis and automation prioritisation.

Answers the README's Step 2 questions from the Day 2 segmentation plus the
completion comments parsed in `case_parser.py`:

  * what processes are performed, how often, how much time do they consume?
  * how many people are involved?
  * are there different handling patterns within the same process?

and then ranks automation candidates on explicit, inspectable criteria rather
than assertion.

Scoring
-------
The README says to judge candidates against each other rather than by
absolute figures, because waiting time was compressed in the test recording.
So every component below is a *relative* score in [0, 1] across the twelve
processes, and the final number is meaningless except as an ordering.

    opportunity = volume x time_share x determinism x data_access
                  ---------------------------------------------
                                  branch_cost

  volume        share of all executions            (how often it happens)
  time_share    share of all observed process time (what it costs today)
  determinism   1 - exception_rate                 (how often a human must judge)
  data_access   share of executions confined to the browser
  branch_cost   1 + normalised variant count       (how many paths to support)

`data_access` started as "how many of the three portals does one execution
touch". Measured, that is 1 for every process — a case stays inside one
system — so the component did no work and was replaced. What actually varies
is whether a process can be driven through the portal alone or also needs a
desktop application: a browser-only flow can be automated against HTTP, while
one that opens Word or Excel needs file handling and a desktop surface.

`determinism` and `branch_cost` are the two that stop a high-volume process
from automatically winning: a process that is frequent but needs judgement on
a quarter of its cases, or that has ten handling patterns, is a worse first
target than a slightly smaller one that is uniform.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent


def build_executions(events: pd.DataFrame, segs: pd.DataFrame) -> pd.DataFrame:
    """One row per execution: label (comment-corrected), variant, duration,
    operator, apps touched."""
    from case_parser import parse_comment

    parsed = [parse_comment(c) if isinstance(c, str) else {} for c in segs.case_comment]
    out = segs.copy().reset_index(drop=True)
    for k in ("template_label", "variant", "amount_yen", "case_ref",
              "effective_date", "quantity", "is_exception"):
        out[k] = [p.get(k) for p in parsed]

    # The comment names its own process; an inherited screen context does not.
    out["label_final"] = out["template_label"].fillna(out["label"])
    out["label_corrected"] = (out["template_label"].notna()
                              & (out["template_label"] != out["label"]))

    op = (events.groupby("session_id")
                .agg(operator=("username_hash", "first"),
                     machine=("machine_id", "first"))
                .reset_index())
    return out.merge(op, on="session_id", how="left")


def per_process(ex: pd.DataFrame) -> pd.DataFrame:
    g = ex.groupby("label_final")
    df = g.agg(
        executions=("label_final", "size"),
        total_s=("duration_s", "sum"),
        median_s=("duration_s", "median"),
        operators=("operator", "nunique"),
        sessions=("session_id", "nunique"),
        variants=("variant", "nunique"),
        exceptions=("is_exception", "sum"),
    ).reset_index()
    df["exception_rate"] = (df.exceptions / df.executions).round(3)
    df["share_of_executions"] = (df.executions / df.executions.sum()).round(3)
    df["share_of_time"] = (df.total_s / df.total_s.sum()).round(3)
    return df.sort_values("total_s", ascending=False).reset_index(drop=True)


def apps_per_process(ex: pd.DataFrame) -> dict[str, list[str]]:
    out = {}
    for lab, g in ex.groupby("label_final"):
        apps = sorted({a for lst in g.apps if isinstance(lst, list) for a in lst})
        out[lab] = apps
    return out


BROWSER_APPS = {"Microsoft Edge"}
DESKTOP_APPS = {"Microsoft Word", "Microsoft Excel", "Notepad"}


def systems_per_process(events: pd.DataFrame, ex: pd.DataFrame) -> dict[str, float]:
    """Median number of distinct portals touched *within a single execution*.

    Measured per execution rather than unioned across the process: every
    process is reachable from all three portals over a full day, so a union is
    3 for everything and says nothing. Measured this way it is 1.0 for all
    twelve processes — a case stays inside one system — which is itself a
    useful (negative) finding and the reason `app_surface` carries the
    integration-cost signal instead.
    """
    per_exec: dict[str, list[int]] = {}
    for sid, gs in ex.groupby("session_id"):
        ses = events[events.session_id == sid]
        ts = ses.timestamp_ms.to_numpy()
        sysvals = ses.system.to_numpy()
        for r in gs.itertuples():
            mask = (ts >= r.start_ms) & (ts <= r.end_ms)
            n = len({s for s in sysvals[mask] if isinstance(s, str)})
            per_exec.setdefault(r.label_final, []).append(max(n, 1))
    return {k: float(pd.Series(v).median()) for k, v in per_exec.items()}


def app_surface(events: pd.DataFrame, ex: pd.DataFrame) -> pd.DataFrame:
    """Per process: the share of executions that stay inside the browser, and
    which desktop applications the rest pull in.

    This is the integration-cost signal. A browser-only process can be driven
    against the portal's own HTTP interface; one that opens Word or Excel
    needs document handling and a desktop surface, which is a materially
    bigger build.
    """
    rows = []
    for sid, gs in ex.groupby("session_id"):
        ses = events[events.session_id == sid]
        ts = ses.timestamp_ms.to_numpy()
        apps = ses.app_name.to_numpy()
        for r in gs.itertuples():
            mask = (ts >= r.start_ms) & (ts <= r.end_ms)
            used = {a for a in apps[mask] if isinstance(a, str)}
            desktop = used & DESKTOP_APPS
            rows.append({
                "label_final": r.label_final,
                "browser_only": not desktop,
                "desktop_apps": ",".join(sorted(desktop)),
            })
    df = pd.DataFrame(rows)
    out = df.groupby("label_final").agg(
        browser_only_share=("browser_only", "mean"),
    ).reset_index()
    out["desktop_apps"] = [
        ",".join(sorted({a for s in df[df.label_final == lab].desktop_apps
                         for a in s.split(",") if a}))
        for lab in out.label_final
    ]
    out["browser_only_share"] = out.browser_only_share.round(3)
    return out


def score(stats: pd.DataFrame, systems: dict[str, float],
          surface: pd.DataFrame) -> pd.DataFrame:
    df = stats.merge(surface, on="label_final", how="left")
    df["n_systems"] = df.label_final.map(systems).fillna(1)

    def norm(s):
        rng = s.max() - s.min()
        return (s - s.min()) / rng if rng else pd.Series(1.0, index=s.index)

    df["volume"] = norm(df.executions)
    df["time_share"] = norm(df.total_s)
    df["determinism"] = 1 - df.exception_rate
    # Floor at 0.2 so a fully desktop-bound process is penalised but not
    # zeroed out — it is harder to automate, not impossible.
    df["data_access"] = df.browser_only_share.fillna(0).clip(lower=0.2)
    df["branch_cost"] = 1 + norm(df.variants)

    df["opportunity"] = (
        (df.volume + df.time_share) / 2
        * df.determinism
        * df.data_access
        / df.branch_cost
    ).round(3)
    return df.sort_values("opportunity", ascending=False).reset_index(drop=True)


def variant_table(ex: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (lab, var), g in ex.groupby(["label_final", "variant"]):
        rows.append({
            "label": lab, "variant": var, "n": len(g),
            "median_s": round(g.duration_s.median(), 1),
            "exception_rate": round(g.is_exception.mean(), 3),
        })
    return pd.DataFrame(rows).sort_values(["label", "n"], ascending=[True, False])


if __name__ == "__main__":
    from data_loader import DATASET_B_ROOTS, load_events
    from process_context import annotate
    from segment import segment

    ev = annotate(load_events(DATASET_B_ROOTS))
    segs = segment(ev)
    ex = build_executions(ev, segs)

    print(f"\nexecutions: {len(ex)}   "
          f"labels corrected by comment: {int(ex.label_corrected.sum())}")
    stats = per_process(ex)
    sysmap = systems_per_process(ev, ex)
    surface = app_surface(ev, ex)
    ranked = score(stats, sysmap, surface)

    print("\n=== per process ===")
    print(stats[["label_final", "executions", "total_s", "median_s",
                 "operators", "variants", "exception_rate"]].to_string(index=False))
    print("\n=== app surface ===")
    print(surface.to_string(index=False))
    print("\n=== ranked automation candidates ===")
    print(ranked[["label_final", "executions", "total_s", "determinism",
                  "data_access", "variants", "opportunity"]].to_string(index=False))
