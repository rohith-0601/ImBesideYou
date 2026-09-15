# Final Report

**Rohith Perugu** · Indian Institute of Technology, Hyderabad · Engineering Science
es24btech11026@iith.ac.in

Companion documents: [`README.md`](README.md) (how the whole thing works),
[`work_log.md`](work_log.md) (what was tried and what failed),
[`reports/`](reports/) (per-stage findings, with generated tables separated
from interpretation).

---

## 1. Step 2 — what the work is, and which parts are worth automating

### 1.1 What was recovered

20,477 events across 15 sessions became **601 case executions across 13
processes**, worked by **4 operators**. The method and its validation are in
[`README.md`](README.md); what matters here is that each execution carries its
process, its handling pattern, its duration and the operator, so the Step 2
questions are read off the data rather than estimated.

| | |
|---|---|
| Processes | 13, across 3 systems (HR payroll, financial accounting, order/inventory) |
| Volume | 15–90 executions each over ~3 hours |
| Time | 294–1,288s each; 10,076s total attributed |
| People | 4 operators, each handling 9–13 of the 13 — no specialists, no single-person silos |
| Variation | 2–11 named handling patterns per process, stated explicitly in the work itself |

Two structural findings shaped everything downstream:

**The portal's navigation is not the business structure.** Three systems share
the same SPA route names, so `#/social-insurance` is welfare applications on
HR, budget variance analysis on Finance and IT equipment requests on
Inventory. Separately, one HR screen hosts two genuinely different processes
(payroll master changes and expense settlement checks). Labelling by screen
would have merged unrelated work and inflated the apparent volume of a
top-ranked candidate.

**Every process ends each case by writing a templated completion comment.**
This is the single most useful property of the data: it supplies case
boundaries, the handling pattern, often the amount and the decision — and,
later, a way to measure the tool's accuracy.

### 1.2 Two ROI arguments that do not hold here

Both are standard, and saying so is more useful than omitting them.

**There is no rework to eliminate.** All 64 real invoice cases were worked
exactly once. A naive count says 18.5%, but that comes entirely from `BATCH-`
codes, which identify *products* — six distinct values across 78 stock
adjustments. The saving must come from making each single pass faster.

**The process chain cannot be traced.** Payment comments name invoice matching
as an upstream step in 27 of 36 cases, but no case reference crosses process
boundaries. So end-to-end cycle time is unmeasurable, and automating one step
cannot be credited with downstream savings.

### 1.3 The ranking, and the two corrections that produced it

```
opportunity = (volume + time_share)/2 × determinism × draftable / branch_cost
```

| # | process | executions | total s | draftable | opportunity |
|---|---|---|---|---|---|
| 1 | `fin_invoice_matching` | 64 | 1,288 | 1.00 | **0.721** |
| 2 | `hr_expense_settlement` | 90 | 972 | 1.00 | 0.587 |
| 3 | `inv_contract_management` | 47 | 1,186 | 1.00 | 0.487 |
| 4 | `hr_leave_application` | 56 | 690 | 1.00 | 0.364 |
| 5 | `inv_stock_adjustment` | 81 | 827 | 0.67 | 0.245 |
| 11 | `fin_purchase_order_management` | 68 | 864 | 0.00 | 0.025 |
| 12 | `hr_onboarding_verification` | 31 | 1,131 | 0.00 | 0.022 |
| 13 | `fin_payment_processing` | 36 | 676 | 0.00 | 0.015 |

Both interesting components arrived by **building the tool and watching it
fail**, not by reasoning about the formula:

**`determinism` separates a labelled exception from a judgement.**
`fin_purchase_order_management` has a 13% exception rate that is entirely
緊急発注 — a property of the order, known before work starts, one branch to
implement. `fin_invoice_matching`'s 34% looked like judgement until 種別
(定常/調整) turned out to predict the outcome **64 out of 64** — and to be an
*input*: populated on un-worked rows, unchanged across 108 records observed
twice. Charging both kinds of exception alike had ranked the wrong candidate
first.

**`draftable` replaced a component that measured the wrong subject.** It was
originally the share of work done inside the browser — i.e. how the *human*
coped. `fin_invoice_matching` scores 25% there because the operator detours
through Excel. But that detour is precisely what the tool removes. Measuring
the manual effort you intend to delete, then penalising the process for it, is
backwards. `draftable` instead asks whether the fields the comment needs are on
the screen the tool reads.

That second correction moved `fin_invoice_matching` from #5 to #1 and
`fin_purchase_order_management` from #1 to #11 — a structural fault, not a
rounding difference.

**A finding about the estate, not one process:** the three at the bottom are
the three whose deciding field is not on the list screen. **311 of 599
executions (52%) sit behind a per-record fetch.** That question — *is the
deciding field visible where the tool looks?* — was absent from the first
ranking entirely and is the one I would put first on a similar engagement.

