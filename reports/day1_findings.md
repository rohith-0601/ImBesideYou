# Day 1 — Findings

Curated conclusions from Day 1. The machine-generated statistics live in
[`day1_eda.md`](day1_eda.md); this file is the interpretation and the
decisions that follow from it.

---

## 1. Data availability: dataset A is unusable, dataset B is intact

| | README expects | On disk | Verdict |
|---|---|---|---|
| dataset_b sessions | 15 | 15 | ✅ complete |
| dataset_b events | ~20,000 | 20,477 | ✅ complete |
| dataset_b `events.jsonl` / `manifest.json` | 20 / 20 | 20 / 20 | ✅ complete |
| dataset_a sessions (dirs) | 63 | 63 | dirs only |
| dataset_a `events.jsonl` | ~100 | **4** | ❌ |
| dataset_a `manifest.json` | ~100 | **0** | ❌ |
| dataset_a `gt.jsonl` / `gt_manifest.json` | 63 / 63 | **0 / 0** | ❌ |

Dataset A arrived as five overlapping Google Drive export splits
(`dataset_a`, `dataset_a 2` … `dataset_a 5`). Their union covers all 63
session directories and 26,979 unique screenshots, but carries only 4
`events.jsonl` files (2 sessions) and **zero ground truth**. `dataset_a` and
`dataset_a 5` are byte-identical duplicates; parts 2/3/4 overlap by 55–57
sessions each. Merging them does not recover the missing files — those files
are in a part that was never downloaded.

**Consequence.** The README's intended workflow ("build and validate on A,
where ground truth lets you measure how correct your approach is") is not
available. There is no way to compute boundary accuracy against truth. This
is the single biggest constraint on the whole 7 days and it is recorded here
as the reason the approach below leans on *internal* consistency evidence
instead of measured accuracy.

`src/data_loader.py` handles the split-folder mess by deduplicating on
`(session_id, chunk_id)` with deterministic first-seen-wins ordering, and
reports chunks that have no loadable events rather than skipping silently.

---

## 2. Idle-gap segmentation does not work here

Percentiles of `ms_since_last_event` across all 20,477 dataset B events:

| percentile | 50% | 90% | 95% | 99% | 99.9% |
|---|---|---|---|---|---|
| seconds | 0.03 | 1.54 | 2.08 | 5.47 | 10.13 |

Gaps over 30s: **7 events (0.04%)**. Over 120s: 3.

The obvious first approach — "split the stream wherever the worker pauses" —
would produce roughly 7 boundaries across 15 sessions where the truth is on
the order of 170. The README explains why: waiting time was compressed in the
test recording. **Idle time is not a boundary signal in this data.** Ruled
out on Day 1 rather than Day 3, which is the main value of having done the
gap analysis first.

---

## 3. Content is redacted, but business text survives in element metadata

The capture settings (`capture_full_keystrokes: false`,
`redact_password_fields: true`) mean the obvious text sources are empty:

- `clipboard_change.payload.text_content` → **null** throughout (only `text_length` survives)
- `browser_form_input.payload.value` → **null** throughout
- `text_input_complete` → only 77 events in 20,477, and per the README unreliable

But real business text does come through on these paths:

| path | example |
|---|---|
| `mouse_click.payload.target_element.name` | `請求書承認 INV-2026-7344` |
| `mouse_click.payload.target_element.value` | `請求書照合完了。INV-2026-7345　金額：455,128円。差異あり要確認。` |
| `keystroke.payload.target_field.value` | `請求書照合完了。INV-2026-7347　金額：1,832,962円。差異なし承認。` |
| `context.extracted_text` | present on 4.6% of events |

So the README's instruction to "reconstruct text from `keystroke`" is
satisfiable — not by replaying individual characters, but by reading the
`target_field.value` snapshot that rides along on keystroke events.

---

## 4. The segmentation anchor: case IDs

Two case-ID families appear, and they are the strongest boundary signal in
the data:

- `P<n>-<8 digits>-<3 digits>` — e.g. `P6-07010448-012` (HR portal records)
- `INV-<year>-<4 digits>` — e.g. `INV-2026-7344` (invoice references)

Measured on dataset B: **170 distinct cases, 1,020 mentions, ~11.4 cases per
session (range 5–20), and 169 of 170 cases appear in exactly one session.**
Cases are session-local units of work — which is what makes case-anchored
segmentation viable where gap-based segmentation failed.

Cases map onto portal routes, giving a label taxonomy grounded in the
system's own vocabulary rather than invented:

| route | label | distinct cases | median naive span |
|---|---|---|---|
| `#/payroll-items` | `payroll_change` | 96 | 6.7s |
| `#/leave-applications` | `leave_application` | 18 | 252.5s |
| `#/onboarding` | `onboarding` | 14 | 244.8s |
| `#/social-insurance` | `social_insurance` | 10 | 134.7s |
| `#/resident-tax` | `resident_tax` | 8 | 320.4s |

Work spans three portal instances (`127.0.0.1:5132/5133/5134`) across
4 operators on 4 machines — so "how many people are involved" (Step 2) is
answerable, and the three hosts are probably separate company entities or
tenants.

---

## 5. Two problems this approach must still solve (Day 2)

Naive first-mention→last-mention spans are **not** submittable as segments,
for two measured reasons:

**(a) Spans overlap far too much.** Summing naive span durations per session
gives 1.45× to 3.32× the session's own wall-clock. Work is genuinely
interleaved (the README warns of exactly this), so overlapping spans must be
reconciled into a coherent timeline rather than emitted as-is.

**(b) `payroll_change` looks inflated by list-view rendering.** 96 of the 170
cases are payroll, but their median span is 6.7s with 3 mentions, versus
134–320s for every other process. A tight burst of many case IDs is the
signature of *a table listing many rows on one screen*, not of 96 separate
executions. Treating every mentioned ID as a worked case would badly
over-count the highest-volume process — and since Step 2 prioritises
automation by volume and time, that error would propagate straight into the
recommendation.

Day 2 therefore has to separate "this case is a row on screen" from "this
case is being actively worked", most likely by requiring evidence of
interaction directed *at* the case (a click on its row followed by
form/keystroke activity, a detail-view navigation) rather than mere presence.

---

## 6. Signals available for labelling and Step 2 variant analysis

Clicked element names carry a rich, directly usable business vocabulary —
useful both for sub-labelling and for the "different handling patterns within
the same process" question in Step 2:

expense categories (`消耗品費` consumables, `研修費` training, `出張旅費`
travel, `交通費精算` commuting reimbursement), leave types (`年次有給休暇`
annual paid leave, `特別休暇（慶弔）` special/bereavement leave), payroll
changes (`昇給` pay raise, `役職手当廃止` position-allowance removal),
contracts (`取引基本契約 (新規締結)` new basic transaction contract), and
product names (`モーターユニットF`, `光学レンズE`).

Application mix, which will drive the Step 3 automation target:

| app | events |
|---|---|
| Microsoft Edge | 13,300 |
| **Microsoft Word** | **3,704** |
| Microsoft Excel | 1,201 |
| Notepad | 599 |
| WindowsTerminal | 407 |

**Word ranking second — above Excel — is the leading Step 3 hypothesis.**
Document production off the back of portal data is typically high-volume,
rule-bound, and low-branching, which is the profile of a good first
automation. To be confirmed or dropped with real numbers on Day 3, not
assumed.
