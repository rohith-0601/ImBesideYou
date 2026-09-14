# Day 5 — Corrected ranking, revised scope, and the operator tool

---

## 1. The ranking, rebuilt

Day 4 found two faults in the Day 3 score, both by building the thing and
watching it fail rather than by re-reading the formula:

1. **`data_access` measured the wrong subject.** It was the share of
   executions that stayed inside the browser — how the *human* did the work.
   `fin_invoice_matching` scores 25% there because the operator detours
   through Excel and Word to perform the check. But the outcome is already
   determined by a field on the record, so that detour is precisely what the
   tool removes. Penalising a process for the manual effort you intend to
   delete is backwards.
2. **Field visibility was absent entirely.** Nothing asked whether the field
   that decides the branch is on the screen the tool reads.
   `fin_purchase_order_management` ranked **first** and is **0 of 81**
   automatable for exactly that reason.

`data_access` is now `draftable` — the share of a process's completion-comment
slots that resolve from a list row, measured by `field_audit.py`. That is the
condition `server/assist.js` actually applies, so the score and the tool
answer the same question.

| # | process | exec | total s | draftable | opportunity | was |
|---|---|---|---|---|---|---|
| 1 | `fin_invoice_matching` | 64 | 1,288 | 1.00 | **0.721** | #5 ↑4 |
| 2 | `hr_expense_settlement` | 90 | 972 | 1.00 | 0.587 | #3 ↑1 |
| 3 | `inv_contract_management` | 47 | 1,186 | 1.00 | 0.487 | #8 ↑5 |
| 4 | `hr_leave_application` | 56 | 690 | 1.00 | 0.364 | #2 ↓2 |
| 5 | `inv_stock_adjustment` | 81 | 827 | 0.67 | 0.245 | #4 ↓1 |
| … | | | | | | |
| 11 | `fin_purchase_order_management` | 68 | 864 | **0.00** | 0.025 | **#1 ↓10** |
| 12 | `hr_onboarding_verification` | 31 | 1,131 | 0.00 | 0.022 | #9 ↓3 |
| 13 | `fin_payment_processing` | 36 | 676 | 0.00 | 0.015 | #7 ↓6 |

The moves are large because the fault was structural, not a rounding
difference. `fin_purchase_order_management` falls ten places; the three
processes at the bottom are the three that cannot be drafted at all.

**One further consequence worth stating:** after Day 4 corrected
`fin_invoice_matching`'s exceptions from *judgement* to *predictable*, **no
process in dataset B has judgement exceptions left**. Every branch observed in
15 sessions is decided by a field that exists on the record before the work
starts. That is a much stronger claim for automatability than Day 3 made, and
it rests on the 種別 input test in `field_audit.field_is_an_input`.

## 2. Scope revised

Configured processes are now the top four by the corrected score, plus one
kept deliberately:

| process | pending | drafted | needs a person |
|---|---|---|---|
| `hr_expense_settlement` | 213 | 84 | 129 |
| `fin_invoice_matching` | 86 | 54 | 32 |
| `inv_contract_management` | 64 | **64** | 0 |
| `hr_leave_application` | 40 | **40** | 0 |
| `fin_purchase_order_management` | 81 | **0** | 81 |
| **total** | **484** | **242 (50%)** | 242 |

**Added `inv_contract_management`** (#8 → #3): all slots resolve from the
list, 47 executions, second-largest by time. It carries a caveat the UI
surfaces on every record — its comment ends 関連書類確認済み ("related
documents confirmed") and the portal names a `.docx` the operator is expected
to open. Day 3 measured 1,087 Word events on this process. The tool drafts the
sentence; it cannot confirm the document, and says so.

**Kept `fin_purchase_order_management` despite ranking #11.** It costs one
config entry and it is the honest demonstration that the tool fails visibly:
81 records, none drafted, each stating why. The plan called for unhandled
cases to fail visibly rather than silently, and a process that *cannot* be
automated is the clearest possible test of that.

## 3. The tool

Three-pane operator layout: queues, records, detail. Built for someone working
several hundred cases in a sitting, so the design priorities are density,
keyboard reach and legibility of Japanese at small sizes.

- **Keyboard-first.** `J`/`K` move, `↵` approves and advances, `E` edits the
  drafted comment. The whole review loop runs without the mouse.
- **Blockers separated from notes.** A *blocker* is why a person must handle
  the case; a *note* is context they should see before approving. These were
  one list at first, which put "no policy threshold configured" under a
  heading saying the record needed attention — on records that were ready.
- **Bulk approve, behind a confirmation** showing the count and a sample of
  the sentence that will be written on every record. Each record is still
  submitted individually, because the portal has no batch endpoint and
  pretending otherwise would hide that a real integration makes N calls and
  can fail partway. **The batch stops at the first failure** rather than
  pressing on: a partial batch with a gap in the middle is harder to reconcile
  than one that stopped at a known point, and the portal's behaviour on a
  failed submit is unobserved.
- **Audit trail** of everything submitted this session, with timestamps and
  the portal's own confirmation string.
- Light and dark, reduced-motion honoured, focus rings, live regions for
  status.

## 4. What is still deliberately absent

**Auto-approval.** Nothing submits without an explicit action. Two reasons
from the data, not caution for its own sake:

- the submit *transport* is unverified (Day 4 §5) — we know what a submit does
  from 345 observed transitions, not how to make one safely;
- policy limits are unknown. Every observed expense case was approved, so the
  logs show ranges and never a threshold. The drafted comment asserts
  規程内であることを確認した ("confirmed within policy") and the tool has no
  policy to confirm against. A tool that auto-approved against an inferred
  limit would be inventing the rule it claims to enforce.

## 5. Carried into Day 6

- Measure coverage honestly: of the 484 pending records, what share does the
  tool actually complete end to end, and how much operator time does the
  review still require?
- Write the two sections the README names specifically — residual manual work
  with realistic expected impact, and anticipated rollout risks with
  mitigations, each tied to its evidence.
- Decide whether `fin_purchase_order_management`, `fin_payment_processing`
  and `hr_onboarding_verification` justify building the per-record fetch, or
  stay out of phase one.
