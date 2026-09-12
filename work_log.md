# Work Log

Daily record of what was attempted, what was concluded, what failed, and how
generative AI was used. Required deliverable #4.

---

## Day 1

**Goal:** find out what data actually exists, and decide what signal Step 1
segmentation should be built on — before writing any segmentation code.

### What I did

1. **Audited the delivered data against the README/DATA_SCHEMA claims.**
   Started here because the first pass over the folder turned up no
   `events.jsonl` at all.
2. **Traced the cause.** The source was a Google Drive multi-part export
   (`AI Engineer-…-1-003.zip`), which contained 6,978 files, all `.jpg`, no
   JSON. Dataset A later arrived as five overlapping folder splits.
3. **Set up the project** — venv, `requirements.txt`, git repo on `main`
   wired to `github.com/rohith-0601/ImBesideYou`.
4. **Wrote `src/data_loader.py`** to flatten `events.jsonl` into one
   DataFrame, deduplicating `(session_id, chunk_id)` across the five
   overlapping dataset A folders and reporting unloadable chunks instead of
   skipping them quietly.
5. **Ran EDA (`src/eda_day1.py`)** on dataset B targeting one question:
   what marks a boundary between units of work?
6. **Wrote `src/case_extract.py`** once case IDs turned out to be the
   viable anchor, and measured how well they'd actually work.

### What I found

- **Dataset A is unusable and there is no ground truth anywhere.** All 63
  session directories exist, but across all five splits there are only 4
  `events.jsonl` files, 0 `manifest.json`, and 0 `gt.jsonl` /
  `gt_manifest.json`. `dataset_a` and `dataset_a 5` are byte-identical.
  Merging the splits doesn't help — the missing files were in a part that
  was never downloaded.
- **Dataset B is complete and verified**: 15/15 sessions, 20/20 chunks,
  20,477 events (README says ~20,000), `extracted_text` on 4.6% of events
  (spec says ~4%). This is the deliverable target, so Steps 1–3 can proceed.
- **Dataset B is HR/payroll**, across three portal instances
  (`127.0.0.1:5132/5133/5134`) and 4 operators, over 5 functional routes.

### What didn't work

- **Idle-gap segmentation — ruled out, with numbers.** My first instinct was
  to split on pauses. The 99.9th percentile gap is 10.1s and only 7 of
  20,477 events have a gap over 30s, because the README notes waiting time
  was compressed in the test environment. That approach would find ~7
  boundaries where the truth is ~170. Better to have killed this on Day 1
  than to have built on it.
- **Reading entered values directly — not possible.** `clipboard_change`'s
  `text_content` and `browser_form_input`'s `value` are null throughout
  (`capture_full_keystrokes: false`, `redact_password_fields: true`). Only
  `text_length` survives. I'd assumed clipboard content would be a strong
  signal for tracking data flow between apps; it isn't available.
- **My first case-ID regex missed a whole family.** `[A-Z]{2,4}-\d+-\d+`
  found only the 72 `INV-` IDs and silently missed the `P6-…`/`P13-…`
  family, because those prefixes are letter+digit. The first run looked
  clean and self-consistent, which is exactly why it was misleading — the
  real count was 170 cases, not 72. Widening the pattern more than doubled
  the recovered cases.

### What I concluded

Case IDs are the segmentation anchor: 170 distinct cases, 1,020 mentions,
~11.4 per session, and 169/170 confined to a single session. They survive in
`target_element.name`/`.value` and `target_field.value`, and they map onto
portal routes, which gives a label taxonomy taken from the system's own
vocabulary instead of an invented one.

Two problems remain, both measured rather than suspected, and both are
Day 2's job:

1. **Naive spans overlap 1.45×–3.32× the session wall-clock** — work is
   genuinely interleaved, so first-mention→last-mention spans can't be
   emitted as segments directly.
2. **`payroll_change` is probably inflated by list-view rendering.** 96 of
   170 cases are payroll, but with a 6.7s median span and 3 mentions,
   against 134–320s for every other process. That's the signature of a
   table rendering many rows at once, not 96 executions. Since Step 2 ranks
   automation candidates by volume and time, leaving this in would corrupt
   the actual recommendation.

