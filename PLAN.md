# 7-Day Plan

Task: recover units of work from raw PC operation logs (Step 1), analyse them
and prioritise automation candidates (Step 2), and build a working automation
tool (Step 3) — delivered as a **web application**.

The README is explicit that judgment is what's assessed, not technical
sophistication, and that how the 7 days are spent is itself part of the
evaluation. So the allocation below deliberately spends ~40% on
segmentation/analysis (Steps 1–2, which everything else rests on) and ~45% on
the build (Step 3, the "show us something that actually works" requirement),
leaving real time for the report rather than treating it as leftover.

---

## Day 1 — Audit, scaffold, and choose the segmentation signal ✅

- Audit what actually arrived on disk vs. what the README promises.
- Set up repo, venv, and a loader that survives the split-folder mess.
- EDA aimed at one question: **which signal marks a work boundary?**
- Test and rule out the obvious approach (idle gaps) before building on it.

**Outcome:** idle-gap segmentation ruled out with measurements; case-ID
anchoring identified and quantified (170 cases, 5 process types); the two
problems it still has (span overlap, list-view false positives) measured and
written down. Dataset A confirmed unusable — no ground truth anywhere.
See [`reports/day1_findings.md`](reports/day1_findings.md).

## Day 2 — Step 1: segmentation algorithm → `segments.jsonl` ✅

- Separate "case is visible on screen" from "case is being worked".
- Reconcile overlapping case spans into a coherent, non-overlapping timeline
  per session, allowing for genuine interleaving (suspend/resume).
- Emit `segments.jsonl` for dataset B in the required schema.
- Validation without ground truth: screenshot spot-checks at predicted
  boundaries, plus internal consistency checks.

**Outcome:** the planned list-view fix turned out to address a non-problem.
The actual defect was that Day 1 labelled processes from the SPA route alone,
but dataset B holds **three business systems that reuse the same route
names** — so `#/payroll-items` was merging invoice approval, HR payroll and
inventory work. Rebuilt the taxonomy on (system, route): **12 resolvable
processes**, each named from its own screen's Japanese vocabulary.

Then split episodes into individual case executions at the completion comment
each process writes per case — episodes were ~3.6x too coarse for the
README's "individual executions". **165 episodes → 601 executions, zero
overlap, 95.4% wall-clock coverage, 97.8% agreement with an independent
process code** stamped into the portal's UIA row names. The one session with
no L3 events was resolved via that same process code, so no `*_unresolved`
labels remain. Deliverable written to `segments/segments.jsonl` and
schema-validated.

Also recorded: boundary alignment (99.3%) is near-tautological and is
reported as a regression guard, not as accuracy. The screenshot check was the
only one that tested something the algorithm didn't already assume — and its
first version was itself buggy. See
[`reports/day2_findings.md`](reports/day2_findings.md).

## Day 3 — Step 2: process analysis and ROI prioritisation ✅

- Per process: execution count, time consumed, operators involved, variance
  between executions (the "different handling patterns" question). All four
  are now available per segment.
- Build the prioritisation on explicit criteria — volume × time × rule
  determinism ÷ implementation difficulty — and show the working, so the
  ordering is arguable rather than asserted.
- Assess feasibility per candidate: data access route, branch count,
  governance constraints, and what could only surface during build.
- **Decide the Step 3 target and scope, and write down what's deferred.**

Three leads carried from Day 2, to be tested rather than assumed:

- Execution counts are now exact per process, and every execution carries the
  completion comment naming its case — so Step 2's "how often, how long, how
  many variants" is answerable from `segments.jsonl` plus those comments,
  which encode the variant directly (`変更種別：昇給` vs `役職手当廃止`,
  `スポット発注` vs `年間契約`).
- Word use is concentrated, not diffuse: `inv_contract_management` is 1,087
  Word events, `fin_payment_processing` 648. The contract screen displays
  `参照：参照書類：<file>.docx` — the portal *names the document the worker
  must open*, which is a far more automatable finding than Day 1's generic
  "Word is the second-heaviest app".
- `fin_budget_variance_analysis` is 497 Excel events out of 714 — nearly pure
  spreadsheet work, a different automation shape from the portal flows.

**Outcome:** 601 executions across 12 processes, 4 operators, with variants
read directly off the completion comments. One screen turned out to host two
processes (payroll change vs expense settlement). 133 executions were
relabelled from their own completion comment — 108 of them that split, and 25
genuine context mislabels where the comment was typed outside the browser.

Ranked on volume x time x determinism x data-access / branch-cost, with a
five-weighting sensitivity check. **The largest process by time
(`fin_invoice_matching`) ranks 7th** — 34% of its cases need human judgement
that nothing captured predicts, and only 25% stay in the browser. Scoring
distinguishes a *predictable* exception (緊急発注, a labelled field — one
branch) from a *judgement* one (差異あり, discovered during the work), because
charging both alike rewarded the wrong candidate.

Top three as a stable set across four of five weightings:
`fin_purchase_order_management`, `hr_leave_application`,
`hr_expense_settlement`.

