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

### Second pass: three things the first pass got wrong or skipped

**1. The score charged predictable and unpredictable exceptions identically.**
`determinism = 1 - exception_rate` treated `fin_purchase_order_management`
(13.2% exceptions) as harder than it is. Checked by variant: exception rate is
exactly 1.0 for 緊急発注 and exactly 0.0 for the other three order types — the
exception is a labelled field, known before work starts, and supporting it is
one branch. Meanwhile `fin_invoice_matching`'s 34.4% is genuine judgement:
amount does not predict it (means ¥1.03M vs ¥1.30M, medians ¥665k vs ¥698k,
fully overlapping), and the 種別 column visible in the screenshots **never
appears in the log at all**. Split the two cases; only judgement exceptions
now reduce determinism. This moved `fin_purchase_order_management` from 3rd to
1st. The chosen *set* of three did not change, which is the reassuring part.

**2. I had not actually answered "how many people are involved" properly.**
Only "operators per process". Doing it per operator: four people, each
handling 9–13 of the 13 processes, median 11.0–13.7s each. Nobody is a
specialist — so automation is a training problem, not a redundancy one, and
there is no key-person risk to claim as urgency. The interesting variation is
*within* processes: `hr_welfare_application` has a 3.40× spread between
operators on an identical procedure and `hr_onboarding_verification` 2.37×.
Inconsistent application is worth more than the time saved — but both rank
9th and 13th otherwise, so I recorded the tension rather than reverse-
engineering the scope to match it. With 16 and 31 executions the sample
cannot separate inconsistent practice from a few slow cases.

**3. No estimate of what stays manual.** The README requires it and I had
nothing. Splitting the three target processes' time by whether an execution
pulls in a desktop app: **1,733s of 2,527s (68.6%) is portal-only and
addressable**; 794s involves Word/Excel/Notepad and stays manual. Crucially
that 68.6% is a ceiling, not a forecast — review time is retained in full,
the submit may stay manual (§6), and `hr_expense_settlement` is half desktop
work despite being the volume argument for its inclusion. Writing the number
without those three deductions would be exactly the optimistic framing the
README says scores badly.

Also checked and worth stating: the `hr_expense_settlement` rule
(規程内であることを確認した) looked like a clean amount threshold per
category, and the observed bands are tidy (交通費精算 ¥5,083–24,395 …
接待交際費 ¥60,936–135,181). But **every observed case was approved** — there
are no rejections in the data — so these are ranges, not thresholds. The tool
must take limits as client configuration rather than infer them here. I had
been about to treat this as the most mechanisable rule in the dataset, which
it may be, but not for the reason I first assumed.

### Third pass: testing two ROI claims I had not yet earned

I had the ranking and the residual-work estimate, but two standard automation
arguments were still unexamined. Both turned out to be unavailable here, and
one of them I had already half-made.

**"The tool eliminates rework" — false, and I nearly published the opposite.**
Counting repeat work by case reference gave 22 of 119 case-session pairs
worked more than once, up to 5 times: an 18.5% rework rate, which would have
been a good line in the report. It is wrong. Splitting by reference kind:
`INV-` references (real invoice cases) are 64 distinct across 64 pairs with
**zero** repeats, and `P-` references 2 of 16. The entire signal came from
`BATCH-Wn`, which is a **product** code — only 6 distinct values across 78
stock adjustments — so "the same batch adjusted six times" is six different
cases about one product, not one case reworked six times.

This is the third time on this task an identifier has looked like a case ID
and not been one (`P<n>-…` on Day 1, `BATCH-` now). The tell is the same each
time: far fewer distinct values than executions. I've added the ref-kind
split to `analyze_day3.rework()` so the number can't be quoted unsplit.

Consequence: **no rework lever exists.** Savings must come from making the
single pass faster.

**"Automating this step speeds up the next one" — not supportable.**
`fin_payment_processing` comments carry a 工程 field naming their upstream
steps, and 27 of 36 name 請求書照合 (invoice matching). So the chain is real
procedurally. But no case reference appears in more than one process (0 of 85),
and the 36 payment amounts share **zero** values with the 64 invoice amounts.
The chain exists in the procedure and is invisible in the data — so end-to-end
cycle time can't be measured, and I can't credit invoice automation with
downstream payment savings. Recorded as a restriction rather than left as an
implied benefit.