**Leading Step 3 hypothesis (to be tested Day 3, not assumed):** Word is the
second-heaviest app at 3,704 events, above Excel. Document production from
portal data is usually high-volume and rule-bound — a good automation
profile.

### Decisions taken

- **Raw data is gitignored.** 12 GB, and it's the client's export rather than
  something this repo produces. The repo holds code, derived outputs, and
  reports.
- **`README.md` left as the task specification.** GitHub's boilerplate
  `echo "# ImBesideYou" >> README.md` would have appended to the spec
  document, so I skipped that line and wired the remote around it instead.
- **Step 3 will be a web application** (confirmed with Rohith). Rationale
  and rejected alternatives recorded in [`PLAN.md`](PLAN.md).
- **Evaluation strategy without ground truth:** screenshot spot-checks at
  predicted boundaries (4,746 dataset B screenshots available), internal
  consistency checks, and a hand-labelled subset — with the weakness of
  this evidence stated openly in the report. The Day 2 harness will be
  written so it can score against `gt.jsonl` the moment it appears.

### Generative AI usage

Claude Code (Opus 5 / Sonnet 5) used throughout: for the data audit and
root-causing the missing files, writing `data_loader.py`, `eda_day1.py` and
`case_extract.py`, and drafting these notes. The idle-gap dead end and the
regex miss were both caught by running the analysis and reading the numbers,
not by inspection. Japanese screen text (`請求書照合完了`, `年次有給休暇`,
`役職手当廃止`, etc.) was translated with the model's help.

### Artifacts

| file | what it is |
|---|---|
| `src/data_loader.py` | event/GT loading, split-folder dedup, session inventory |
| `src/eda_day1.py` | generates `reports/day1_eda.md` |
| `src/case_extract.py` | case-ID extraction + naive span/coverage measurement |
| `reports/day1_eda.md` | machine-generated statistics |
| `reports/day1_findings.md` | curated findings and their consequences |
| `PLAN.md` | 7-day plan and Step 3 form decision |

---

## Day 2

**Goal:** turn Day 1's chosen signal into an actual segmentation algorithm and
emit the `segments.jsonl` deliverable for dataset B.

I expected to spend the day on the two problems Day 1 left open — span
overlap and the `payroll_change` over-count. I spent most of it discovering
that Day 1's process taxonomy was wrong, which changed what those problems
even were.

### What I did

1. **Probed which surfaces the Day 1 case IDs actually came from**, expecting
   to separate "case rendered on screen" from "case actively worked".
2. **Dumped the raw strings behind the matches** when the surface split came
   back 170/170 on interaction surfaces — which contradicted the list-view
   hypothesis.
3. **Traced the `P<n>-<digits>-<digits>` family** through element payloads,
   session scoping, and eventually a screenshot.
4. **Discovered the three-system structure** from `browser_navigation`
   payloads, which carry `url` and `page_title` together.
5. **Rebuilt the taxonomy** on (system, route) pairs, naming each process
   from the Japanese vocabulary on its own screen (`src/process_context.py`).
6. **Wrote the segmenter** (`src/segment.py`) — contiguous process-context
   episodes with substantive-work gating and absorption of insubstantial runs.
7. **Wrote the evaluation harness** (`src/evaluate.py`) — four internal
   checks, plus a `score_against_gt` that stays unused until/unless dataset
   A's JSON appears.
8. **Wrote the screenshot spot-check** (`src/spot_check.py`) and actually
   opened the images, which is where the interesting failure came from.
9. **Generated the reports** (`src/report_day2.py`) so the numbers in
   `day2_segmentation.md` are reproducible rather than pasted.

### What I found

- **There are three business systems, not one.** `5132` HR人事給与システム,
  `5133` 財務会計システム, `5134` 受発注在庫管理システム — and they **reuse
  the same route names**. `#/social-insurance` is welfare applications on HR,
  budget variance analysis on Finance, and IT equipment requests on
  Inventory. Route-only labelling had been merging unrelated work.
