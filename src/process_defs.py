"""
Per-process definitions — the config that makes the Step 3 tool general.

Day 3's scope decision was a shared review-and-approve foundation with
per-process definitions, on the grounds that all twelve processes have the
same shape: select a pending record, check it against a rule, write a
templated completion comment, submit. The definition below is what "a process"
means to that tool, so adding the fourth process is a JSON file rather than a
code change.

Every field is grounded in recorded evidence, not invented:

  screen / columns / states / transition / confirmation
      from `portal_contract.py`, reconstructed from 939 screen dumps
  comment_template / variants
      from `case_parser.py`, the completion comments workers actually wrote
  exception_field / exception_values
      from the Day 3-4 branch analysis (種別 for invoices, 発注区分 for POs)

Deliberately *not* encoded: the policy thresholds. Every observed expense case
was approved, so the data shows ranges and never a limit — those have to come
from the client as configuration. The `rule` field records what is checked and
leaves the bound null.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFS_DIR = REPO_ROOT / "portal" / "processes"

DEFINITIONS = {
    "hr_leave_application": {
        "label": "hr_leave_application",
        "display_name": "勤怠・休暇申請",
        "system": {"name": "HR人事給与システム", "port": "5132"},
        "route": "#/leave-applications",
        "columns": ["ID", "社員ID", "氏名", "申請種別", "期間・詳細", "部署", "ステータス"],
        "states": {"pending": "申請中", "done": "承認"},
        "transition": "申請中 -> 承認",
        "transitions_observed": 23,
        "confirmation": "申請を承認しました",
        "comment_template": "勤怠申請確認。種別：{variant}。取得日：{date}。問題なし承認。",
        "variant_field": "申請種別",
        "variants": ["年次有給休暇", "特別休暇（慶弔）", "代休申請",
                     "半日有給申請", "フレックス変更申請"],
        "exception_field": None,
        "exception_values": [],
        "rule": {
            "checks": ["申請種別 is a recognised leave type",
                       "期間・詳細 is a valid future date"],
            "threshold": None,
            "note": "No exceptions observed across 56 executions.",
        },
        "evidence": {"executions": 56, "operators": 3,
                     "browser_only_share": 0.964, "exception_rate": 0.0},
    },
    "hr_expense_settlement": {
        "label": "hr_expense_settlement",
        "display_name": "経費精算（確認）",
        "system": {"name": "HR人事給与システム", "port": "5132"},
        "route": "#/payroll-items",
        "columns": ["ID", "社員ID", "氏名", "区分", "金額", "種別", "ステータス"],
        "states": {"pending": "未処理", "done": "登録済み"},
        "transition": "未処理 -> 登録済み",
        "transitions_observed": 83,
        "confirmation": "登録確定しました",
        "comment_template": "経費精算確認済み。費目：{variant}　金額：{amount}円。規程内であることを確認した。",
        "variant_field": "区分",
        "variants": ["交通費精算", "出張旅費", "消耗品費", "研修費", "接待交際費"],
        "exception_field": "種別",
        "exception_values": ["調整"],
        "rule": {
            "checks": ["金額 is within the policy limit for 区分"],
            "threshold": None,
            "note": ("Observed amounts per category are 交通費精算 5,083-24,395; "
                     "消耗品費 4,354-29,889; 研修費 11,116-55,571; "
                     "出張旅費 21,956-79,409; 接待交際費 60,936-135,181. These "
                     "are observed RANGES, not limits — every recorded case "
                     "was approved, so no rejection boundary is visible. "
                     "Limits must be supplied by the client."),
        },
        "evidence": {"executions": 90, "operators": 3,
                     "browser_only_share": 0.567, "exception_rate": 0.0},
    },
    # Added on Day 4 after the field audit. This process was deferred twice —
    # on Day 3 as "irreducible judgement", on Day 4 as "desktop-heavy" — and
    # both reasons turned out to be wrong:
    #
    #   * 種別 (定常/調整) predicts the 差異 outcome 64/64, and it is an
    #     *input*: populated on 未処理 rows and unchanged across 108 records
    #     observed more than once. So the branch is decided before the work.
    #   * every slot its comment needs resolves from the list row.
    #
    # Its low browser-only share (25%) measures how the *human* did the check
    # — the Excel and Word detour — which is the work the tool removes, not a
    # barrier to removing it. It is the largest process by time in the whole
    # dataset.
    "fin_invoice_matching": {
        "label": "fin_invoice_matching",
        "display_name": "請求書承認・経費精算",
        "system": {"name": "財務会計システム", "port": "5133"},
        "route": "#/payroll-items",
        "columns": ["ID", "社員ID", "氏名", "区分", "金額", "種別", "ステータス"],
        "states": {"pending": "未処理", "done": "登録済み"},
        "transition": "未処理 -> 登録済み",
        "transitions_observed": 46,
        "confirmation": "登録確定しました",
        "comment_template": "請求書照合完了。{case}　金額：{amount}円。{variant}",
        "variant_field": "種別",
        "variant_map": {"定常": "差異なし承認。", "調整": "差異あり要確認。"},
        "variants": ["定常", "調整"],
        "exception_field": "種別",
        "exception_values": ["調整"],
        "rule": {
            "checks": ["種別 決定 the 差異 outcome: 定常 -> 差異なし承認, "
                       "調整 -> 差異あり要確認"],
            "threshold": None,
            "note": ("種別 predicts the recorded outcome 64/64 and is set "
                     "before the work (populated on 未処理 rows, never "
                     "changes). 調整 cases are still routed to a human — the "
                     "correlation is strong but 64 observations is a modest "
                     "sample and nothing in the logs says what sets 種別 "
                     "upstream."),
        },
        "evidence": {"executions": 64, "operators": 4,
                     "browser_only_share": 0.250, "exception_rate": 0.344},
    },
    # Added on Day 5 when the corrected ranking moved it from #8 to #3. All
    # of its comment slots resolve from the list screen (申請種別, 期間・詳細),
    # and it is the second-largest process by time in the dataset.
    #
    # Caveat carried into the UI: the comment ends 関連書類確認済み ("related
    # documents confirmed"), and the portal names a .docx the operator is
    # expected to open — Day 3 measured 1,087 Word events on this process.
    # The tool can draft the sentence; it cannot confirm the document. That
    # confirmation is exactly what the human step is for.
    "inv_contract_management": {
        "label": "inv_contract_management",
        "display_name": "契約管理",
        "system": {"name": "受発注在庫管理システム", "port": "5134"},
        "route": "#/leave-applications",
        "columns": ["ID", "社員ID", "氏名", "申請種別", "期間・詳細", "部署",
                    "ステータス"],
        "states": {"pending": "処理待ち", "done": "承認"},
        "transition": "処理待ち -> 承認",
        "transitions_observed": 28,
        "confirmation": "処理完了しました",
        "comment_template": "契約管理処理。種別：{variant}。期日：{date}。関連書類確認済み。",
        "variant_field": "申請種別",
        "variants": ["取引基本契約 (新規締結)", "秘密保持契約 (新規締結)",
                     "保守委託契約 (更新)", "売買契約 (変更)",
                     "業務委託契約 (解除)"],
        "exception_field": None,
        "exception_values": [],
        "requires_document_check": True,
        "rule": {
            "checks": ["関連書類 (the named .docx) must be opened and checked "
                       "by a person before approval"],
            "threshold": None,
            "note": ("No exception variant was observed across 47 executions. "
                     "The document check is not automatable from the logs — "
                     "the portal names the file but its contents were never "
                     "captured."),
        },
        "evidence": {"executions": 47, "operators": 4,
                     "browser_only_share": 0.170, "exception_rate": 0.0},
    },
    "fin_purchase_order_management": {
        "label": "fin_purchase_order_management",
        "display_name": "発注管理",
        "system": {"name": "財務会計システム", "port": "5133"},
        "route": "#/resident-tax",
        "columns": ["ID", "社員ID", "氏名", "項目", "金額", "ステータス"],
        "states": {"pending": "未確認", "done": "完了"},
        "transition": "未確認 -> 完了",
        "transitions_observed": 26,
        "confirmation": "完了しました",
        "comment_template": ("発注管理処理。{variant}：{item}　数量 {qty}　"
                             "合計 {amount}円　{urgency}。発注書確認・登録完了。"),
        # The list view carries only the PO number in 項目 ("発注管理
        # PO-2026-5156"). The order type that determines the branch is NOT
        # exposed there — it appears only in the completion comment, i.e.
        # after the worker has opened the record. So the variant cannot be
        # read from the list, and the tool must open each record to classify
        # it. Caught by validate(); recorded rather than papered over.
        "variant_field": None,
        "variant_source": "record_detail",
        "variants": ["年間契約", "スポット発注", "定期発注", "緊急発注"],
        "exception_field": None,
        "exception_values": ["緊急発注"],
        "rule": {
            "checks": ["発注区分 determines routing",
                       "緊急発注 is flagged for expedited handling"],
            "threshold": None,
            "note": ("Exception rate by variant is exactly 1.0 for 緊急発注 "
                     "and 0.0 for the other three, so the branch is a "
                     "labelled property of the order. But it is not visible "
                     "in the list view, so it is known only after opening "
                     "the record — a per-record fetch the other two "
                     "processes do not need. Day 5 build risk."),
        },
        "evidence": {"executions": 68, "operators": 4,
                     "browser_only_share": 0.735, "exception_rate": 0.132},
    },
}

REQUIRED_FIELDS = {
    "label", "display_name", "system", "route", "columns", "states",
    "transition", "confirmation", "comment_template", "variant_field",
    "variants", "rule", "evidence",
}


def validate(defn: dict) -> list[str]:
    """Problems with a definition, empty if it is usable."""
    problems = []
    missing = REQUIRED_FIELDS - set(defn)
    if missing:
        problems.append(f"missing fields: {sorted(missing)}")
    st = defn.get("states", {})
    if set(st) != {"pending", "done"}:
        problems.append("states must be exactly {pending, done}")
    elif defn.get("transition") != f"{st['pending']} -> {st['done']}":
        problems.append("transition does not match states")
    if defn.get("variant_field") and defn["variant_field"] not in defn.get("columns", []):
        problems.append(f"variant_field {defn['variant_field']!r} "
                        f"is not one of the screen's columns")
    ex = defn.get("exception_field")
    if ex and ex not in defn.get("columns", []):
        problems.append(f"exception_field {ex!r} is not one of the "
                        f"screen's columns")
    tpl = defn.get("comment_template", "")
    if "{variant}" not in tpl:
        problems.append("comment_template has no {variant} slot")
    # A process whose variant is not a list column must say where it comes
    # from instead, so the tool knows it needs a per-record fetch.
    if defn.get("variant_field") is None and not defn.get("variant_source"):
        problems.append("variant_field is null but no variant_source given")
    return problems


def write_all() -> None:
    DEFS_DIR.mkdir(parents=True, exist_ok=True)
    for name, defn in DEFINITIONS.items():
        (DEFS_DIR / f"{name}.json").write_text(
            json.dumps(defn, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    write_all()
    print(f"wrote {len(DEFINITIONS)} process definitions -> "
          f"{DEFS_DIR.relative_to(REPO_ROOT)}/\n")
    ok = True
    for name, defn in DEFINITIONS.items():
        problems = validate(defn)
        status = "OK" if not problems else "PROBLEMS"
        print(f"{status:9s} {name}")
        for p in problems:
            print(f"          - {p}")
            ok = False
    print("\nall definitions valid" if ok else "\nfix the problems above")