**What an execution is made of.** 872 clipboard operations in total, and every
process averages at least one per execution. Manual data movement is how all
of this work is done, not a quirk of a few flows — and it's the thing an
integration actually removes. Two useful reads: `hr_leave_application` is
confirmed as the cleanest target from an independent direction (1.14
clipboard, 3.0 keystrokes, 0.86 app switches, 1.12 apps — nearly
single-application clicking, which is why its addressable share is 98.8%);
and `fin_budget_variance_analysis` averages 57.9 keystrokes per execution,
six times the next-highest, confirming it's figures typed into Excel and
needs a different tool rather than a slot in this one.

`hr_onboarding_verification` is the heaviest shuttler (2.74 clipboard, 9.42
app switches). Largest per-case gain in the set, but 31 executions — noted
for a later phase rather than pulled into scope.

### Decisions taken

- **Step 3 scope: a shared review-and-approve foundation with per-process
  definitions, configured for three processes** — `fin_purchase_order_management`,
  `hr_leave_application`, `hr_expense_settlement`. Together 214 of 601
  executions (35.6%) and 2,527s of 10,076s (25.1%), of which 1,733s (68.6%)
  is portal-only and addressable. Taken as a set rather than by rank, since
  the top three scores sit within 0.033 of each other.
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


---

## Day 4

**Goal:** verify the submit path against the real portals — the thing Day 3
identified as the biggest risk — then scaffold the app and define the
per-process schema.

The verification took a different route than planned, and on the way it
exposed a bug that had been quietly suppressing the richest source in the
dataset since Day 1.

### What I did

1. **Checked whether the portals are reachable.** They are not — they ran on
   the client's Windows machines in July 2026 and nothing is listening here.
2. **Went looking for what the logs could tell me about the portal instead**,
   starting with `context.extracted_text`.
3. **Found the bug**, fixed it in `data_loader`, and re-examined what it
   unlocked.
4. **Re-tested a Day 3 conclusion** that had rested on the suppressed data.
5. **Wrote `src/portal_contract.py`** to reconstruct the portal's data
   contract from 939 screen dumps.
6. **Wrote `src/process_defs.py`** — the per-process definition schema, with
   a validator, plus the three definitions for the chosen scope.

### The bug

`context.extracted_text` is a **dict**, not a string:

```python
{"text": "...", "source": "text_pattern", "char_count": 890, "truncated": False}
```

Every guard I had written against it since Day 1 was `isinstance(x, str)`.
That matches nothing. **939 screen dumps, 633,859 characters, never read** —
not by `case_extract.text_surfaces`, not by the Day 3 probe that went hunting
for the 種別 column and reported it absent.

This is the failure mode I keep having to watch for: nothing errors, a filter
just returns empty, and an empty result is indistinguishable from a real
negative finding. Day 3 stated "the 種別 column never appears in the event log
at all" with apparent evidence behind it, and that sentence was a type
mismatch. I now expose a flattened `screen_text` column so the same mistake
can't be made again.

### What that overturned

**Day 3's central claim about invoice matching was wrong.** Joining the 64
invoices present in both a screen dump and a completion comment:
定常 → 差異なし承認 in **42/42**, 調整 → 差異あり要確認 in **22/22**. The
discrepancy outcome is a deterministic function of a column that is on screen,
in the log, and visible before the work starts. Not judgement at all.

Reclassified, `fin_invoice_matching` rises from 7th to 5th. **The scope
decision holds — but on a different reason.** It is no longer "unpredictable
judgement", it is "predictable but desktop-heavy" (25% browser-only). I'd
rather the deferral be right for the right reason.

### What the screen dumps gave me

Full list views with column headers, every row, and the confirmation toast
after an action. Enough to reconstruct each screen's record schema, status
vocabulary and state machine.

**Every screen is a two-state machine with exactly one transition** —
申請中→承認, 未処理→登録済み, 照合中→完了, 処理待ち→処理完了, 未確認→完了 —
each with a known confirmation string, across **345 observed transitions**.

So Day 3's "the terminal action is invisible" needed narrowing rather than
retracting. The button clicks really are absent (7 `✓ 承認` in 20,477 events),
but the *effect* of every submit is recorded. We know what a submit does and
what the system says back; we don't know how to invoke it. That is an
integration unknown, not a semantic one — the difference between "we don't
understand the process" and "we need an hour with the API".

### What didn't work

