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

## 5. Replay: the first verifiable accuracy number

Every evaluation up to here has been structural — does the segmentation tile
the session, does the label agree with an independent process code, can a
comment slot be filled. None of it answers what a client asks first: *if this
had been running during those 15 sessions, would it have been right?*

That is answerable, because the operators left their answers behind. Each of
the 601 recovered executions ends with the comment its worker wrote; the tool
drafts a comment from the same record; the two compare character for
character. `src/replay.py` does exactly that.

| outcome | n |
|---|---|
| `exact` | 189 |
| `exact_in_memo` | 15 |
| `mismatch` | **1** |
| `no_draft` (declined by design) | 103 |
| `record_not_linked` | 17 |
| `not_configured` (the 8 other processes) | 276 |

**Comment accuracy where the tool drafted: 204 / 205 = 99.5%.**
308 of 325 executions on configured processes linked to a portal record.

Per process, the shape is exactly what the definitions predict:

| process | exact | declined | note |
|---|---|---|---|
| `fin_invoice_matching` | 42 | 22 | declines are the 調整 exceptions |
| `hr_expense_settlement` | 76 | 13 | 15 of the 76 were written as Notepad memos |
| `inv_contract_management` | 32 | 0 | |
| `hr_leave_application` | 54 | 0 | |
| `fin_purchase_order_management` | 0 | 68 | cannot draft from the list at all |

**This is the only measured accuracy figure in the project.** `gt.jsonl` never
arrived, so Step 1 boundary accuracy remains unmeasurable — but comment
accuracy did not have to stay that way, and it is a more direct measure of
whether the tool does the job than any of the internal checks.

### Two things the first run got wrong

- **It reported 0.0% accuracy.** Every match was scored a mismatch because
  some operators write the completion text into Notepad first, as
  `精算確認メモ / P1-07109774-002 / 経費精算確認済み。費目：…`. The business
  sentence inside is identical; the header and ID are the operator's own
  scaffolding. Scored as `exact_in_memo` and counted as correct, with the
  reasoning stated rather than silently relaxed.
- **It linked 17 of 601 executions.** Most completion comments name the case
  only in prose, so an ID lookup finds almost nothing. Linking on
  (process, variant, amount, date) — what actually identifies a row on these
  screens — took it to 308. One bug inside that: `variant_map` stores the
  comment phrase *with* its trailing 。 and the parsed variant has none, so
  every invoice execution failed to link until both sides were stripped.

The single remaining mismatch is not a tool error: it is one segment holding
two consecutive leave approvals, so the actual text is two comments
concatenated. That is a Step 1 segmentation artefact, and at 1 in 205 it is
not worth chasing.

## 6. The blocked process was not blocked — it was one fetch away

Day 4 scored `fin_purchase_order_management` **0 of 81** because the order type
that decides its branch is not on the list screen. That was right about the
list and wrong about the portal.

When an operator opens a record the portal renders a **detail pane**, and
eight of those were captured in `context.extracted_text`. `src/detail_panes.py`
parses them. The purchase-order pane carries exactly what the list does not:

```
詳細 — P10-07054374-004        未確認
name          沖縄物流センター
emp_id        V3008
variant       V1_routine_po
procedure     発注管理 PO-2026-5097
reason        定期発注：電子基板ユニット　数量 176　合計 842,336円　通常
```

`reason` is not merely a missing field. It is the **entire body of the
completion comment**:

```
発注管理処理。定期発注：電子基板ユニット　数量 176　合計 842,336円　通常。発注書確認・登録完了。
              └──────────────────── reason, verbatim ────────────────────┘
```

Checked against every recorded execution: **68 of 68** purchase-order comments
decompose to `発注管理処理。{reason}。発注書確認・登録完了。`, and 61 of those
reasons carry the exact shape of the captured pane. So with one per-record
fetch this process is a string substitution, not a judgement — the same
conclusion Day 4 reached about `fin_invoice_matching`, arrived at the same way:
by looking at what the portal actually renders rather than at what the list
shows.

### The 7 that did not fit revealed a variant nobody had seen

The other 7 of 68 all look like this:

```
発注変更：事務用品　数量 87　合計 3,206,385円　要注意
```

**発注変更** ("order change") is a **fifth order type**, and **要注意**
("requires attention") is a **third urgency value** — neither appears anywhere
in the list view, which has no urgency column at all. They were invisible
until the completion comments were parsed. 要注意 is now a second exception arm
alongside 緊急, so those 7 route to a person.

This is the argument for parsing what operators write rather than only what
the screen shows: a whole branch of the process existed outside the columns.

### Reframed, not solved

`field_audit.py` now distinguishes a fetch contract that is **specified** from
one that is **unknown**:

| process | executions | fetch contract |
|---|---|---|
| `fin_purchase_order_management` | 68 | **specified** |
| `fin_payment_processing` | 36 | unknown |
| `hr_onboarding_verification` | 31 | unknown |

**68 of those 135 executions are an integration task with a known shape**, not
a blocked process. The definition now carries a `detail_source` block naming
the field, what it fills, the evidence behind it, and — honestly — its status:
*specified, not implemented*. Only one pane was captured, so the mock cannot
serve 81 details, and the real endpoint has still never been seen.

The process-definition validator was extended to enforce this: a field may
come from a list column **or** a declared `detail_source`, but a template slot
with no stated source is now a validation error. It caught two mistakes in the
new definition while I was writing it — an exception field with no source, and
`urgency`, which is parsed out of the composite `reason` string rather than
returned on its own.

## 7. Carried into Day 6

- Measure coverage honestly: of the 484 pending records, what share does the
  tool actually complete end to end, and how much operator time does the
  review still require?
- Write the two sections the README names specifically — residual manual work
  with realistic expected impact, and anticipated rollout risks with
  mitigations, each tied to its evidence.
- Decide whether `fin_purchase_order_management`, `fin_payment_processing`
  and `hr_onboarding_verification` justify building the per-record fetch, or
  stay out of phase one.