---

## 2. Step 3 — what was built

### 2.1 Why these processes, and why this scope

**Scope: a shared review-and-approve foundation with per-process definitions,
configured for five processes.**

The decisive evidence is that all thirteen processes have the same shape —
select a record, check it against a rule, write a templated comment, submit —
and the templates are parameterised strings:

```
勤怠申請確認。種別：{variant}。取得日：{date}。問題なし承認。
経費精算確認済み。費目：{variant}　金額：{amount}円。規程内であることを確認した。
発注管理処理。{reason}。発注書確認・登録完了。
```

So a process definition is a **config object**, not code: template, variant
list, state machine, rule, exception field. One bespoke tool for
`hr_leave_application` alone would cover 690s of observed work; the same
foundation plus four more config entries covers **5,000s across 325
executions**. The marginal cost of process six is a JSON file.

Four processes were chosen on the corrected ranking. The fifth,
`fin_purchase_order_management`, is kept **deliberately at rank #11**: it costs
one config entry and is the honest demonstration that the tool fails visibly —
81 records, none drafted, each stating exactly which field is missing.

Explicitly deferred, with reasons rather than for lack of time:
`fin_payment_processing` and `hr_onboarding_verification` (need a fetch whose
contract is still unknown), `fin_budget_variance_analysis` (497 of 714 events
are Excel — a spreadsheet tool, not a portal one), `inv_stock_adjustment`
(11 variants on 81 executions is the thinnest evidence-per-branch in the set).

### 2.2 Why a web application, and why not the alternatives

| form | why not |
|---|---|
| **Desktop RPA** (Power Automate, UiPath) | Closest to how the work is done today, but brittle against UI change, needs per-machine licensing, and — decisively — it would *replay* the operator's clicks, which is exactly the part the evidence says is unnecessary. The outcome is already on the record. |
| **Deterministic script** | Cheapest to build and gives operators no review surface. With the submit path unverified and payroll records at stake, a tool with nowhere for a human to intervene is the wrong shape. |
| **AI agent over procedure definitions** | Highest ceiling, but the branches here are decided by *fields*, not judgement — 種別, 緊急度. An LLM would be a probabilistic substitute for a lookup, adding cost and failure modes to a deterministic problem. A candidate for the 調整 arm later, once the deterministic path has produced labelled decisions. |
| **Web application** ✅ | The portals are already local web apps, so a browser tool sits alongside them with no desktop install; it gives the natural review surface a human-in-the-loop design requires; and it is directly demonstrable. |

### 2.3 What it does

Express API over a portal adapter, React front end. Three-pane operator
layout built for someone working several hundred cases in a sitting: `J`/`K`
move, `↵` approves and advances, `E` edits — the review loop runs without the
mouse. Bulk approve sits behind a confirmation showing the count and a sample
sentence, submits each record individually, and **stops at the first failure**
rather than leaving a gap mid-batch.

The portals were unreachable (they ran on the client's machines during the
recording), so the tool runs against a **mock reconstructed from the logs**:
528 real records parsed out of recorded screen text, enforcing the real state
machine recovered from 345 observed transitions. Everything portal-facing goes
through one interface; `HttpPortalClient` is a deliberate stub whose methods
throw with the specific question each needs answered against a live instance.

### 2.4 Measured accuracy

The strongest validation available, and it exists because **the operators left
their answers behind**. Each recovered execution ends with the comment its
worker wrote; the tool drafts one from the same record; the two compare
directly.

**204 of 205 drafted comments match what the operator actually wrote — 99.5%**,
across 308 linked executions. The single mismatch is one segment holding two
consecutive approvals — a segmentation artefact, not a tool error.

A 12-test suite covers the branches the replay *cannot* reach: 要注意 urgency
appears in 7 completion comments and no captured detail pane, and the refusal
paths are by definition things operators never did.

---

## 3. What manual work remains after deployment

### 3.1 Coverage, measured against the work that actually happened

Applied to the 601 observed executions rather than to a convenient snapshot:

| outcome | executions | share of all | share of time |
|---|---|---|---|
| **Drafted by the tool** | **222** | 37% | 35% |
| Exception → a person | 35 | 6% | 6% |
| Needs the specified fetch | 68 | 11% | 9% |
| Out of scope (8 processes) | 276 | 46% | 50% |

Within the five configured processes: **222 of 325 executions drafted (68%)**.

| process | drafted | exception | needs fetch |
|---|---|---|---|
| `hr_leave_application` | 56 | — | — |
| `inv_contract_management` | 47 | — | — |
| `fin_invoice_matching` | 42 | 22 | — |
| `hr_expense_settlement` | 77 | 13 | — |
| `fin_purchase_order_management` | — | — | 68 |