- **My first row parser assumed fixed-width rows.** 発注管理 leaves 金額
  empty, the blank line vanishes when empty lines are stripped, and every
  subsequent row desynchronised — producing a screen with *no statuses at
  all*. It looked like the screen simply had no status column. Rewrote to
  split on record-id boundaries.
- **Then the toast got absorbed into the last row's status cell**, giving
  statuses like `P10-07040532-004: 完了しました` and transitions between two
  toasts. Fixed by finding the toast boundary first.
- **Keying the contract on the forward-filled process label mixed screens
  together** — `hr_welfare_application` came back titled 契約管理. The screen
  prints its own title, which can't drift, so I key on that instead.
- **The validator rejected my own first process definition** ten seconds after
  I wrote it: `exception_field: 変異` is not a column on that screen. Chasing
  it produced a genuine build constraint (below), which is the best argument
  I have for having written the validator at all.

### The constraint the validator surfaced

The 発注管理 list view shows only `発注管理 PO-2026-5156` in its 項目 column.
**The order type that determines the branch is not in the list at all** — it
appears only in the completion comment, i.e. after the worker has opened the
record. So this process needs a per-record fetch that the other two don't, to
classify each case before acting. Recorded as `variant_source: record_detail`
and flagged for Day 5, rather than discovered mid-implementation.

### Second pass: the scaffold, after all

I had written the scaffold off as a schedule risk for Day 5. With the contract
settled it turned out to be reachable the same day, so I built it rather than
carry the risk.

**Stack changed twice, on request, and the second change improved the
design.** I started on Python `http.server` (no dependencies, runs from a
fresh clone). Rohith asked for React, so the front end became Vite + React —
node 26 and the npm registry were both available, so a proper build rather
than CDN script tags. Then he asked for an Express backend, which I initially
read as a lateral move and it isn't: it puts a clean seam in the project.
**Python is now the analysis pipeline that derives the portal contract from
the logs; Node/Express is the tool that consumes it.** The JSON artefacts
(`contract.json`, `records.json`, `processes/*.json`) are the interface
between them. I deleted the Python `portal_client.py` and `assist.py` rather
than keep two implementations to drift apart.

**What got built:**

- `src/harvest_records.py` — pulls **420 real records** out of the recorded
  screen dumps. Not synthetic: every one was on an operator's screen. Keeps
  the *earliest* observed status per record, so the mock starts in the state
  the operator found it in and a run is reproducible.
- `server/portalClient.js` — the adapter seam. `MockPortalClient` enforces the
  real state machine from `contract.json`; `HttpPortalClient` is a deliberate
  stub whose three methods throw with the specific question each needs
  answered against a live instance. Putting the unknowns in code rather than
  in a report paragraph is the point.
- `server/assist.js` — drafts the completion comment from the record's own
  fields, and marks what it cannot decide.
- `server/index.js` — Express API.
- `web/` — React front end: process tabs, a queue split into *ready* and
  *needs review*, and a card per record showing the drafted comment and the
  tool's reasoning.

**Verified end to end:** Express serves the queue, Vite proxies to it, a
submit returns 申請を承認しました and decrements the pending count, a repeat
submit is refused, an empty comment is refused, and `vite build` compiles
clean (31 modules).

### The number that matters most

Running the assist logic over the real queues:

| process | pending | ready | needs review |
|---|---|---|---|
| `hr_leave_application` | 40 | **40** | 0 |
| `hr_expense_settlement` | 213 | 84 | 129 |
| `fin_purchase_order_management` | 81 | **0** | 81 |

**My top-ranked candidate is currently 0% automatable.** `fin_purchase_order_management`
ranked first on Day 3's scoring, and not one of its 81 pending records can be
drafted, because the list view does not carry the order type that decides the
branch — the constraint the validator surfaced this morning, now quantified
against real data.

That is worth more than a working demo. The Day 3 ranking scored volume, time,
determinism and *app* surface, but never asked whether the deciding field is
actually on the screen the tool reads. It is a gap in the scoring model, not
just in this one process, and Day 5 should check the same question for every
deferred candidate before anything else gets promoted.

`hr_expense_settlement`'s 129 reviews are different and expected — those are
`種別: 調整` records the definition deliberately flags as exceptions.

### Third pass: auditing the gap the prototype exposed

The 0/81 result was too important to leave as a note for tomorrow, so I ran
the check across all thirteen processes (`src/field_audit.py`).

