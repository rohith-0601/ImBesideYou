"""
Loads raw operation logs (events.jsonl) into a single flat, analysis-ready
pandas DataFrame, and loads ground truth (gt.jsonl / gt_manifest.json) where
present.

Handles two messy realities of how the data arrived on disk:

1. Dataset A was delivered as 5 overlapping folder splits ("dataset_a",
   "dataset_a 2", ... "dataset_a 5") produced by a Google Drive multi-part
   export. The same (session_id, chunk_id) can physically exist in more than
   one of those folders. We dedupe on (session_id, chunk_id) and keep the
   first copy found, in a fixed folder order, so re-runs are deterministic.
2. A chunk is only usable if it has an events.jsonl. Chunks that are
   screenshots-only (no events.jsonl came through in whichever part we have)
   are recorded as "known but unloadable" rather than silently skipped, so
   coverage gaps are visible instead of hidden.

Usage:
    from data_loader import load_events, load_ground_truth, DATASET_A_ROOTS, DATASET_B_ROOTS

    events_a = load_events(DATASET_A_ROOTS)
    events_b = load_events(DATASET_B_ROOTS)
    gt_a     = load_ground_truth(DATASET_A_ROOTS)
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent

DATASET_A_ROOTS = [
    REPO_ROOT / "dataset_a",
    REPO_ROOT / "dataset_a 2",
    REPO_ROOT / "dataset_a 3",
    REPO_ROOT / "dataset_a 4",
    REPO_ROOT / "dataset_a 5",
]
DATASET_B_ROOTS = [REPO_ROOT / "dataset_b"]


def _iter_chunks(roots: list[Path]):
    """Yield (session_id, chunk_id, chunk_dir) for every chunk directory
    found under any of `roots`, deduplicated on (session_id, chunk_id) using
    first-seen-wins across the given root order."""
    seen: set[tuple[str, str]] = set()
    for root in roots:
        if not root.exists():
            continue
        for ses_dir in sorted(root.glob("ses_*")):
            if not ses_dir.is_dir():
                continue
            session_id = ses_dir.name
            for chunk_dir in sorted(ses_dir.glob("chunk_*")):
                if not chunk_dir.is_dir():
                    continue
                key = (session_id, chunk_dir.name)
                if key in seen:
                    continue
                seen.add(key)
                yield session_id, chunk_dir.name, chunk_dir


def load_events(roots: list[Path], verbose: bool = True) -> pd.DataFrame:
    """Flatten every events.jsonl found under `roots` into one DataFrame,
    one row per event, with the nested JSON pulled out into flat columns
    that matter for segmentation/EDA. Raw payload is kept as a dict in
    `payload` for anything not promoted to its own column.
    """
    rows = []
    n_chunks_seen = 0
    n_chunks_missing_events = 0

    for session_id, chunk_id, chunk_dir in _iter_chunks(roots):
        n_chunks_seen += 1
        events_path = chunk_dir / "events.jsonl"
        if not events_path.exists():
            n_chunks_missing_events += 1
            continue

        with events_path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)

                ctx = d.get("context") or {}
                active_app = ctx.get("active_app") or {}
                browser_tab = ctx.get("active_browser_tab") or {}
                corr = d.get("correlation") or {}
                src = d.get("source") or {}
                payload = d.get("payload") or {}

                rows.append({
                    "event_id": d.get("event_id"),
                    "session_id": d.get("session_id", session_id),
                    "chunk_id": corr.get("chunk_id", chunk_id),
                    "layer": d.get("layer"),
                    "event_type": d.get("event_type"),
                    "timestamp_ms": d.get("timestamp_ms"),
                    "timestamp_iso": d.get("timestamp_iso"),
                    "sequence_number": corr.get("sequence_number"),
                    "ms_since_last_event": corr.get("ms_since_last_event"),
                    "triggered_by": corr.get("triggered_by"),
                    "machine_id": src.get("machine_id"),
                    "username_hash": src.get("username_hash"),
                    "app_name": active_app.get("app_name"),
                    "process_name": active_app.get("process_name"),
                    "window_title": active_app.get("window_title"),
                    "browser_url": browser_tab.get("url"),
                    "browser_tab_title": browser_tab.get("title"),
                    "extracted_text": ctx.get("extracted_text"),
                    "payload": payload,
                })

    df = pd.DataFrame(rows)
    if not df.empty:
        df["timestamp_iso"] = pd.to_datetime(df["timestamp_iso"], utc=True)
        df = df.sort_values(["session_id", "timestamp_ms"]).reset_index(drop=True)

    if verbose:
        print(f"[data_loader] chunks found: {n_chunks_seen}, "
              f"missing events.jsonl: {n_chunks_missing_events}, "
              f"events loaded: {len(df)}")

    return df


def load_ground_truth(roots: list[Path], verbose: bool = True) -> pd.DataFrame:
    """Flatten gt.jsonl for every session under `roots` that has one.
    Returns an empty DataFrame if none are found (expected for dataset_b,
    and currently also for dataset_a until the JSON-only parts are added)."""
    rows = []
    seen_sessions: set[str] = set()

    for root in roots:
        if not root.exists():
            continue
        for ses_dir in sorted(root.glob("ses_*")):
            if ses_dir.name in seen_sessions:
                continue
            gt_path = ses_dir / "gt.jsonl"
            if not gt_path.exists():
                continue
            seen_sessions.add(ses_dir.name)
            with gt_path.open(encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    d = json.loads(line)
                    d["session_id"] = ses_dir.name
                    rows.append(d)

    df = pd.DataFrame(rows)
    if verbose:
        print(f"[data_loader] gt.jsonl found for {len(seen_sessions)} session(s), "
              f"{len(df)} ground-truth events loaded")
    return df


def session_inventory(roots: list[Path]) -> pd.DataFrame:
    """One row per session: chunk count, whether events.jsonl exists for
    every one of its chunks, and whether gt.jsonl/gt_manifest.json exist.
    Use this before touching the data to see exactly what's usable."""
    seen_chunks: dict[str, list[tuple[str, bool]]] = {}
    for session_id, chunk_id, chunk_dir in _iter_chunks(roots):
        has_events = (chunk_dir / "events.jsonl").exists()
        seen_chunks.setdefault(session_id, []).append((chunk_id, has_events))

    rows = []
    for root in roots:
        if not root.exists():
            continue
        for ses_dir in sorted(root.glob("ses_*")):
            sid = ses_dir.name
            if sid not in seen_chunks:
                continue
            chunks = seen_chunks.pop(sid)  # only report once
            rows.append({
                "session_id": sid,
                "n_chunks": len(chunks),
                "n_chunks_with_events": sum(1 for _, ok in chunks if ok),
                "has_gt": (ses_dir / "gt.jsonl").exists(),
                "has_gt_manifest": (ses_dir / "gt_manifest.json").exists(),
            })
    return pd.DataFrame(rows).sort_values("session_id").reset_index(drop=True)


if __name__ == "__main__":
    print("=== Dataset A inventory ===")
    inv_a = session_inventory(DATASET_A_ROOTS)
    print(inv_a.to_string(index=False))
    print(f"\nfully usable sessions (all chunks have events.jsonl): "
          f"{(inv_a.n_chunks == inv_a.n_chunks_with_events).sum()} / {len(inv_a)}")

    print("\n=== Dataset B inventory ===")
    inv_b = session_inventory(DATASET_B_ROOTS)
    print(inv_b.to_string(index=False))
    print(f"\nfully usable sessions: "
          f"{(inv_b.n_chunks == inv_b.n_chunks_with_events).sum()} / {len(inv_b)}")
