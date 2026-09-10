"""
Case-ID extraction — the anchor for Step 1 segmentation.

Day 1 finding: inter-event idle gaps are useless as boundary signals in this
data (99.9th percentile is ~10s; only 7 gaps in 20,477 events exceed 30s,
because the README says waiting time was compressed in the test recording).
So boundaries have to come from *semantic* signal instead.

The usable semantic anchor is the case identifier. Two families appear in
dataset_b:

    P<n>-<8digits>-<3digits>   e.g. P6-07010448-012   (HR portal records)
    INV-<year>-<4digits>       e.g. INV-2026-7344     (invoice references)

They survive in these payload paths (note that clipboard `text_content` and
browser_form_input `value` are NULL throughout — content is redacted at
capture, so these element/field paths are the only place real business text
comes through):

    payload.target_element.name    (mouse_click)
    payload.target_element.value   (mouse_click)
    payload.target_field.value     (keystroke)
    payload.element.text           (browser_click)
    context.extracted_text         (~4.6% of events)

Measured on dataset_b: 170 distinct cases, 1,020 mentions, ~11.4 cases per
session, and 169/170 cases occur in exactly one session — so a case is a
session-local unit of work. That is what makes case-anchored segmentation
viable.
"""

from __future__ import annotations

import re

import pandas as pd

# P-family allows a letter+digit prefix (P6, P13); INV-family is separate.
CASE_RE = re.compile(
    r"\b(?:[A-Z]{1,3}[0-9]{0,2}-[0-9]{4,9}-[0-9]{2,4}|INV-[0-9]{4}-[0-9]{3,5})\b"
)

# Route -> a stable process label. Kept deliberately close to the portal's own
# vocabulary so the label is defensible against the screens themselves.
ROUTE_LABELS = {
    "#/payroll-items": "payroll_change",
    "#/leave-applications": "leave_application",
    "#/onboarding": "onboarding",
    "#/social-insurance": "social_insurance",
    "#/resident-tax": "resident_tax",
    "#/dashboard": "dashboard_review",
}


def _dig(payload, *keys):
    cur = payload
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def route_of(url) -> str | None:
    """'http://127.0.0.1:5132/#/payroll-items?x=1' -> '#/payroll-items'."""
    if not isinstance(url, str) or "#/" not in url:
        return None
    return "#/" + url.split("#/", 1)[1].split("?")[0]


def text_surfaces(row) -> list[str]:
    """Every string on an event that has been observed to carry business text."""
    out = []
    p = row.get("payload")
    if isinstance(p, dict):
        for path in (
            ("target_element", "name"),
            ("target_element", "value"),
            ("target_field", "value"),
            ("element", "text"),
        ):
            v = _dig(p, *path)
            if isinstance(v, str):
                out.append(v)
    for col in ("extracted_text", "window_title", "browser_tab_title"):
        v = row.get(col)
        if isinstance(v, str):
            out.append(v)
    return out


def extract_case_mentions(df: pd.DataFrame) -> pd.DataFrame:
    """One row per (event, case-ID) mention. An event mentioning two cases
    yields two rows; most mention zero and drop out entirely."""
    rows = []
    for r in df.to_dict("records"):
        found: set[str] = set()
        for t in text_surfaces(r):
            found.update(CASE_RE.findall(t))
        if not found:
            continue
        rt = route_of(r.get("browser_url"))
        for case in found:
            rows.append({
                "session_id": r["session_id"],
                "case_id": case,
                "case_family": case.split("-")[0],
                "route": rt,
                "label": ROUTE_LABELS.get(rt) if rt else None,
                "timestamp_ms": r["timestamp_ms"],
                "timestamp_iso": r["timestamp_iso"],
                "event_type": r["event_type"],
                "app_name": r["app_name"],
            })
    return pd.DataFrame(rows)


def case_spans(mentions: pd.DataFrame) -> pd.DataFrame:
    """Collapse mentions to one row per (session, case): first and last time
    the case was seen, plus its dominant route. This is the raw material for
    segments.jsonl — but NOT yet segments: first/last mention is an
    under-estimate of the true span (the worker opens the record before the
    ID is ever rendered, and keeps working after the last mention), and
    overlapping spans still need reconciling. That's Day 2 work.
    """
    if mentions.empty:
        return pd.DataFrame()

    def dominant_route(s: pd.Series):
        s = s.dropna()
        return s.mode().iloc[0] if not s.empty else None

    g = mentions.groupby(["session_id", "case_id"])
    out = g.agg(
        case_family=("case_family", "first"),
        first_seen_ms=("timestamp_ms", "min"),
        last_seen_ms=("timestamp_ms", "max"),
        n_mentions=("case_id", "count"),
        route=("route", dominant_route),
    ).reset_index()
    out["label"] = out["route"].map(ROUTE_LABELS)
    out["span_seconds"] = (out["last_seen_ms"] - out["first_seen_ms"]) / 1000
    return out.sort_values(["session_id", "first_seen_ms"]).reset_index(drop=True)


if __name__ == "__main__":
    from data_loader import DATASET_B_ROOTS, load_events

    df = load_events(DATASET_B_ROOTS)
    mentions = extract_case_mentions(df)
    spans = case_spans(mentions)

    print(f"\nmentions: {len(mentions)}, distinct cases: {mentions.case_id.nunique()}")
    print(f"case-session spans: {len(spans)}")
    print("\n=== spans per label ===")
    print(spans.groupby("label").agg(
        n_cases=("case_id", "nunique"),
        median_span_s=("span_seconds", "median"),
        median_mentions=("n_mentions", "median"),
    ).round(1).to_string())
    print("\n=== how much of each session is covered by case spans? ===")
    for sid, g in spans.groupby("session_id"):
        covered = (g.last_seen_ms - g.first_seen_ms).sum() / 1000
        ses = df[df.session_id == sid]
        total = (ses.timestamp_ms.max() - ses.timestamp_ms.min()) / 1000
        print(f"{sid}  cases={len(g):3d}  span_sum={covered:7.1f}s  "
              f"session={total:7.1f}s  ratio={covered/total:5.2f}")
