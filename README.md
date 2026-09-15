# From Operation Logs to an Automation Proposal

**Rohith Perugu**
Indian Institute of Technology, Hyderabad — Engineering Science
es24btech11026@iith.ac.in

Submission for the FDE intern selection task.

**The three required deliverables:**

| | |
|---|---|
| Step 1 output | [`segments/segments.jsonl`](segments/segments.jsonl) — 601 executions across 15 dataset B sessions |
| Final report | [`FINAL_REPORT.md`](FINAL_REPORT.md) — analysis, prioritisation, what was built, residual work, risks, day allocation |
| Work log | [`work_log.md`](work_log.md) — what was tried each day, what failed, and how generative AI was used |

This README explains how the whole thing works. The client's brief is in
[`TASK.md`](TASK.md); the data specification in
[`DATA_SCHEMA.md`](DATA_SCHEMA.md).

---

## What this is

Raw PC operation logs — keystrokes, clicks, application switches — from a
Japanese company's back-office departments, with no markers saying where one
piece of work ends and the next begins. The job is to recover the units of
work, find where automation would pay, and build something that runs.

What came out of it:

| | |
|---|---|
| Events analysed | 20,477 across 15 sessions, 4 operators |
| Units of work recovered | **601 case executions** across **13 processes** |
| Automation candidates ranked | 13, on explicit and inspectable criteria |
| Built | a keyboard-driven operator tool, Express + React |
| Configured for | 5 processes — **222 of 325 in-scope executions drafted (68%)** |
| Measured accuracy | **99.5%** of drafted comments match what the operator actually wrote |

---

## The flow

Each stage feeds the next, and each one is a script you can run.

```
  events.jsonl                                        ┌──────────────────┐
       │                                              │  portal/         │
       ▼                                              │   contract.json  │
  ┌─────────────┐   which system + screen is this?    │   records.json   │
  │  CONTEXT    │ ──────────────────────────────────► │   processes/*    │
  └─────────────┘                                     └────────┬─────────┘
       │                                                       │
       ▼                                                       │
  ┌─────────────┐   contiguous work in one context             │
  │  EPISODES   │                                              │
  └─────────────┘                                              │
       │                                                       │
       ▼                                                       │
  ┌─────────────┐   split at each completion comment           │
  │ EXECUTIONS  │ ──────────────────────────► segments.jsonl   │
  └─────────────┘                                              │
       │                                                       │
       ▼                                                       │
  ┌─────────────┐   volume × time × determinism × draftable    │
  │  RANKING    │                                              │
  └─────────────┘                                              │
       │                                                       ▼
       └──────────────────────────────────────────►  ┌──────────────────┐
                            scope decision           │   THE TOOL       │
                                                     │ Express + React  │
                                                     └──────────────────┘
```

### 1 — Establish what screen each event happened on

`src/process_context.py`

The obvious approach is to label work by the SPA route (`#/payroll-items`).
That is wrong here, and the error is worth understanding because it shaped
everything after it.

Dataset B contains **three separate business systems** on three ports, and
they **reuse the same route names**:

| port | system | |
|---|---|---|
| `5132` | HR人事給与システム | HR / payroll |
| `5133` | 財務会計システム | financial accounting |
| `5134` | 受発注在庫管理システム | order / inventory |

`#/social-insurance` is welfare applications on HR, **budget variance
analysis** on Finance, and **IT equipment requests** on Inventory. Labelling by
route merged unrelated work into single classes.

So process identity is the **(system, route)** pair, forward-filled
atomically. `browser_url` is populated on only 37–66% of events and on **0%**
of one session where the browser extension never connected, so `window_title`
(which names the system on 96.6–100% of browser events) validates it and
covers the gap.

An independent check falls out of the data: the portal stamps a process code
`P<n>` into clicked row names, and 11 of 12 codes map to exactly one
(system, route) pair at 82–100%. It is used to verify the labels, never to
produce them.

### 2 — Recover units of work

`src/segment.py`, `src/executions.py` → **`segments/segments.jsonl`**

Two approaches were tested and rejected on measurement:

- **Idle gaps.** The 99.9th percentile inter-event gap is 10.1 seconds and
  only 7 of 20,477 events exceed 30 seconds, because the recording compressed
  waiting time. Splitting on pauses would find ~7 boundaries where the truth
  is ~600.
- **Case IDs as the unit.** The only genuine per-item IDs cover one process of
  thirteen.

What works is two-level. An **episode** is a contiguous stretch of work in one
process context. Inside it, each case ends with a **completion comment** the
worker types — and those are strictly templated:

```
請求書照合完了。INV-2026-7347　金額：1,832,962円。差異なし承認。
勤怠申請確認。種別：年次有給休暇。取得日：2026-07-15。問題なし承認。
発注管理処理。スポット発注：梱包材料　数量 164　合計 6,314,164円　通常。発注書確認・登録完了。
```

