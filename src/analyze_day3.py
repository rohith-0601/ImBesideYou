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
  determinism   penalises *unpredictable* exceptions only
  data_access   share of executions confined to the browser
  branch_cost   1 + normalised variant count       (how many paths to support)

Not all exceptions cost the same
--------------------------------
`determinism` began as `1 - exception_rate`, which turned out to conflate two
very different situations:

* `fin_purchase_order_management` has a 13.2% exception rate, and every one of
  those exceptions is a 緊急発注 (urgent order). Exception rate by variant is
  exactly 1.0 for 緊急発注 and exactly 0.0 for スポット発注 / 定期発注 /
  年間契約. The exception is a **labelled property of the order, known before
  the work starts**. Supporting it is one branch.
* `fin_invoice_matching` has a 34.4% exception rate (差異あり要確認), and
  nothing captured predicts it. Amount does not: 差異あり averages
  ¥1,030,094 against ¥1,299,373 for 差異なし, with medians of ¥665,036 and
  ¥697,654 and fully overlapping ranges. The 種別 column visible in the
  screenshots (調整 / 定常) **never appears in the event log at all** — not in
  `extracted_text`, not in any element name. The discrepancy is *discovered by
  doing the comparison*, against data the recording does not carry.

Penalising both at 1 - rate rewarded the wrong candidate. Only unpredictable
exceptions reduce `determinism` now; predictable ones are charged to
`branch_cost` instead, where they belong.

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


# How each process's exceptions arise. Stated explicitly with the evidence
# rather than derived, because for fin_invoice_matching the variant *is* the
# outcome, so deriving predictability from the variant would be circular.
#   predictable  - determined by a field captured before the work begins
#   judgement    - discovered during the work, not predictable from the log
#   none         - no exceptions observed
EXCEPTION_NATURE = {
    "fin_purchase_order_management": "predictable",  # 緊急発注, rate 1.0 by variant
    "fin_invoice_matching": "judgement",             # 差異あり; amount does not predict, 種別 never logged
}

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
    df["exception_nature"] = df.label_final.map(EXCEPTION_NATURE).fillna("none")
    # Only judgement exceptions reduce determinism. A predictable exception is
    # a branch to implement, not work a machine cannot do, so it is charged to
    # branch_cost via the variant count instead.
    df["determinism"] = 1 - df.exception_rate.where(
        df.exception_nature == "judgement", 0.0)
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


TARGET_PROCESSES = [
    "hr_leave_application",
    "hr_expense_settlement",
    "fin_purchase_order_management",
]


def per_operator(ex: pd.DataFrame) -> pd.DataFrame:
    """Who does what, and how consistently.

    The README asks how many people are involved. The more useful form of the
    question is whether the work is concentrated or shared, and whether
    operators handle the same process at the same speed — wide spread between
    operators on an identical process is itself an argument for automating it,
    since it means the procedure is being applied inconsistently.
    """
    rows = []
    for op, g in ex.groupby("operator"):
        rows.append({
            "operator": op[-8:] if isinstance(op, str) else op,
            "executions": len(g),
            "processes": g.label_final.nunique(),
            "sessions": g.session_id.nunique(),
            "total_s": round(g.duration_s.sum(), 1),
            "median_s": round(g.duration_s.median(), 1),
        })
    return pd.DataFrame(rows).sort_values("executions", ascending=False)


def operator_spread(ex: pd.DataFrame) -> pd.DataFrame:
    """Per process, how much operators differ in median time per execution."""
    rows = []
    for lab, g in ex.groupby("label_final"):
        med = g.groupby("operator").duration_s.median()
        if len(med) < 2:
            continue
        rows.append({
            "label": lab,
            "operators": len(med),
            "fastest_median_s": round(med.min(), 1),
            "slowest_median_s": round(med.max(), 1),
            "spread_x": round(med.max() / med.min(), 2) if med.min() else None,
        })
    return (pd.DataFrame(rows)
            .sort_values("spread_x", ascending=False)
            .reset_index(drop=True))


