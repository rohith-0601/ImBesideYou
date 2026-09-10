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