**311 of 599 executions (52%) sit behind a per-record fetch that does not
exist.** Six processes are draftable from the list alone (288 executions),
four partially, and three are fully blocked:
`fin_purchase_order_management`, `fin_payment_processing`,
`hr_onboarding_verification`.

My first version of the audit was wrong and gave two answers I didn't believe,
which is why I looked. It compared each process's *variant* values against the
list columns — but for `fin_invoice_matching` the variant is the **outcome**
(差異なし承認 / 差異あり要確認), not an input, so comparing it to columns
reported `detail_only` when the real predictor (種別) is right there on the
list. And `inv_stock_adjustment` matched 0.55 against 氏名 purely because my
Day 3 variant regex falls back to a product name for portal records and a 区分
code for Notepad ones. Rewrote it to check **per comment slot**, which is the
same condition `assist.js` applies when deciding whether to draft — so the
audit and the tool can't disagree.

### The reversal

That fix flipped `fin_invoice_matching` to `list_sufficient`, which mattered
enough to test properly. It is the largest process by time in the dataset and
I had deferred it **twice** — Day 3 as irreducible judgement, Day 4 as
desktop-heavy. Both reasons are wrong:

1. 種別 predicts the outcome **64/64**.
2. 種別 is an **input**, not an output — populated on 未処理 rows (147 定常 /
   91 調整 while still un-worked), and across **108 records seen more than
   once, not one changed**. So the branch is decided before anyone touches the
   record and automating against it isn't circular. I checked this because a
   field that perfectly predicts an outcome is worthless if the work sets it;
   `field_is_an_input()` encodes the test and I ran it on all three 種別
   screens.
3. Every comment slot resolves from the list row.

The 25% browser-only share I used to justify deferring it measures how the
*human* did the check — the Excel and Word detour. If the outcome is already
on the record, that detour is the work being removed, not a barrier to
removing it. **`data_access` was measuring the wrong thing**, which is the
second flaw found in the Day 3 scoring model today.

So I added it as a fourth process definition. In the running prototype: 86
pending, **54 ready**, 32 routed to a human, and the drafted comment matches
the recorded originals character for character —
`請求書照合完了。INV-2026-7347　金額：1,832,962円。差異なし承認。`

Across all four processes: **420 pending, 178 draftable (42%)**.

One more bug worth recording: adding it, every one of the 86 records came back
flagged. `variant_map` turns 種別 = 定常 into the comment phrase 差異なし承認,
and I was validating that *mapped phrase* against the definition's raw variant
list `[定常, 調整]`, so every record failed as "unknown variant". Split into
`rawVariantOf` (validate) and `commentVariantOf` (render).

### What I deliberately did not build

**Auto-approval.** Every proposal carries `needs_review` and nothing submits
without an explicit POST. Two reasons from the data rather than caution for
its own sake: the submit transport is unverified, and policy limits are
unknown — every observed expense case was approved, so a tool that
auto-approved against an inferred threshold would be inventing the rule it
claims to enforce. The drafted comment says 規程内であることを確認した
("confirmed within policy") and the tool has no policy to confirm against; a
human still does that part.

### Decisions taken

- **Build against a mock reconstructed from `contract.json`**, with the portal
  adapter behind an interface so it can be swapped for a real client. Given
  the portals are unreachable, the alternative is not building at all.
- **Key the contract on screen title, not process label.** The title is
  printed by the screen; the label is inferred and can drift.
- **Policy thresholds stay configuration.** Still not inferable — every
  observed case was approved, so the data shows ranges and never a limit.
- **`fin_invoice_matching` stays deferred**, on the corrected reason.

### Generative AI usage

Claude Code (Opus 5). The screen-dump parser went through four iterations, and
every one of its bugs was found by printing the parsed output and not
believing it — fixed-width rows, the absorbed toast, the label-keyed
contamination. The 種別 correlation was a hypothesis the model proposed once
the screen text became visible; I tested it as a join rather than accepting
it. Japanese portal vocabulary (未確認, 照合中, 登録確定しました, 発注区分)
translated with the model's help.

### Artifacts