def residual_work(events: pd.DataFrame, ex: pd.DataFrame,
                  targets: list[str]) -> pd.DataFrame:
    """What the tool would *not* remove, for the processes in scope.

    Splits each target process's observed time into the part spent in the
    portal (which a prepared-and-reviewed tool can compress) and the part
    spent in desktop applications (which it cannot, in this phase). Used for
    the README's "what manual work remains after deployment" question, and
    deliberately conservative: review time is retained in full, because the
    tool prepares and a human still commits.
    """
    rows = []
    for lab in targets:
        g = ex[ex.label_final == lab]
        portal_s = desktop_s = 0.0
        for sid, gs in g.groupby("session_id"):
            ses = events[events.session_id == sid]
            ts = ses.timestamp_ms.to_numpy()
            apps = ses.app_name.to_numpy()
            for r in gs.itertuples():
                mask = (ts >= r.start_ms) & (ts <= r.end_ms)
                used = {a for a in apps[mask] if isinstance(a, str)}
                if used & DESKTOP_APPS:
                    desktop_s += r.duration_s
                else:
                    portal_s += r.duration_s
        total = portal_s + desktop_s
        rows.append({
            "label": lab,
            "executions": len(g),
            "total_s": round(total, 1),
            "portal_only_s": round(portal_s, 1),
            "desktop_involved_s": round(desktop_s, 1),
            "addressable_share": round(portal_s / total, 3) if total else None,
        })
    return pd.DataFrame(rows)


def activity_profile(events: pd.DataFrame, ex: pd.DataFrame) -> pd.DataFrame:
    """What an execution is actually made of, per process.

    Counts the mean number of clipboard operations, keystrokes, clicks, app
    switches and distinct applications inside one execution. The clipboard
    column is the interesting one: it is manual data movement — a value being
    carried by hand from one field or application to another — which is
    precisely the work an integration removes. Content is redacted throughout
    (Day 1), so only the *count* is available, not what was copied.
    """
    import numpy as np

    rows = []
    for sid, gs in ex.groupby("session_id"):
        ses = events[events.session_id == sid]
        ts = ses.timestamp_ms.to_numpy()
        et = ses.event_type.to_numpy()
        ap = ses.app_name.to_numpy()
        for r in gs.itertuples():
            m = (ts >= r.start_ms) & (ts <= r.end_ms)
            e, a = et[m], ap[m]
            rows.append({
                "label": r.label_final,
                "duration_s": r.duration_s,
                "clipboard": int((e == "clipboard_change").sum()),
                "keystrokes": int((e == "keystroke").sum()),
                "clicks": int(np.isin(
                    e, ["mouse_click", "browser_click", "mouse_double_click"]).sum()),
                "app_switches": int((e == "app_switch").sum()),
                "distinct_apps": len({x for x in a if isinstance(x, str)}),
            })
    df = pd.DataFrame(rows)
    return (df.groupby("label")
              .agg(executions=("duration_s", "size"),
                   median_s=("duration_s", "median"),
                   clipboard_per_exec=("clipboard", "mean"),
                   keystrokes_per_exec=("keystrokes", "mean"),
                   clicks_per_exec=("clicks", "mean"),
                   switches_per_exec=("app_switches", "mean"),
                   apps_per_exec=("distinct_apps", "mean"),
                   clipboard_total=("clipboard", "sum"))
              .round(2)
              .reset_index()
              .sort_values("clipboard_per_exec", ascending=False))


# Reference kinds found in completion comments. Only INV and P identify an
# individual case; BATCH is a product code, and treating it as a case makes
# repeat work look like rework when it is simply the same product adjusted
# on separate occasions.
CASE_REF_KINDS = {
    "INV": "case",      # invoice number, one per case
    "P": "case",        # portal record id, one per case
    "BATCH": "product",  # product batch code, recurs by design
}


def rework(ex: pd.DataFrame) -> pd.DataFrame:
    """Is the same case worked more than once in a session?

    Split by reference kind, because the answer is completely different
    depending on which you count. Rework is a standard automation argument —
    "the tool removes the second pass" — so it is worth establishing whether
    there is any, rather than assuming.
    """
    cr = ex[ex.case_ref.notna()].copy()
    cr["kind"] = cr.case_ref.str.extract(r"^(INV|BATCH|P)")[0]
    rows = []
    for kind, g in cr.groupby("kind"):
        rep = g.groupby(["session_id", "case_ref"]).size()
        rows.append({
            "ref_kind": kind,
            "identifies": CASE_REF_KINDS.get(kind, "?"),
            "distinct_refs": g.case_ref.nunique(),
            "ref_session_pairs": len(rep),
            "repeated": int((rep > 1).sum()),
            "repeat_rate": round(float((rep > 1).mean()), 3),
            "max_repeats": int(rep.max()),
        })
    return pd.DataFrame(rows)


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
                  "exception_nature", "data_access", "variants",
                  "opportunity"]].to_string(index=False))
    print("\n=== activity profile per execution ===")
    print(activity_profile(ev, ex).to_string(index=False))
    print("\n=== rework check, by reference kind ===")
    print(rework(ex).to_string(index=False))
    print("\n=== per operator ===")
    print(per_operator(ex).to_string(index=False))
    print("\n=== residual manual work for the chosen scope ===")
    print(residual_work(ev, ex, TARGET_PROCESSES).to_string(index=False))
