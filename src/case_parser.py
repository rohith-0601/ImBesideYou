"""
Parse completion comments into structured case records.

Each execution recovered on Day 2 ends with a completion comment that the
worker writes into the screen's comment field. Those comments are strictly
templated, one template per process, with the case's details in slots:

    請求書照合完了。INV-2026-7347　金額：1,832,962円。差異なし承認。
    給与変更登録。変更種別：残業手当調整。適用日：2026-07-06。確認完了。
    発注管理処理。スポット発注：梱包材料　数量 164　合計 6,314,164円　通常。発注書確認・登録完了。
    契約管理処理。種別：保守委託契約 (更新)。期日：2026-07-05。関連書類確認済み。

This makes Step 2 answerable directly rather than by inference: the template
names the process, a slot names the **variant** (the README's "different
handling patterns within the same process"), and some templates carry the
**decision outcome**, which is what determines whether a process can be
automated end-to-end or only prepared for a human.

The template also corrects the label
-------------------------------------
Day 2 labelled each execution from the forward-filled (system, route) pair.
That is reliable while a URL is live — template and label agree on
**415/419 (99.0%)** of such markers. It is *not* reliable when the comment is
written in Notepad or Excel, which have no URL: there the label is inherited
from whichever portal screen preceded, and agreement falls to **41/62
(66.1%)**.

Since the comment states which process it belongs to, it outranks an
inherited context. `corrected_label` applies that. Across the 601 executions
it changes 133 labels, of which 108 are the HR screen split above (a
refinement, not a correction) and 25 are genuine context mislabels.

Two values are dropped as non-comments: bare spreadsheet numbers
(`-4.366847059`) captured from Excel cells during budget variance work.
"""

from __future__ import annotations

import re

import pandas as pd

# Template -> process. Ordered; first match wins. The Notepad scratch-memo
# forms (精算確認メモ, IT申請メモ, 在庫調整メモ) are folded into the same
# process as their portal equivalents.
TEMPLATES: list[tuple[str, str]] = [
    ("fin_invoice_matching",          r"請求書照合完了"),
    ("fin_expense_approval",          r"経費承認（管理職）"),
    ("fin_payment_processing",        r"支払処理確認"),
    ("fin_purchase_order_management", r"発注管理処理"),
    ("fin_budget_variance_analysis",  r"予算差異分析完了"),
    ("hr_leave_application",          r"勤怠申請確認"),
    ("hr_onboarding_verification",    r"入社照合完了"),
    ("hr_welfare_application",        r"福利厚生申請処理完了"),
    # One HR screen hosts two genuinely different processes, distinguishable
    # by their own templates: a payroll master change (給与変更登録) versus an
    # employee expense settlement check (経費精算確認済み / the 精算確認メモ
    # Notepad form). They have different inputs, different approvers and very
    # different automation profiles, so they are separated here rather than
    # counted as one 111-execution process with ten "variants".
    ("hr_payroll_change",             r"給与変更登録"),
    ("hr_expense_settlement",         r"経費精算確認済み|精算確認メモ"),
    ("inv_contract_management",       r"契約管理処理"),
    ("inv_it_request_processing",     r"IT申請"),
    ("inv_stock_adjustment",          r"在庫調整"),
]

# Variant slot per process. The group named `v` is the handling pattern.
VARIANT_RE: dict[str, re.Pattern] = {
    "fin_invoice_matching":          re.compile(r"(?P<v>差異なし承認|差異あり要確認)"),
    "fin_expense_approval":          re.compile(r"費目：(?P<v>[^\s　]+)"),
    "fin_purchase_order_management": re.compile(r"。(?P<v>スポット発注|年間契約|定期発注|緊急発注)"),
    "fin_payment_processing":        re.compile(r"工程：(?P<v>[^。]+)。"),
    "fin_budget_variance_analysis":  re.compile(r"完了。(?P<v>[^\s　]+?部)"),
    "hr_leave_application":          re.compile(r"種別：(?P<v>[^。]+?)。"),
    "hr_onboarding_verification":    re.compile(r"採用区分：(?P<v>[^。]+?)。"),
    "hr_welfare_application":        re.compile(r"種別：(?P<v>[^。]+?)。"),
    "hr_payroll_change":             re.compile(r"変更種別[：:]\s*(?P<v>[^。\s　]+)"),
    "hr_expense_settlement":         re.compile(r"費目[：:]\s*(?P<v>[^。\s　]+)"),
    "inv_contract_management":       re.compile(r"種別：(?P<v>[^。]+?)。"),
    # Portal form is 申請種別：X。; the Notepad memo form puts X straight
    # after the header with no label, so both shapes are matched.
    "inv_it_request_processing":     re.compile(
        r"申請種別：(?P<v>[^。]+?)。|IT申請メモ\s*(?P<v2>\S+?申請)"),
    # 区分 (返品入庫 / 棚卸調整 / 出荷引当) is the handling pattern; 品名 is
    # the subject of the case. Prefer 区分, fall back to the product name.
    "inv_stock_adjustment":          re.compile(
        r"区分：(?P<v>[^\s\r]+)|品名：(?P<v2>[^\s　]+)"),
}