165 episodes contain 588 of these — a median of 3–4 each — so episodes alone
under-segment by roughly 3×. Splitting at them gives **601 executions, zero
overlap, 95.4% of session wall-clock covered**, each carrying its own case
identity and handling pattern.

The comment also outranks the screen context for labelling: where a URL is
live the two agree 415/419, but where the comment was typed in Notepad the
inherited context is wrong a third of the time.

**Validation.** Dataset A's ground truth never arrived (see
[Data](#a-note-on-the-data)), so boundary accuracy cannot be measured against
truth. Four internal checks substitute, each able to fail: non-overlap and
coverage, 97.8% agreement with the independent process code, one label per
(system, route), and screenshot inspection at sampled boundaries. They are
weaker evidence than a measured F1 and are reported as such.

### 3 — Analyse the work

`src/case_parser.py`, `src/analyze_day3.py`

The completion comments make Step 2 readable rather than inferred — the
template names the process, a slot names the handling pattern, and many carry
the amount and the decision.

- **13 processes**, 15–90 executions each, 2–11 named variants apiece.
- **4 operators**, each handling 9–13 of the 13. No specialists and no
  single-person silos, so automation is a training problem rather than a
  redundancy one.
- **872 clipboard operations**, at least one per execution on average —
  manual data movement is how all of this work is done.

Two standard ROI arguments were tested and **do not hold here**:

- **No rework.** All 64 real invoice cases were worked exactly once. A naive
  count says 18.5%, but that comes entirely from `BATCH-` codes, which are
  *product* identifiers — six distinct values across 78 stock adjustments.
- **The process chain cannot be traced.** Payment comments name invoice
  matching as an upstream step in 27 of 36 cases, but no case reference
  crosses processes, so automating one step cannot be credited with
  downstream savings.

### 4 — Rank the candidates

`src/field_audit.py`, `src/rescore.py`

```
opportunity = (volume + time_share)/2 × determinism × draftable / branch_cost
```

Two components are the interesting ones, and both arrived by building the tool
and watching it fail rather than by reasoning:

**`determinism`** distinguishes an exception that is a *labelled property of
the case* from one requiring judgement. `fin_purchase_order_management`'s 13%
exceptions are all 緊急発注 — one branch to implement. Charging both kinds the
same rewarded the wrong candidate.

**`draftable`** is the share of a process's comment slots that resolve from a
list row. It replaced a component that measured the share of work done inside
the browser — i.e. how the *human* coped. `fin_invoice_matching` scores 25%
there because the operator detours through Excel, but that detour is precisely
what the tool removes. **Measuring the manual effort you intend to delete, and
then penalising the process for it, is backwards.**

| # | process | exec | total s | draftable | opportunity |
|---|---|---|---|---|---|
| 1 | `fin_invoice_matching` | 64 | 1,288 | 1.00 | **0.721** |
| 2 | `hr_expense_settlement` | 90 | 972 | 1.00 | 0.587 |
| 3 | `inv_contract_management` | 47 | 1,186 | 1.00 | 0.487 |
| 4 | `hr_leave_application` | 56 | 690 | 1.00 | 0.364 |
| … | | | | | |
| 11 | `fin_purchase_order_management` | 68 | 864 | **0.00** | 0.025 |

The three processes at the bottom are the three whose deciding field is not on
the screen the tool reads — **311 of 599 executions (52%) sit behind a
per-record fetch that does not exist yet**, which is a finding about the whole
estate rather than one process.

### 5 — Build the tool

`server/` (Express) · `web/` (React) · `portal/` (the reconstructed contract)

The three portals ran on the client's Windows machines during the recording
and are unreachable. So the tool runs against a **mock built from the logs**:
528 real records parsed out of recorded screen text, enforcing the real state
machine (`未処理 → 登録済み`, confirmation `登録確定しました`) recovered from
345 observed transitions.

Everything portal-facing goes through one interface. `MockPortalClient`
implements it; `HttpPortalClient` is a deliberate stub whose methods throw with
the specific question each needs answered against a live instance — the
unknowns live in code, not in a paragraph.

**What the tool does:** for each pending record it drafts the completion
comment the operator would otherwise type, and says what it cannot decide.
**What it does not do is submit anything on its own.**

---

## Results

Two different populations get reported, and they answer different questions.
Both appear below rather than picking whichever is flattering.

### The outstanding queue — what the tool would do next

**486 pending records across 5 configured processes; 244 drafted (50%).**

| process | pending | drafted | needs a person |
|---|---|---|---|
| `hr_expense_settlement` | 214 | 85 | 129 (種別 = 調整) |
| `fin_invoice_matching` | 86 | 54 | 32 (種別 = 調整) |
| `inv_contract_management` | 64 | 64 | — |
| `hr_leave_application` | 40 | 40 | — |
| `fin_purchase_order_management` | 82 | **1** | 81 |

`fin_purchase_order_management` is kept in scope deliberately at rank #11. It
costs one config entry and is the honest demonstration that the tool fails
visibly — 81 records stating exactly which field is missing, alongside the one
record whose detail pane *was* captured, which drafts correctly and proves the
fetch would unblock the rest.

### The work that actually happened — what it would have done

Coverage measured against the 601 recovered executions rather than a snapshot
of whatever happened to be outstanding: **222 of 325 in-scope executions
drafted (68%)**, 35 routed to a person as exceptions, 68 awaiting the specified
fetch. Full breakdown in [`FINAL_REPORT.md`](FINAL_REPORT.md) §3.

The two figures differ because the populations differ — the pending queue
carries a higher share of 調整 records than the operators actually worked
during the recording. Neither is the "real" number on its own.

### Measured accuracy

`src/replay.py` replays the tool against the work that actually happened. Each
recovered execution ends with the comment its worker wrote; the tool drafts one
from the same record; the two compare directly.

**204 of 205 drafted comments match what the operator wrote — 99.5%**, across
308 executions linked to a portal record. The single mismatch is one segment
holding two consecutive approvals, a Step 1 artefact rather than a tool error.

This is the only measured accuracy figure in the project, and it exists because
the operators left their answers behind.

### What stays manual

Of the targeted work, **1,733s of 2,527s (68.6%) is portal-only** and therefore
addressable; the rest pulls in Word or Excel. That 68.6% is a ceiling, not a
forecast — review time is retained in full, and the submit may stay manual.

---

## Why there is no auto-approval

Two reasons from the data, not caution for its own sake.

**The submit transport is unverified.** Across 20,477 events there are 7
`✓ 承認` clicks. We know what a submit *does* — 345 status transitions and
their confirmation strings — but never how one is made. Endpoint, payload,
idempotency and failure behaviour are all unobserved. Any plan that assumes
"and then POST the approval" assumes the part the data does not cover.

**The policy the comment asserts is unknown.** The drafted sentence ends
規程内であることを確認した — "confirmed within policy". Every observed expense
case was approved, so the logs show ranges and never a threshold. A tool that
auto-approved against an inferred limit would be inventing the rule it claims
to enforce. Limits are configuration supplied by the client.

So the tool prepares and a person commits. Bulk approve exists, behind a
confirmation showing the count and a sample sentence; it submits each record
individually because the portal has no batch endpoint, and it **stops at the
first failure** rather than leaving a gap in the middle of a batch.

---

## Running it

See [`RUNNING.md`](RUNNING.md) for detail.

```bash
cd server && npm install && npm start     # API on :8765
cd web    && npm install && npm run dev   # UI  on :5173
```

To regenerate the analysis artefacts from the raw logs:

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
cd src
python segment.py --dataset b --out ../segments/segments.jsonl   # the Step 1 deliverable
python portal_contract.py    # -> portal/contract.json
python harvest_records.py    # -> portal/records.json
python process_defs.py       # -> portal/processes/*.json, validated
python rescore.py            # the ranking
python replay.py             # the accuracy measurement
```

---

## Repository

| path | |
|---|---|
| `segments/segments.jsonl` | **Step 1 deliverable** — 601 executions, 15 sessions |
| `src/` | analysis pipeline: context → segmentation → analysis → ranking → replay |
| `portal/` | the portal contract reconstructed from the logs |
| `server/` | Express API and the portal adapter |
| `web/` | React operator tool |
| `reports/` | findings per stage, generated tables kept separate from interpretation |
| `FINAL_REPORT.md` | **required deliverable** — the report and its four mandated sections |
| `work_log.md` | **required deliverable** — what was tried, what failed, and why |
| `PLAN.md` | the 7-day allocation and its rationale |

`reports/` splits generated numbers from written interpretation, so every
figure quoted in a findings document can be regenerated by the script named at
the top of it.

---

## A note on the data

Dataset A arrived as five overlapping folder exports containing all 63 session
directories but only **4 `events.jsonl` files, 0 manifests, and no ground
truth at all**. Its `gt.jsonl` — the thing that makes Step 1 measurable — was
in a part that was never downloaded.

The consequence runs through the whole submission: **Step 1 accuracy is argued
rather than measured.** Dataset B is complete (15/15 sessions, 20,477 events)
and everything here is built on it.

The evaluation harness in `src/evaluate.py` includes a `score_against_gt`
function that computes boundary precision and recall directly. It is unused,
and will work the moment a `gt.jsonl` appears.

---

## Honest limitations

- **Boundary accuracy is unmeasured.** The internal checks can fail and do
  constrain the result, but they are not an F1 against truth.
- **The sample is small.** 15 sessions, ~3 hours, 4 operators. Variant counts
  are thin — `hr_welfare_application` has 16 executions across 5 variants.
  Rules inferred from 2–4 examples would be wrong.
- **Durations are compressed** by design of the recording, so processes are
  ranked against each other and no annualised saving is extrapolated.
- **種別 predicts the invoice outcome 64/64 and is set before the work
  begins**, which is strong but is still 64 observations, and nothing in the
  logs says what sets it upstream. The 調整 arm stays manual.
- **The mock is faithful to the portal's semantics, not its transport.** It
  cannot be otherwise; no one has seen the transport.
