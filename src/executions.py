"""
Per-case execution boundaries inside a process episode.

Why this exists
---------------
`segment.py` recovers *episodes*: contiguous stretches of work in one process
context. But an episode routinely contains several executions of the same
process — the invoice clerk works INV-2026-7345, then -7347, then -7348,
without ever leaving the screen. The README asks for "individual executions
of business processes", and dataset A's `gt_manifest.json` schema confirms the
granularity: `executions[]` is "one entry per execution of that process",
each with its own `case_id`.

Measured: 162 episodes contain **656** execution-completion markers, a median
of 3-4 per episode. Emitting episodes alone under-segments by roughly 3x.

The marker
----------
Every process ends each case by writing a completion comment into the
screen's comment field, and the text names the case:

    請求書照合完了。INV-2026-7347　金額：1,832,962円。差異なし承認。
    給与変更登録。変更種別：残業手当調整。適用日：2026-07-02。確認完了。
    発注管理処理。スポット発注：梱包材料　数量 164　合計 6,314,164円　通常。発注書確認・登録完了。
    在庫調整登録。品番：BATCH-W2　品名：電源モジュールB　調整数：+155個。
    入社照合完了。採用区分：新卒。照合項目すべて確認済み。

These arrive on `payload.target_field.value` (keystroke) and
`payload.target_element.value` (mouse_click). Detection is deliberately
*structural* rather than keyword-based — an early version keyed on
完了|承認|済み and missed `inv_stock_adjustment` almost entirely (8 markers
instead of 82), because stock adjustments are logged as memos with no
completion verb. The rule used instead: a field value long enough to be a
real comment, that is not the field's placeholder text.

Placeholders are distinguishable because they all end in an ellipsis:

    処理内容・確認コメントを入力してください…
    承認コメントまたは差戻し理由を入力してください…

Safe to deduplicate by text
---------------------------
`target_field.value` on a keystroke carries the field's *current* value, so
progressive typing would produce partial prefixes and inflate the count.
Checked: across a full session's 86 long values, **zero** are a strict prefix
of a nearby later value. The comments are pasted rather than typed
character-by-character (hence the accompanying `clipboard_change` events), so
each distinct text is one completed case.
"""

from __future__ import annotations

import pandas as pd

from process_context import _dig

MIN_COMMENT_LEN = 12
VALUE_PATHS = (("target_field", "value"), ("target_element", "value"))


def _is_comment(text: str) -> bool:
    t = text.strip()
    if len(t) < MIN_COMMENT_LEN:
        return False
    if t.endswith("…") or t.endswith("..."):
        return False          # placeholder, not a completed case
    if t.startswith("http://") or t.startswith("https://"):
        return False          # URL leaking through an element value
    return True


def completion_markers(events: pd.DataFrame) -> pd.DataFrame:
    """One row per completed case execution: the moment its comment first
    appears, with the comment text as the case's identity."""
    rows = []
    for r in events.to_dict("records"):
        p = r.get("payload") or {}
        for path in VALUE_PATHS:
            v = _dig(p, *path)
            if isinstance(v, str) and _is_comment(v):
                rows.append({
                    "session_id": r["session_id"],
                    "timestamp_ms": r["timestamp_ms"],
                    "process_label": r.get("process_label"),
                    "comment": v.strip(),
                    "source": ".".join(path),
                })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    # First appearance of each distinct comment within a session+process.
    df = (df.sort_values("timestamp_ms")
            .drop_duplicates(subset=["session_id", "process_label", "comment"],
                             keep="first")
            .reset_index(drop=True))
    return df


def split_segment(seg: dict, markers: pd.DataFrame) -> list[dict]:
    """Split one episode into per-case executions at its completion markers.

    Execution *i* runs from the previous marker (or the episode start) to
    marker *i*. Any tail after the last marker is attached to the final
    execution, so the split conserves the episode's span exactly: no time is
    created or lost, and the results stay non-overlapping.

    An episode with no marker is returned unchanged as a single execution —
    7 of 162 episodes, mostly short ones where the worker left before
    completing a case.
    """
    m = markers[(markers.session_id == seg["session_id"])
                & (markers.timestamp_ms >= seg["start_ms"])
                & (markers.timestamp_ms <= seg["end_ms"])]
    if m.empty:
        out = dict(seg)
        out["n_executions"] = 0
        out["case_comment"] = None
        return [out]

    out = []
    cursor = seg["start_ms"]
    times = m.timestamp_ms.tolist()
    comments = m.comment.tolist()
    for i, (t, c) in enumerate(zip(times, comments)):
        last = i == len(times) - 1
        out.append({
            **seg,
            "start_ms": cursor,
            "end_ms": seg["end_ms"] if last else t,
            "n_executions": 1,
            "case_comment": c,
        })
        cursor = t
    return out


if __name__ == "__main__":
    from data_loader import DATASET_B_ROOTS, load_events
    from process_context import annotate

    ev = annotate(load_events(DATASET_B_ROOTS))
    m = completion_markers(ev)
    print(f"\ncompletion markers: {len(m)}")
    print("\n=== per process ===")
    print(m.groupby("process_label").agg(
        executions=("comment", "size"),
        sessions=("session_id", "nunique"),
    ).sort_values("executions", ascending=False).to_string())
    print("\n=== by source path ===")
    print(m.source.value_counts().to_string())
