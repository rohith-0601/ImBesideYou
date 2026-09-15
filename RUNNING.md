# Running the Step 3 prototype

Two processes: an Express API over the portal adapter, and a Vite/React front
end that proxies `/api` to it.

## Prerequisites

- Node 18+ (developed on 26)
- Python 3.11+, only if you want to regenerate the portal artefacts from the
  raw logs. The tool itself needs no Python.

The committed artefacts (`portal/`, `segments/`) mean the app runs from a
fresh clone without the 12 GB of raw data.

> If `npm install` reports that install scripts were skipped, Vite's `esbuild`
> binary will not have been fetched. Run `npm install-scripts approve esbuild`
> then `npm rebuild esbuild`. This is an npm security setting, not a repo
> problem.

## 1. Start the API

```bash
cd server
npm install
npm start            # http://127.0.0.1:8765
```

Expected output:

```
portal adapter API on http://127.0.0.1:8765
  fin_invoice_matching: 86 pending
  fin_purchase_order_management: 81 pending
  hr_expense_settlement: 213 pending
  hr_leave_application: 40 pending
  inv_contract_management: 64 pending
```

## 2. Start the front end

```bash
cd web
npm install
npm run dev          # http://localhost:5173
```

Open <http://localhost:5173>.

## What you should see

Five queues in the sidebar, ordered by how much work the tool has actually
drafted. Each splits into **drafted** (comment written, awaiting your
approval) and **needs a person** (the tool declines, with its reason).

**Keyboard:** `J`/`K` move · `↵` approve and advance · `E` edit the comment.
The review loop runs without the mouse.

- **勤怠・休暇申請** — 40 pending, all 40 ready. The cleanest case.
- **請求書承認・経費精算** — 86 pending, 54 ready, 32 needing review. The split
  is 種別: `定常` records get 差異なし承認 drafted, `調整` records are routed
  to a human. 種別 predicts the outcome 64/64 in the recorded data and is set
  before the work begins.
- **経費精算（確認）** — 213 pending, 84 ready, 129 needing review. The 129 are
  records whose 種別 is `調整`, which the definition marks as an exception.
- **契約管理** — 64 pending, all 64 drafted. Every record carries a note: the
  comment asserts 関連書類確認済み and the portal names a `.docx` you are
  expected to open. The tool drafts the sentence; you confirm the document.
- **発注管理** — 81 pending, **0 drafted**. Its list view does not expose the
  order type that decides the branch, so the tool cannot classify any of them
  without a per-record fetch that does not exist yet. This is a real finding,
  not a bug: see `reports/day4_findings.md` §6 and `day5_findings.md` §2.

Across all five: **484 pending, 242 drafted (50%)**.

**Bulk approve** appears above the queue when anything is drafted. It shows
the count and a sample of the sentence before committing, submits each record
individually, and stops at the first failure rather than leaving a gap in the
middle of a batch.

Approving calls `POST /api/processes/:p/submit`, which enforces the state
machine recovered from the logs. Try approving the same record twice — the
second is refused, because the real portal's behaviour on a repeat submit has
never been observed.

## Where the data comes from

Nothing here is invented. The 528 records were parsed out of recorded screen
text in dataset B (`portal/records.json`), the screen contracts and state
machines from 939 screen dumps (`portal/contract.json`), and the four process
definitions are validated against both (`portal/processes/*.json`).

To regenerate them:

```bash
cd src
python portal_contract.py     # -> portal/contract.json
python harvest_records.py     # -> portal/records.json
python process_defs.py        # -> portal/processes/*.json, validates
```

## The mock, and why

The three portals ran on the client's Windows machines at
`127.0.0.1:5132/5133/5134` during the July 2026 recording and are unreachable.
`server/portalClient.js` therefore ships two implementations behind one
interface: `MockPortalClient` (real records, real state machine, in memory)
and `HttpPortalClient`, whose methods throw with the specific question each
one needs answered against a live instance. Swapping them is the only change
required once someone can reach a running system.

## Tests

**Drafting logic** — `cd server && npm test` (12 tests). Covers the branches the
replay in `src/replay.py` cannot reach: 要注意 urgency appears in seven
completion comments and no captured detail pane, and the refusal paths are by
definition things operators never did.

**End-to-end UI** — `cd web && npm run e2e` (17 checks). Drives a real browser:
selects a record, approves it, uses the keyboard, and checks the drawer and
phone layouts. It needs the stack already running, on spare ports so it cannot
disturb a dev server you have open:

```bash
cd server && PORT=8791 npm start
cd web    && npx vite --port 5191 --strictPort
cd web    && npm run e2e
```

Every UI bug in this project was found by rendering the app rather than reading
the code, and the last one — `Escape` not closing the drawer — needed a click,
which screenshots could not provide.
