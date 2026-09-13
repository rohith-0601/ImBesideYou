# Running the Step 3 prototype

Two processes: an Express API over the portal adapter, and a Vite/React front
end that proxies `/api` to it.

## Prerequisites

- Node 18+ (developed on 26)
- Python 3.11+ with the analysis venv, only if you want to regenerate the
  portal artefacts

## 1. Start the API

```bash
cd server
npm install
npm start            # http://127.0.0.1:8765
```

Expected output:

```
portal adapter API on http://127.0.0.1:8765
  fin_purchase_order_management: 81 pending
  hr_expense_settlement: 213 pending
  hr_leave_application: 40 pending
```

## 2. Start the front end

```bash
cd web
npm install
npm run dev          # http://localhost:5173
```

Open <http://localhost:5173>.

## What you should see

Three process tabs. Pick one and the queue splits into **ready** (the tool has
drafted the completion comment; you approve or not) and **needs review** (the
tool declines to draft, with its reason).

- **勤怠・休暇申請** — 40 pending, all 40 ready. The cleanest case.
- **経費精算（確認）** — 213 pending, 84 ready, 129 needing review. The 129 are
  records whose 種別 is `調整`, which the definition marks as an exception.
- **発注管理** — 81 pending, **0 ready**. Its list view does not expose the
  order type that decides the branch, so the tool cannot classify any of them
  without a per-record fetch that does not exist yet. This is a real finding,
  not a bug: see `reports/day4_findings.md` §6.

Approving calls `POST /api/processes/:p/submit`, which enforces the state
machine recovered from the logs. Try approving the same record twice — the
second is refused, because the real portal's behaviour on a repeat submit has
never been observed.

## Where the data comes from

Nothing here is invented. The 420 records were parsed out of recorded screen
text in dataset B (`portal/records.json`), the screen contracts and state
machines from 939 screen dumps (`portal/contract.json`), and the three process
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