Four operators, each handling 9–13 of the 13 processes — no specialists, so
adoption is a training problem rather than a redundancy one.

Two ROI levers tested and found unavailable, recorded rather than quietly
dropped: **there is no rework** (all 64 invoice cases worked exactly once; an
apparent 18.5% rate was `BATCH-` product codes miscounted as case IDs), and
**the process chain cannot be traced** (payment comments name 請求書照合
upstream in 27 of 36 cases, but no case reference crosses processes), so
automating one step cannot be credited with downstream savings.

**Step 3 decided: a shared review-and-approve foundation with per-process
definitions, configured for those three** — 214 of 601 executions (35.6%),
2,527s of 10,076s (25.1%), of which **1,733s (68.6%) is portal-only and
addressable**; the rest involves Word/Excel and stays manual. Justified by the
completion templates being parameterised strings, so a process definition is
config rather than code.

**The finding that reshaped Day 4:** across 20,477 events there are 7 `✓ 承認`
clicks. The submit action is essentially never captured, so the terminal step
of every one of these flows is unobserved. See
[`reports/day3_findings.md`](reports/day3_findings.md) §5.

## Day 4 — Step 3 foundation: portal contract + process schema ✅

- **First: verify the submit path.** Day 3 found the approve action is
  essentially absent from the logs (7 `✓ 承認` clicks in 20,477 events), so
  whether approval can be driven programmatically is unknown and everything
  else rests on it. If it cannot, the tool becomes a preparation-and-checklist
  surface rather than an execute surface — a change of shape that must be
  discovered before building, not after.
- Lock the stack and scaffold the app.
- Get the app reading real portal data from `127.0.0.1:5132/5133/5134`.
- Define the per-process definition schema, so the three configured processes
  are data rather than code. Policy limits (e.g. the expense
  規程内 thresholds) are **configuration supplied by the client**, not values
  inferred from the logs — every observed case was approved, so the data shows
  ranges, never a limit.
- Deliberately front-loaded: if the integration can't work, Day 4 is when to
  find out, not Day 6.

**Outcome:** the portals are unreachable (they ran on the client's Windows
machines), so the contract was reconstructed from evidence instead.

Doing that exposed a bug present since Day 1: `context.extracted_text` is a
**dict**, and every `isinstance(str)` guard against it matched nothing — so
**939 screen dumps, 633,859 characters** had been invisible. Nothing errored;
a filter just returned empty, which reads exactly like a negative finding.

That suppressed data **overturned a Day 3 conclusion**: the invoice
discrepancy branch is not judgement, it is a deterministic function of the
種別 column (定常→差異なし 42/42, 調整→差異あり 22/22, **64/64**).
`fin_invoice_matching` moves 7th → 5th. It stays deferred, but because it is
desktop-heavy rather than unpredictable.

**The submit risk narrowed rather than cleared.** Button clicks are still
absent, but every submit's *effect* is recorded: each screen is a two-state
machine with one transition and a known confirmation, over **345 observed
transitions**. Semantics established; transport (endpoint, payload, auth,
idempotency) still unknown.

Built `portal/contract.json` (13 screen contracts) and `portal/processes/*.json`
(3 validated definitions). See
[`reports/day4_findings.md`](reports/day4_findings.md).

**Then built the scaffold after all**, so the schedule risk did not carry.
Stack is Express + React on Rohith's call, which put a useful seam in the
project: Python derives the portal contract from the logs, Node consumes it,
and the JSON artefacts are the interface. 420 real records harvested from the
screen dumps back a mock that enforces the recovered state machine; the HTTP
client is a deliberate stub whose methods throw with the specific unknown each
one needs answered.

**The result that matters:** running the assist logic over the real queues,
`hr_leave_application` is 40/40 ready and `hr_expense_settlement` 84/213 — but
**`fin_purchase_order_management`, the top-ranked candidate, is 0 of 81.** Its
list view does not carry the field that decides the branch.

Audited that across all thirteen processes (`src/field_audit.py`): **311 of
599 executions (52%) sit behind a per-record fetch that does not exist**, and
three processes are fully blocked. The Day 3 model weighed volume, time,
determinism, integration surface and branch count but never asked whether the
deciding field is *visible* — a gap in the model, not in one process.

**And a reversal.** `fin_invoice_matching`, the largest process by time,
deferred twice, turns out to be the strongest candidate: 種別 predicts its
outcome 64/64 **and is an input** (populated on un-worked rows, unchanged
across 108 records seen twice), and every comment slot resolves from the list.
The 25% browser-only share that justified deferring it measures how the
*human* did the check — the work being removed, not a barrier to removing it.
Added as a fourth process: 86 pending, **54 ready**. Across all four: 420
pending, **178 draftable (42%)**.

## Day 5 — Corrected ranking, revised scope, operator tool ✅

- Generate the mock portal from `contract.json` — real columns, real status
  vocabularies, real records harvested from the dumps.
- Scaffold the web app with the portal adapter behind an interface, so the
  mock swaps for a real client without touching the tool.