- **That, not list-view rendering, was the `payroll_change` inflation.**
  `#/payroll-items` exists on all three systems. Day 1's guess and the actual
  cause were unrelated — a good argument for not having built on the guess.
- **The `P<n>-…` strings are `P<process>-<batch>-<row>`**, not case IDs. The
  body is session-constant; `P<n>` maps 1:1 onto (system, route). A
  screenshot of the Finance invoice table confirmed it outright: the `ID`
  column lists `P6-07010448-001`…`-012`, one per row, each paired with
  `INV-2026-7344`…`-7355` in the 区分 column. Same case, two identifiers.
- **Corrected taxonomy: 12 resolvable processes**, each name backed by its
  screen's own vocabulary.
- **162 segments, zero overlap, 95.6% coverage** (93.4–99.4%). Day 1's naive
  spans summed to 1.45×–3.32× wall-clock; that's fixed.
- **98.6% agreement with the independent `p_code`** (145/147 segments with
  evidence). The 2 disagreements both involve `P8`, the one genuinely
  ambiguous code.
- **One session has no L3 events at all** (`…192455-NEELA9BAF`) — the browser
  extension never connected, so `browser_url` is null for all 998 events.
  `window_title` covers the system for 99.2% of its Edge events, so it is
  segmented at system-only granularity and labelled `*_unresolved`.

### What didn't work

- **My Day 1 list-view hypothesis was wrong.** Surface attribution showed all
  170 cases came from interaction surfaces (`target_element.name`,
  `target_field.value`), none from screen-render text only. If I'd
  implemented the "require interaction evidence" fix I planned, it would have
  changed nothing, because presence-vs-interaction was never the problem.
- **Independent forward-fill of `port` and `route` manufactured three phantom
  processes.** A stale route from one system attached to a newly-focused
  other system, producing `hr_resident_tax`, `inv_order_check`,
  `inv_inventory_review`. They looked entirely plausible in the output table.
  What exposed them was that they had **no `p_code` support and no Japanese
  business vocabulary** — the corroborating-signal check, not inspection.
  Fixed by filling the (port, route) pair atomically.
- **`float('nan')` is truthy in Python.** My guard
  `if p and r and r not in IGNORED_ROUTES` happily built a literal
  `"nan|nan"` pair for 11,042 events, dropping label coverage to 45.2%. The
  symptom looked like a taxonomy gap, not a type bug. `isinstance(x, str)`
  fixed it; coverage went to 100%.