| file | what it is |
|---|---|
| `src/portal_contract.py` | reconstructs the portal contract from screen dumps |
| `src/process_defs.py` | per-process definition schema + validator |
| `portal/contract.json` | 13 screen contracts: columns, states, transitions, confirmations |
| `portal/processes/*.json` | 3 validated definitions for the chosen scope |
| `reports/day4_findings.md` | the bug, the correction, the contract, the schedule risk |
| `src/harvest_records.py` | pulls 528 real records out of the screen dumps |
| `src/field_audit.py` | is the deciding field on the screen the tool reads? |
| `portal/records.json` | the harvested records the mock serves |
| `server/` | Express API: portal adapter, assist logic, routes |
| `web/` | React front end (Vite) |
| `RUNNING.md` | how to run both halves, and what to expect |

---

## Day 5

**Goal:** rebuild the ranking with the two components Day 4 proved were wrong,
settle the scope that follows from it, and build the operator tool properly.

### What I did

1. **Rebuilt the score** (`src/rescore.py`), replacing `data_access` with
   `draftable` from `field_audit.py`.
2. **Revised scope** on the corrected ordering — added
   `inv_contract_management`, kept `fin_purchase_order_management` for a
   reason.
3. **Rebuilt the front end** as a three-pane operator tool with a real design
   system, keyboard navigation, bulk approve and an audit trail.
4. **Looked at it.** Screenshotted the running app in both colour schemes and
   fixed what was actually wrong rather than assuming it was fine.

### What I found

**The ranking moved a long way, because the fault was structural.**

| process | was | now |
|---|---|---|
| `fin_invoice_matching` | #5 | **#1** (0.721) |
| `inv_contract_management` | #8 | #3 |
| `fin_purchase_order_management` | **#1** | **#11** |
| `fin_payment_processing` | #7 | #13 |

The three at the bottom are the three that cannot be drafted at all.
`fin_invoice_matching` is now clear of second place by a wide margin — it is
the largest process by time *and* fully list-resolvable, which is the
combination I spent two days failing to see.

**No process in dataset B has judgement exceptions left.** Once Day 4
reclassified `fin_invoice_matching`'s 差異 branch as predictable, every branch
observed across 15 sessions is decided by a field that exists on the record
before the work starts. That is a much stronger automatability claim than Day
3 made, and it rests entirely on the input-vs-output test — which is why I
wrote that test rather than eyeballing the correlation.

### Scope

Five configured: `hr_expense_settlement` (84/213 drafted),
`fin_invoice_matching` (54/86), `inv_contract_management` (64/64),
`hr_leave_application` (40/40), `fin_purchase_order_management` (0/81).
**484 pending, 242 drafted (50%).**

Added `inv_contract_management` on the corrected ranking. **Kept
`fin_purchase_order_management` despite #11** — it costs one config entry and
it is the honest demonstration that the tool fails visibly. The plan asked for
unhandled cases to fail loudly rather than silently, and a process that cannot
be automated at all is the sharpest test of that. Deleting it would have made
the demo look better and the submission worse.

### On the UI

Rohith asked for premium rather than vibe-coded, so I built it as an operator
tool — someone works several hundred of these in a sitting — not a dashboard.
Reference points are Linear and Superhuman: density, keyboard reach, one
accent colour, motion only where it confirms a state change.

Concretely: a design-token system with a warm neutral scale (long sessions are
easier than on pure grey), tabular numerals for amounts and IDs, a Japanese
font stack with looser leading for JP text, light and dark, reduced-motion
honoured, focus-visible rings, live regions on the audit trail and toasts.
`J`/`K`/`↵`/`E` run the whole review loop without the mouse.

### What looking at it caught

I screenshotted the running app rather than trusting the build, and found
three things I would otherwise have shipped:

- **The record rows were broken.** Subject and detail ran together on one line
  — "福岡システム設計請求書承認 INV-2026-7347 · 定常" — because I styled a
  `<span>` with `margin-top` and spans are inline. Two seconds to fix, would
  have been embarrassing to leave.
- **A heading was lying.** Drafted records showed "Why this needs you" above
  the note "no policy threshold configured". That note is context, not a
  blocker, and the heading told the operator a ready record needed attention.
  Split `blockers` from `notes` server-side and gave them separate headings
  and styling.
- **The sidebar bars showed wrong data.** The ready/review split rendered only
  for the open queue, because `ready` was set on a process only after fetching
  its queue. Moved the computation to `/api/processes` so every bar is right
  on first paint.

None of these would have been caught by the build passing, which it did
throughout.

### Bulk approve, and why it stops early