- **Rebuild the ranking with the two corrected components.** `data_access`
  measured how the human worked rather than what the tool needs, and field
  visibility was absent entirely. Both are now measurable
  (`field_audit.py`), so the Day 3 ordering should be recomputed rather than
  patched process by process.
- Decide what to do about `fin_purchase_order_management`: either drop it from
  scope, or add the per-record fetch and accept that its integration is larger
  than the other three. The same question applies to `fin_payment_processing`
  and `hr_onboarding_verification`, also fully blocked.
- Harden the flow: bulk approve, keyboard-driven review, and a visible audit
  trail of what was submitted.
- Human-in-the-loop by default: the operator reviews and approves rather
  than the tool acting blind — chosen because these are HR/payroll records
  where a silent wrong write is expensive.
- Handle the branch cases found on Day 3; make unhandled cases fail visibly
  and fall back to the manual path.

**Outcome:** `data_access` replaced by `draftable` (what the tool needs, not
how the human coped). The ranking moved structurally —
`fin_invoice_matching` #5 → **#1**, `fin_purchase_order_management` #1 → #11,
and the three processes that cannot be drafted at all now sit last. After Day
4's correction, **no process in dataset B has judgement exceptions left**:
every observed branch is decided by a field present before the work starts.

Scope is now five processes, **484 pending / 242 drafted (50%)**. Added
`inv_contract_management` (#3). Kept `fin_purchase_order_management` at #11
deliberately — 81 records, none drafted, each saying why, which is the
clearest demonstration that unhandled cases fail visibly.

Front end rebuilt as a three-pane keyboard-driven operator tool: design-token
system, light/dark, bulk approve behind a confirmation that stops at the first
failure, session audit trail. Screenshotting it caught three real bugs the
build did not — inline row layout, a heading that told operators ready records
needed attention, and sidebar counts that only rendered for the open queue.
Then replayed the tool against the work that actually happened
(`src/replay.py`): each recovered execution ends with the comment its operator
wrote, so the drafted comment can be compared directly. **204 of 205 match —
99.5%**, the only measured accuracy figure in the project. Its first run
reported 0.0%, because operators sometimes wrap the same sentence in a Notepad
memo header.

`README.md` rewritten as the submission front door, structured as the flow of
the work; the client brief moved to `TASK.md`.
See [`reports/day5_findings.md`](reports/day5_findings.md).

## Day 6 — Harden, test, and the honest analysis

- Test against real logged cases; measure what fraction the tool actually
  covers.
- Write the two sections the README calls out specifically:
  **what manual work remains after deployment** (with realistic expected
  impact, not best-case), and **anticipated implementation/rollout risks
  with mitigations** — each risk tied to the evidence that suggested it.

## Day 7 — Report, work log, packaging

- Final report: Step 2 analysis and prioritisation, what was built and why
  that process/scope/form, alternatives rejected and why, residual manual
  work, risks and mitigations, and the 7-day allocation rationale.
- Work log: what was tried each day, what didn't work, and how generative AI
  was used (the README asks for this explicitly).
- Repo packaging and a clean run-through from a fresh clone.

---

## Step 3 form: web application

Fixed as a web app. The alternatives and why they lose here:

| form | why not |
|---|---|
| Desktop RPA (Power Automate Desktop, UiPath) | Closest to how the work is done today, but brittle against UI change, needs per-machine licensing/installation, and is hard to demo or hand over as a repo. |
| Deterministic script (Python/PowerShell) | Cheapest to build, but gives operators no review surface — and human review is exactly what HR/payroll writes require. |
| AI agent over procedure definitions | Highest ceiling, but the log gives limited evidence about decision rules, so an agent would be guessing on branches. A candidate for a later phase, once the deterministic path has produced labelled decisions. |
| **Web application** | The portals are already local web apps (`127.0.0.1:5132/5133/5134`), so a browser-based tool sits naturally alongside them, needs no desktop install, gives a natural review/approve surface for a human-in-the-loop design, and is directly demonstrable. |

Stack decision deferred to Day 4 on purpose — it should follow from the
process chosen on Day 3, not precede it.

---

## Known risks to the plan itself

- **No ground truth (materialised).** Step 1 accuracy cannot be measured,
  only argued. Mitigation: screenshot-based spot-checking plus a
  hand-labelled subset, and explicit honesty about the weaker evidence.
  If the missing dataset A JSON parts turn up mid-week, Day 2's evaluation
  harness is written so it can score against `gt.jsonl` immediately.
- **Over-counted `payroll_change` would mis-rank the automation candidates**
  (materialised, and fixed on Day 2 — but the cause was route/system
  conflation, not the list-view rendering Day 1 suspected). Volume feeds
  straight into prioritisation, so this had to be right before Day 3.
- **One session had no L3 events** (`ses_20260701-192455-NEELA9BAF`).
  Resolved on Day 2 via the portal's `p_code`, so it now carries real process
  labels — but its routes are inferred from a different signal than the other
  14 sessions, which is worth a sentence in the report.
- **Small absolute data volume.** 176 minutes of wall-clock across 15
  sessions. The README says to compare processes against each other rather
  than trusting absolute figures — so the report must present relative
  ranking, not extrapolated annual savings.