AMOUNT_RE = re.compile(r"(?:金額：|合計\s*|振込\s*¥?)([\d,]+)\s*円?")
CASE_ID_RE = re.compile(r"(INV-\d{4}-\d{3,5}|P\d{1,2}-\d{6,9}-\d{2,4}|BATCH-[A-Z]\d+)")
DATE_RE = re.compile(r"(?:適用日|取得日|期日)：(\d{4}-\d{2}-\d{2})")
QTY_RE = re.compile(r"(?:数量|調整数)\s*(?P<q>[+\-]?\d+)")

# Outcomes that mean "a human had to judge something" vs "routine".
EXCEPTION_MARKERS = ("差異あり要確認", "緊急", "要確認", "差戻")


def template_label(text: str) -> str | None:
    for label, pattern in TEMPLATES:
        if re.search(pattern, text):
            return label
    return None


def _variant(label: str | None, text: str) -> str | None:
    if not label:
        return None
    rx = VARIANT_RE.get(label)
    if not rx:
        return None
    m = rx.search(text)
    if not m:
        return None
    d = m.groupdict()
    return d.get("v") or d.get("v2")


def parse_comment(text: str) -> dict:
    """Structured fields from one completion comment."""
    t = " ".join(text.split())
    label = template_label(t)
    amount = AMOUNT_RE.search(t)
    case = CASE_ID_RE.search(t)
    date = DATE_RE.search(t)
    qty = QTY_RE.search(t)
    return {
        "template_label": label,
        "variant": _variant(label, t),
        "amount_yen": int(amount.group(1).replace(",", "")) if amount else None,
        "case_ref": case.group(1) if case else None,
        "effective_date": date.group(1) if date else None,
        "quantity": int(qty.group("q")) if qty else None,
        "is_exception": any(k in t for k in EXCEPTION_MARKERS),
    }


def parse_markers(markers: pd.DataFrame) -> pd.DataFrame:
    """Add parsed fields to a completion-marker frame and drop non-comments."""
    if markers.empty:
        return markers
    parsed = pd.DataFrame([parse_comment(c) for c in markers.comment])
    out = pd.concat([markers.reset_index(drop=True), parsed], axis=1)
    dropped = out.template_label.isna().sum()
    if dropped:
        out = out[out.template_label.notna()].reset_index(drop=True)
    out.attrs["dropped_non_comments"] = int(dropped)
    # The comment names its own process; an inherited context does not.
    out["corrected_label"] = out["template_label"]
    out["label_corrected"] = out["template_label"] != out["process_label"]
    return out


if __name__ == "__main__":
    from data_loader import DATASET_B_ROOTS, load_events
    from executions import completion_markers
    from process_context import annotate

    ev = annotate(load_events(DATASET_B_ROOTS))
    m = parse_markers(completion_markers(ev))
    print(f"\nparsed executions: {len(m)}  "
          f"(dropped {m.attrs['dropped_non_comments']} non-comment values)")
    print(f"labels corrected from the comment template: "
          f"{int(m.label_corrected.sum())} ({100 * m.label_corrected.mean():.1f}%)")
    print(f"variant extracted: {100 * m.variant.notna().mean():.1f}%")
    print(f"amount extracted : {100 * m.amount_yen.notna().mean():.1f}%")
    print("\n=== executions and variants per process ===")
    for lab, g in m.groupby("corrected_label"):
        print(f"\n{lab}  n={len(g)}  exceptions={int(g.is_exception.sum())}")
        print("   " + ", ".join(f"{v}×{c}" for v, c in
                                g.variant.value_counts().head(8).items()))
