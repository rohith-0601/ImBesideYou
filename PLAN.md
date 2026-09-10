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

## Day 2 — Step 1: segmentation algorithm → `segments.jsonl`

- Separate "case is visible on screen" from "case is being worked" — the
  list-view false-positive problem that currently inflates `payroll_change`.
- Reconcile overlapping case spans into a coherent, non-overlapping timeline
  per session, allowing for genuine interleaving (suspend/resume).
- Emit `segments.jsonl` for dataset B in the required schema.
- **Validation without ground truth:** since dataset A's `gt.jsonl` is gone,
  substitute (a) screenshot spot-checks at predicted boundaries — we have
  4,746 dataset B screenshots and can literally look at what was on screen,
  (b) internal consistency checks (segments tile the session without
  overlap; label matches the route actually in the foreground), and (c) a
  hand-labelled subset of 2–3 sessions to score against. State plainly in
  the report that this is weaker evidence than measured accuracy on A, and
  why that wasn't available.

## Day 3 — Step 2: process analysis and ROI prioritisation

- Per process: execution count, time consumed, operators involved, variance
  between executions (the "different handling patterns" question).
- Build the prioritisation on explicit criteria — volume × time × rule
  determinism ÷ implementation difficulty — and show the working, so the
  ordering is arguable rather than asserted.
- Assess feasibility per candidate: data access route, branch count,
  governance constraints, and what could only surface during build.
- **Decide the Step 3 target and scope, and write down what's deferred.**

## Day 4 — Step 3 foundation: web app scaffold + the hard integration

- Lock the stack and scaffold the app.
- Do the risky integration first, while there's still time to change course:
  get the app reading real portal data and driving the real target actions
  against the local portal (`127.0.0.1:5132/5133/5134`).
- Deliberately front-loaded: if the integration can't work, Day 4 is when to
  find out, not Day 6.

## Day 5 — Step 3 core build

- Build the actual automation path end to end for the chosen process.
- Human-in-the-loop by default: the operator reviews and approves rather
  than the tool acting blind — chosen because these are HR/payroll records
  where a silent wrong write is expensive.
- Handle the branch cases found on Day 3; make unhandled cases fail visibly
  and fall back to the manual path.

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
- **Over-counted `payroll_change` would mis-rank the automation candidates.**
  Volume feeds directly into prioritisation, so the Day 2 false-positive fix
  gates the credibility of Day 3's recommendation.
- **Small absolute data volume.** 176 minutes of wall-clock across 15
  sessions. The README says to compare processes against each other rather
  than trusting absolute figures — so the report must present relative
  ranking, not extrapolated annual savings.