With 84 drafted expense records, one-at-a-time is 84 keystrokes, so bulk is
the actual productivity feature rather than a nicety. Three decisions in it:

- **Behind a confirmation** showing the count and a sample of the sentence
  that will be written on every record. Approving 84 payroll records in one
  action is exactly the operation that is expensive to get wrong.
- **Each record still submitted individually.** The portal has no batch
  endpoint; inventing one would hide that a real integration makes N calls and
  can fail partway.
- **Stops at the first failure.** A partial batch with a gap in the middle is
  much harder for an operator to reconcile than one that stopped at a known
  point — and the portal's behaviour on a failed submit is unobserved, so
  pressing on would be guessing. Verified with a deliberately bad record
  mid-batch: two submitted, stopped, counts correct.

### Replay: finally a real accuracy number

Every evaluation so far has been structural — tiling, coverage, agreement with
an independent code. None of it answers what a client asks first: *if this had
been running during those sessions, would it have been right?*

It turns out that is answerable, and I should have seen it earlier. The
operators left their answers behind: every recovered execution ends with the
comment its worker typed, and the tool drafts a comment from the same record.
So they compare character for character. `src/replay.py`.

**204 of 205 drafted comments match what the operator actually wrote — 99.5%**,
across 308 executions linked to a portal record. `fin_invoice_matching` 42
exact and 22 declined (the 調整 exceptions), `hr_expense_settlement` 76 and 13,
`inv_contract_management` 32 and 0, `hr_leave_application` 54 and 0,
`fin_purchase_order_management` 0 and 68 — which is exactly the shape the
definitions predict.

This is the only measured accuracy figure in the whole project. `gt.jsonl`
never arrived so Step 1 boundary accuracy stays unmeasurable, but comment
accuracy never had to be.

**The first run reported 0.0%.** Every single match scored as a mismatch. The
cause: some operators write the completion text into Notepad first, as
`精算確認メモ / P1-07109774-002 / 経費精算確認済み。費目：…`. The business
sentence inside is identical — the header and ID are the operator's own
scaffolding. I nearly concluded the tool was broken. Scored those as
`exact_in_memo` and counted them correct, with the reasoning written into the
module rather than quietly relaxing the comparison.

**The second run linked 17 of 601 executions.** Most completion comments name
the case only in prose, so an ID lookup finds almost nothing. Linking instead
on (process, variant, amount, date) — what actually identifies a row on these
screens — took it to 308. One bug inside that fix: `variant_map` stores the
comment phrase *with* its trailing 。 while the parsed variant has none, so
every invoice execution silently failed to link until both sides were
stripped.

The one remaining mismatch is a segment holding two consecutive leave
approvals, so the "actual" is two comments concatenated. That is a Step 1
artefact, and at 1 in 205 not worth chasing.

### The blocked process was one fetch away

I had written `fin_purchase_order_management` off twice — 0 of 81, list view
lacks the deciding field. Before accepting that for the report I went looking
for what the portal renders when an operator *opens* a record, since the Day 4
screenshots clearly showed a detail pane.

Eight were captured in `extracted_text`. The purchase-order one carries a
`reason` field that is the **entire body of the completion comment**:

    reason : 定期発注：電子基板ユニット　数量 176　合計 842,336円　通常
    comment: 発注管理処理。<reason>。発注書確認・登録完了。

Checked it properly rather than on one example: **68 of 68** recorded
purchase-order comments decompose to that template, 61 with the exact shape of
the captured pane. So one fetch makes it a string substitution. Same lesson as
the 種別 discovery on Day 4 — look at what the portal renders, not at what the
list column shows.

**The 7 that did not fit were the most useful part.** They read
`発注変更：事務用品　数量 87　合計 3,206,385円　要注意` — a **fifth order
type** and a **third urgency value**, neither of which appears in the list view
at all (there is no urgency column). A whole branch of the process existed
outside the columns and was invisible until the comments were parsed. 要注意
now routes to a person alongside 緊急.

I did not overclaim it as solved. Only one pane was captured, so the mock
cannot serve 81 details and the real endpoint has still never been seen. The
definition carries a `detail_source` block naming the field, what it fills,
the evidence, and the status: *specified, not implemented*. `field_audit.py`
now reports "fetch contract: specified" versus "unknown", which turns 68 of
the 135 supposedly-blocked executions into an integration task with a known
shape.