- **My screenshot spot-check was broken, and it looked like the segmenter was
  broken.** The first run appeared to show a false boundary — identical
  Finance screens either side. Reading the raw events proved the boundary was
  *real* (there's a `browser_navigation` to the HR system at that instant) and
  the checker was at fault: a capture 0.1s after a navigation still shows the
  old page, and `window_title` trails navigation by ~2.3s. Fixed with a
  standoff (≥2s before, ≥4s after). Nearly cost me a correct algorithm.

### What I concluded

The segmentation model is process **episodes**: a contiguous stretch of work
in one (system, route) context, with interleaving expressed as repeated
episodes of the same label. This matches the GT schema's
`process_suspended`/`process_resumed` shape, so it should be comparable to
truth if truth ever arrives.

On evaluation honesty: three of my four internal checks are worth something,
but **boundary alignment (99.3%) is close to tautological** — segments are
cut *because* of navigation events, so that number confirms the code does
what it intends, not that the boundaries are right. I've written that caveat
into the report rather than quoting the flattering number. The only check
that tested something the algorithm didn't assume was looking at pixels.

### Decisions taken

- **Label from (system, route), cross-check with `p_code`** — never the
  reverse. Using `p_code` as the label source would have destroyed the only
  independent signal available.
- **Name labels from screen vocabulary, not route strings.** The route names
  are actively misleading here, so `5134|#/leave-applications` is
  `inv_contract_management` (its sidebar says 契約管理), not anything to do
  with leave.
- **Emit `*_unresolved` for the L3-less session** rather than guessing a
  route. Coarser but honest, and flagged in the deliverable's limitations.
- **Keep case IDs for Day 3 sub-counting**, not for segmentation — they cover
  1 process of 12.
- **Thresholds deliberately loose** (`MIN_SUBSTANTIVE=3`,
  `MIN_DURATION_S=2.0`). With no ground truth there is nothing to tune
  against, so tight constants would be false precision.

### Generative AI usage

Claude Code (Opus 5) throughout. Most of the day was iterative probing —
roughly a dozen throwaway scripts in the scratchpad testing one hypothesis
each (which surfaces carry case IDs; is the `P` body session-scoped; does
`window_title` agree with the URL port; is each `P<n>` confined to one
route). The three-system discovery came from crosstabbing `page_title`
against port in `browser_navigation` payloads, and the `P<n>` decomposition
was settled by reading a screenshot rather than by more code. Japanese screen
text (契約管理, 予算差異分析, IT申請, 保守委託契約（更新）, 福利厚生申請) was
translated with the model's help. All three bugs above were found by running
the code and disbelieving the output, not by review.

### Optimisation pass (same day)

Having got a working pipeline, I went back over it looking for real defects
rather than polish. Three, in increasing order of how much they mattered.

**1. Episodes were not executions — a ~3.6x under-segmentation.** My segments
were contiguous stretches of work in one process context. But an invoice
clerk works `INV-2026-7345`, then `-7347`, then `-7348` without leaving the
screen: one episode, three executions. I counted the completion comments
inside my episodes and found **588 markers across 162 episodes**, a median of
3–4 each. The README asks for "individual executions", and dataset A's
`gt_manifest.json` settles the granularity — `executions[]` is "one entry per
execution", each with its own `case_id`. So I was emitting the wrong unit.

Fixed by splitting each episode at its completion markers: **165 episodes →
601 executions**, with coverage and non-overlap unchanged because the split
conserves each episode's span.

Two things I had to check before trusting it. First, my initial detector
keyed on 完了|承認|済み and found only 8 markers for `inv_stock_adjustment`
instead of 82 — stock adjustments are logged as memos with no completion
verb. Replaced keyword matching with a structural rule (a long field value
that isn't the placeholder; placeholders all end in `…`). Second,
`target_field.value` on keystrokes carries the field's *running* value, so
progressive typing would have inflated the count with partial prefixes — I
checked, and across a session's 86 long values **zero** were a prefix of a
later one. The comments are pasted, not typed, which is why
`clipboard_change` accompanies them. Had that check failed, dedupe-by-text
would have been badly wrong.

**2. The L3-less session no longer needs `*_unresolved`.** I'd shipped 10
segments labelled `hr_payroll_unresolved` etc. because that session has no
URL to derive a route from. But `p_code` is stamped into clicked row names by
the portal, needs no browser extension, and forward-fills cleanly since the
worker stays on a screen between clicks. Recovering the route from it
resolved the session completely — all 12 processes, no `*_unresolved`
anywhere in the deliverable. I left `P8` out of the recovery map (it's the one
ambiguous code) so an unresolvable stretch would still degrade honestly
rather than be guessed.

**3. `fin_bank_reconciliation` was the wrong name.** I'd inferred it from the
vendor names on screen. The completion comments say otherwise:
`発注管理処理。スポット発注：梱包材料　数量 164　合計 6,314,164円　通常。発注書確認・登録完了。`
— this is **発注管理, purchase order management**. It corroborates: the
Finance sidebar lists 請求書承認・経費精算, 経費承認（管理職）, 支払処理,
予算差異分析, 発注管理, and 発注管理 was the only item with no route assigned.
Renamed. The lesson is that vendor names were consistent with both readings,
and the completion comment is the process *naming itself* — better evidence
than row contents. I could only see it after building the execution splitter,
so that optimisation paid for itself twice.

**What the optimisation cost me, honestly:** execution-boundary alignment
with navigation events is 75.1%, down from 96.0% at episode level. That fall
is correct — most case boundaries happen inside one screen with no navigation
to align against, so a high score would have proved the executions weren't
being split. But it does mean the reassuring number got smaller, and
`evaluate.py` now reports both granularities and states which is which
instead of quoting the better one.

### Artifacts

| file | what it is |
|---|---|
| `src/process_context.py` | per-event system/route/label resolution, `p_code` extraction and route recovery |
| `src/executions.py` | per-case completion-marker detection and episode splitting |
| `src/segment.py` | episode segmentation + `segments.jsonl` writer |
| `src/evaluate.py` | four ground-truth-free checks at both granularities, plus a dormant GT scorer |
| `src/spot_check.py` | resolves screenshots either side of predicted boundaries |
| `src/report_day2.py` | regenerates `day2_segmentation.md` from the pipeline |
| `segments/segments.jsonl` | **the Step 1 deliverable** — 601 case executions, 15 sessions, 12 labels |
| `reports/day2_segmentation.md` | generated statistics and the taxonomy evidence |
| `reports/day2_findings.md` | curated findings |
| `reports/day2_boundary_spotcheck.md` | 30 sampled boundaries with image paths |

---

## Day 3

**Goal:** answer Step 2 — what work is done, how often, by whom, with what
variation — then rank automation candidates on stated criteria and decide the
Step 3 target and scope.

### What I did

1. **Parsed the completion comments into structured case records**
   (`src/case_parser.py`). Day 2 found them as boundaries; Day 3 reads what
   they say. They are strictly templated, one template per process, with the
   case details in slots.
2. **Cross-checked every execution's label against its comment template** and
   used the comment to correct the label where they disagreed.
3. **Built the Step 2 analysis** (`src/analyze_day3.py`) — executions, time,
   operators, variants, exception rates, integration surface.
4. **Scored and ranked** candidates on explicit criteria, then ran a
   **sensitivity check** across five weightings.
5. **Tested the shared-shape hypothesis** before committing to a scope, by
   looking for a common approve-flow across processes — which is where the
   most important finding of the day came from.
6. **Regenerated `segments.jsonl`** with the corrected labels.
7. **Wrote the reports** (`src/report_day3.py` generates the numbers;
   `day3_findings.md` holds the decision).

### What I found

- **One screen hosts two processes.** `5132|#/payroll-items` is both
  `給与変更登録` (payroll master change, 19 executions) and
  `経費精算確認済み` (expense settlement check, 90 executions). Counting them
  as one 111-execution process with "ten variants" would have overstated both
  the volume and the branching of a candidate that ranks near the top. This
  is the third time a screen-derived label turned out coarser than the real
  process; the portal's navigation structure is not the business structure.
- **The comment outranks the screen context for labelling.** Where a URL was
  live, comment and label agree 415/419 (99.0%). Where the comment was typed
  in Notepad or Excel, 41/62 (66.1%) — the inherited context is just wrong
  there. 133 of 601 executions relabelled in total: 108 from the HR screen
  split above (a refinement) and 25 genuine context mislabels. Deliverable
  regenerated.
- **The biggest process is not the best target.** `fin_invoice_matching` has
  the most time (1,288s) and ranks **7th**: 34.4% of cases end in
  差異あり要確認 (human judgement), and only 25% stay in the browser. Ranking
  by size alone picks it, and that would be wrong.
- **The ranking is stable.** Across five weightings `hr_leave_application` is
  1st in four; the exception is "ignore feasibility entirely", which is
  exactly the weighting that produces the bad answer.
- **All twelve processes share one shape** — select record, check rule, write
  a templated comment, submit. That is what makes a shared foundation with
  per-process definitions the right scope rather than a bespoke tool.

### What didn't work

- **My first `n_systems` metric measured nothing.** I scored "data access
  difficulty" as the number of portals a process touches, computed as a union
  across all its executions. That is 3 for every process, because every
  process is reachable from all three portals over a day. Recomputed *per
  execution* it is 1.0 for all twelve — a case stays inside one system. So
  the component was doing no work at all and was silently flattening the
  ranking. Replaced with the share of executions that stay inside the
  browser, which does vary (17%–96%) and is the real integration-cost
  difference. The lesson: a component that produces the same value for every
  row is not a weak signal, it is no signal, and it took looking at the
  column to notice.
- **Two variant regexes were extracting the wrong slot.** All 44
  `inv_it_request_processing` executions came back as variant "IT申請"
  (the template header) instead of the five real request types, and stock
  adjustment returned product names rather than the 区分 handling code. Both
  looked fine as a count — 44 executions, variant extracted — and were only
  visible once I printed the variant values themselves.
- **Three figures in the findings were stale or wrong and I had to go back
  for them.** Two totals I'd written from memory (10,281s vs the actual
  10,076s; 24.6% vs 25.1%), and a relabelling count of 37 that was measured
  *before* I split the HR screen into two processes — the real number is 133,
  of which 108 are that split and only 25 are genuine corrections. The 37
  survived in the draft because it still looked plausible. I caught it only
  because the segmenter printed its own count and the two disagreed, which is
  an argument for having the pipeline print numbers the report also claims.

### The finding that changed the plan

**The terminal action is invisible in the logs.** Across all 20,477 events
there are 7 `✓ 承認` clicks and 4 `⏸ 保留` clicks. Only 1.6% of invoice
executions contain an approve-style click at all.

I went looking for the shared approve-flow expecting to confirm it, and found
the opposite: we can see a worker select a record, consult a document and
write a completion comment, but we essentially never see the submit. L3
browser coverage is 13.5% of events and UIA rarely names the button.

That is the single biggest risk in the proposal and it is evidence-based —
we would be automating a flow whose final step has never been observed. We
don't know the endpoint, the payload, whether it's idempotent, or what it
returns on failure. It also settles the human-in-the-loop question: with the
submit path unverified and payroll records at stake, a tool that *prepares*
and a human who *commits* is the only defensible first version.

Day 4's first task is now to verify the submit path against the real portal,
before building anything on top of it.

### Decisions taken

- **Step 3 scope: a shared review-and-approve foundation with per-process
  definitions, configured for three processes** — `hr_leave_application`,
  `hr_expense_settlement`, `fin_purchase_order_management`. Together 214 of
  601 executions (35.6%) and 2,527s of 10,076s (25.1%).
- **Justified by measurement, not preference:** the completion templates are
  parameterised strings, so a process definition is a config object (template,
  variant list, rule, target screen). One bespoke tool for the top process
  covers 690s; the same effort plus three config entries covers 2,527s.
- **Deferred with reasons stated**, not for lack of time:
  `fin_invoice_matching` (34% judgement, 75% desktop),
  `inv_contract_management` (needs `.docx` handling),
  `fin_budget_variance_analysis` (Excel, a different tool),
  `inv_stock_adjustment` (11 variants on 81 executions — thinnest evidence
  per branch), and straight-through processing (unverified submit path).
- **Relative figures only.** The README says waiting time was compressed, so
  the report ranks processes against each other and extrapolates no
  annualised saving.

### Generative AI usage

Claude Code (Opus 5). The comment-template taxonomy and the variant regexes
were drafted with the model and then corrected against printed output twice —
both regex bugs above were caught that way, not by reading the patterns.
Japanese business vocabulary (給与変更登録, 経費精算確認済み, 差異あり要確認,
規程内であることを確認した, 発注管理処理, 緊急発注) was translated with the
model's help. The scoring formula was mine; the sensitivity check was added
because a single composite number is a fragile basis for a recommendation.

### Artifacts

| file | what it is |
|---|---|
| `src/case_parser.py` | completion-comment templates, variant/amount/date extraction, label correction |
| `src/analyze_day3.py` | Step 2 statistics, integration surface, opportunity scoring |
| `src/report_day3.py` | regenerates `day3_analysis.md`, including the sensitivity table |
| `reports/day3_analysis.md` | generated Step 2 tables and the ranking |
| `reports/day3_findings.md` | curated findings, risks, and the Step 3 decision |
| `segments/segments.jsonl` | regenerated with comment-corrected labels |