### 3.2 What a person still does — on every drafted case

**Drafted is not done.** For all 222, the operator still opens the record,
reads it, satisfies themselves the drafted sentence is true, and approves.
The tool removes composition and entry; it does not remove judgement or
accountability.

Two cases where the drafted sentence makes a claim the tool cannot verify, and
where the human step is therefore load-bearing rather than ceremonial:

- **`hr_expense_settlement`** — the comment ends 規程内であることを確認した
  ("confirmed within policy"). Every observed case was approved, so the logs
  show ranges and never a threshold. **The tool has no policy to check
  against.** It writes the sentence; the operator makes it true.
- **`inv_contract_management`** — the comment ends 関連書類確認済み ("related
  documents confirmed") and the portal names a `.docx`. The tool cannot open
  it. Both caveats are surfaced per record in the UI, not buried here.

### 3.3 The impact I would actually claim

**Not** a headline percentage. Three deductions sit between the 68% and any
real saving:

1. **Review time is retained in full.** The operator reads every case.
2. **The submit may stay manual** — the transport is unverified (§4.1).
3. **Only part of an execution is composition.** An execution boundary *is* the
   completion marker, so its recorded duration spans opening, checking and
   writing with no seam between them. Attempts to isolate the composition step
   from event structure did not survive inspection, and the README states
   waiting time was compressed in the recording, so even a clean decomposition
   would not transfer.

So the defensible claim is:

> For 68% of cases in five processes, the operator's job changes from
> *compose and type a templated sentence* to *read and confirm one*. The
> remaining 32% is unchanged. No estimate of minutes saved is offered, because
> this data cannot support one.

That is deliberately narrower than what these figures could be made to say. A
percentage quoted without those three deductions would be exactly the
optimistic framing the brief warns against.

### 3.4 What would move the number

| change | effect | cost |
|---|---|---|
| Build the specified `reason` fetch | +68 executions (21% of in-scope) | One endpoint, contract already specified |
| Obtain the expense policy thresholds | Turns 規程内 from a claim into a check | A conversation, not code |
| Establish the two unknown fetch contracts | Opens `fin_payment_processing`, `hr_onboarding_verification` (67 executions) | One instrumented session |
| Verify the submit path | Enables straight-through for the deterministic arm | One hour with the real system |

Every one is an access problem rather than an engineering one — which is the
main thing I would tell the client.

---

## 4. Risks, and what I would do about each

Each is tied to the evidence that raised it. The brief warns that proposals
built on optimistic assumptions score badly; these are the places where this
one could fail.

### 4.1 The terminal action has never been observed — **highest risk**

**Evidence.** Across 20,477 events there are **7 `✓ 承認` clicks** and 4
`⏸ 保留`. L3 browser coverage is 13.5% of events and captured no network calls.
We know what a submit *does* — 345 status transitions and their confirmation
strings — but not how one is made: endpoint, payload, auth, idempotency,
failure behaviour are all unknown.

**Why it matters.** Any plan that says "and then POST the approval" is
assuming the part the data does not cover. A wrong or duplicated write against
payroll records is expensive and individually harmful.

**Mitigation.** It is already contained by design: the tool prepares and a
human commits, so nothing depends on an unverified write. Closing it needs one
hour with a live instance or one instrumented recording with the extension
connected — not analysis. Until then the mock refuses repeat submits rather
than guessing, and `HttpPortalClient` throws with the specific unanswered
question.

### 4.2 The policy the tool asserts is unknown

**Evidence.** Every observed expense case was approved. The logs show amount
*ranges* per category (交通費精算 ¥5,083–24,395 … 接待交際費 ¥60,936–135,181)
and never a threshold, because no rejection was ever recorded.

**Why it matters.** The drafted comment says "confirmed within policy". A tool
that auto-approved against an inferred limit would be **inventing the rule it
claims to enforce**.

**Mitigation.** Thresholds are configuration supplied by the client, never
learned from logs. The definition carries `"threshold": null` and the UI states
per record that no amount check was performed. This is also why auto-approval
is deferred rather than merely unbuilt.

### 4.3 Browser instrumentation is unreliable

**Evidence.** L3 is 2,764 of 20,477 events (13.5%). One session of 15 recorded
**zero** L3 events — the extension never connected, and the log says so:
`Extension installed but NMH not running`.

**Why it matters.** Anything depending on DOM events — including a future
browser-extension integration — inherits that failure rate.

**Mitigation.** Nothing in the pipeline depends on L3 alone; the segmentation
resolves the system from `window_title` when the URL is missing, which is why
the L3-dead session was still recoverable. A production integration should
target the portal's HTTP interface rather than the DOM.

### 4.4 Thin evidence per branch

**Evidence.** 15 sessions, ~3 hours, 4 operators. `hr_welfare_application` has
16 executions across 5 variants — 2–4 examples each.

**Why it matters.** Rules inferred from 2–4 cases will be wrong, and wrong in
ways that only appear at volume.

**Mitigation.** Every rule is declarative config with a validator that rejects
a template slot with no stated source. Adding a process is a JSON file and a
test, so a bad rule is cheap to correct. I would also stage rollout by
evidence density — `hr_leave_application` (56 executions, 5 clean variants)
before `hr_welfare_application`.

### 4.5 A whole branch can be invisible in the list view

**Evidence.** Parsing the completion comments revealed 発注変更 ("order
change") as a **fifth** purchase-order type carrying urgency 要注意 ("requires
attention") — neither appears on the list screen, which has no urgency column
at all. It surfaced only because 7 of 68 comments refused to fit the template.

**Why it matters.** This is the general case of the field-visibility problem:
the screen the tool reads is not the whole record, and a variant you cannot see
is one you cannot route.

**Mitigation.** Treat any comment that fails to parse as a signal, not noise —
that is what exposed this one. On rollout, log unparsed cases and review them
weekly. The tool already refuses unknown variants rather than guessing.

### 4.6 Production conditions are unrepresented

**Evidence.** All three systems ran on `127.0.0.1:513x` with no visible login.
Durations are compressed by the recording's design.

**Why it matters.** Real deployment brings SSO, role restrictions, audit
requirements and network latency — none of which the logs say anything about.
Absolute timings will not transfer.

**Mitigation.** Comparisons are relative throughout and no annualised saving is
extrapolated. Auth and audit are integration questions to settle with the
client before build, and they sit behind the same `PortalClient` seam as the
submit path.

### 4.7 Adoption is a training problem, not a redundancy one

**Evidence.** Four operators each handle 9–13 of the 13 processes; nobody is a
specialist. Within-process spread between operators reaches 3.4×.

**Why it matters.** Automating any process touches all four people. The
positive reading is there is no key-person risk; the risk is that a tool
changing part of everyone's day needs everyone's buy-in.

**Mitigation.** Start with `hr_leave_application` — highest accuracy, zero
exceptions, cleanest integration — so the first thing operators see works
consistently. Keep the manual path available throughout; the tool adds a
surface rather than removing one.

---

## 5. How the seven days were spent

| day | focus | share |
|---|---|---|
| 1 | Data audit; choose the segmentation signal | ~14% |
| 2 | Step 1: segmentation → `segments.jsonl` | ~14% |
| 3 | Step 2: analysis and prioritisation | ~14% |
| 4 | Portal contract; field audit; first build | ~14% |
| 5 | Corrected ranking; the operator tool; replay | ~21% |
| 6 | Coverage, residual work, risks, this report | ~14% |
| 7 | Packaging and final pass | ~9% |

Roughly **40% on Steps 1–2** and **45% on Step 3**, with real time for the
report rather than treating it as leftover.

**Two decisions about that allocation.**

Day 1 went entirely on auditing the data and testing the obvious segmentation
approach before writing any. Idle-gap splitting was ruled out with numbers
(99.9th percentile gap 10.1s) rather than by intuition. Discovering on Day 3
that the boundary signal was wrong would have cost far more than the day spent
ruling it out.

The build was started on Day 4 rather than Day 5 as planned, and that turned
out to be the highest-leverage decision of the week. **Both faults in the
ranking were found by building the tool and watching it fail** — the 0-of-81
result exposed a missing component in the score, and the Excel-detour penalty
only looked wrong once the tool could draft the comment without Excel. Neither
would have surfaced from more analysis.

**What I would do differently.** Ask "is the deciding field on the screen the
tool reads?" during Step 2, not after building. It is cheap to check and it
reordered the entire ranking. I would also have run the replay earlier: it was
the strongest evidence available all week, needed no new data, and I only built
it on Day 5.

---

## 6. Honest limitations

- **Step 1 accuracy is argued, not measured.** Dataset A arrived without any
  ground truth, so boundary accuracy cannot be scored. The internal checks can
  fail and do constrain the result, but they are not an F1 against truth.
  `src/evaluate.py` contains a working `score_against_gt` that will run the
  moment a `gt.jsonl` appears.
- **The 99.5% is comment accuracy**, not process accuracy. It says the tool
  writes what the operator would have written, on cases it agrees to draft.
- **種別 predicts the invoice outcome 64/64 and is set before the work**, which
  is strong — but it is 64 observations, and nothing says what sets it
  upstream. The 調整 arm stays manual.
- **The mock is faithful to the portal's semantics, not its transport.** It
  cannot be otherwise; nobody has seen the transport.
- **No time-saved figure is offered**, for the reasons in §3.3.