**The validator earned its keep.** I extended it so a field may come from a
list column or a declared `detail_source`, and a template slot with no stated
source is an error. It immediately rejected my new definition twice: an
exception field with no source, then `urgency` — which is parsed out of the
composite `reason` string rather than returned separately, and I had not said
so. Both were real omissions, not false positives.

One self-inflicted detour: my first attempt to replace the definition used a
regex to find the block boundaries, which cut the file mid-dict and produced a
syntax error. Restored from git and replaced it by line range instead. Not
interesting except as a reminder that structured edits to structured files
should not be done with pattern matching.

### Implementing the fetch, and what it exposed

Specifying a contract is not the same as showing it works, so I built the path
end to end: `portal/details.json` serves the 4 captured panes,
`MockPortalClient.getRecord()` attaches `_detail` where one exists, and
`assist.js` reads the declared `detail_source`, substitutes `reason`, and
parses the urgency token out of the composite string for routing.

**The process that was 0 of 81 now drafts the record the fetch data exists
for**, producing exactly the template sentence, and the other 81 name the
missing field (`reason`) rather than saying something vague. That distinction
matters for the report: it is an unbuilt integration, not an undecidable case.

**A harvesting bug nearly hid the whole thing.** The one purchase-order record
with a detail pane was not in the pending queue at all — its earliest *list*
capture already showed 完了, while the detail pane had caught it at 未確認
minutes earlier. Taking the starting status from list views alone dropped the
only record that could demonstrate any of this. `harvest_records.py` now treats
detail panes as status observations too. I found it only because I expected
`ready=1` and got `ready=0`, which is a good argument for predicting the number
before running the command.

### Tests, and why now

`server/assist.test.js`, 12 tests, `npm test`.

The replay is stronger evidence than any unit test — 601 real executions — but
it can only exercise branches that actually happened, and two kinds did not.
**要注意 urgency** appears in 7 completion comments and in no captured detail
pane, so the routing it triggers cannot be verified from data at all. And the
refusal paths — empty comment, unknown variant, unfetched detail — are by
definition things operators never did.

Fixtures are copied from `portal/records.json` and `portal/detail_contract.json`
rather than invented, so a passing test means the same thing it would against
the portal. They also pin the three regressions I introduced this week: the
`variant_map` phrase-vs-value confusion, the blockers/notes split, and the
detail-vs-no-detail refusal.

### README restructured

`README.md` was still the client's brief. Moved it to `TASK.md` and wrote the
submission README as the **flow of the work** — context → episodes →
executions → ranking → tool — rather than a day-by-day account. The diary
belongs here in the work log; the front door should explain how the thing
works and what it found, with the honest limitations in their own section
rather than buried.

### Decisions taken

- **`draftable` replaces `data_access`** as the integration-cost component,
  because it measures what the tool needs rather than how the human coped.
- **Still no auto-approval.** The submit transport is unverified and the
  drafted comment asserts 規程内であることを確認した against a policy the tool
  does not have. A human confirms that sentence.
- **The document-check caveat is surfaced per record**, not buried in the
  report — `inv_contract_management`'s comment claims a document was checked
  and the tool cannot check it.

### Generative AI usage

Claude Code (Opus 5) throughout: the rescore module, the design system and the
React components. The three UI bugs above were found by rendering the app and
reading the screenshot, not by review — the same pattern as every other day
this week, where the failures surfaced by running things rather than by
inspecting them.

### Artifacts

| file | what it is |
|---|---|
| `src/rescore.py` | corrected ranking, with the delta against Day 3 |
| `server/index.js` | adds the batch endpoint and per-process ready counts |
| `server/assist.js` | blockers/notes split, document-check note |
| `web/src/styles.css` | the design system |
| `web/src/{App,Sidebar,QueueList,RecordDetail,BulkBar,Toasts}.jsx` | the tool |
| `portal/processes/inv_contract_management.json` | fourth configured process |
| `src/replay.py` | replays the tool against the real executions — 99.5% |
| `src/detail_panes.py` | recovers record detail panes; specifies the fetch contract |
| `portal/detail_contract.json` | what a per-record fetch must return, per process |
| `portal/details.json` | the 4 captured panes, served by the mock |
| `server/assist.test.js` | 12 tests covering branches the replay cannot reach |
| `README.md` | submission front door, written as the flow |
| `TASK.md` | the client's brief, moved off README |
| `reports/day5_findings.md` | ranking, scope, the tool, and the replay |
