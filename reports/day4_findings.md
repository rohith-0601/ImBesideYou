# Day 4 — Findings

Day 4's first task was to verify the submit path against the real portals,
because Day 3 concluded the terminal action was unobserved and everything in
Step 3 rested on it.

The portals are gone, the verification took a different route, and on the way
it exposed a bug that had been silently suppressing the richest source in the
dataset since Day 1 — which in turn overturned one of Day 3's central claims.

---

## 1. The portals are unreachable, as expected

```
port 5132: no response
port 5133: no response
port 5134: no response
```

They ran on the client's Windows machines during the July 2026 recording.
Nothing is listening here. So the submit path cannot be exercised, and the
contract has to be reconstructed from evidence with the real integration left
as an explicit open risk.

## 2. The bug: 633,859 characters of screen text were invisible

`context.extracted_text` is a **dict**:

```python
{"text": "...", "source": "text_pattern", "char_count": 890, "truncated": False}
```

Every guard written against it since Day 1 was `isinstance(x, str)`, which
matches nothing. The result: **939 screen dumps, 633,859 characters — never
read.** Not by `case_extract.text_surfaces` on Day 1, not by the Day 3 probe
that went looking for the 種別 column.

The failure mode is the dangerous kind. Nothing errored; a filter just
returned empty, and an empty result reads exactly like a negative finding. Day
3 reported "the 種別 column never appears in the event log at all" with
apparent evidence behind it, and that sentence was produced by a type
mismatch.

`data_loader` now exposes a flattened `screen_text` column so the same mistake
cannot recur, and `case_extract` is corrected.

## 3. What the screen dumps contain

Full list views, in reading order: brand, system, department, clock, operator,
sidebar entries with pending counts, breadcrumb, screen title, count line,
table caption, column headers, every visible row, and **the confirmation toast
after an action**:

```
ID / 社員ID / 氏名 / 申請種別 / 期間・詳細 / 部署 / ステータス
P2-07047510-001 / E2003 / 上野 大樹 / 半日有給申請 / 2026-07-13 / 経理部 / 承認
...
P2-07047510-004: 申請を承認しました
```

`src/portal_contract.py` parses these into a machine-readable contract
(`portal/contract.json`).

## 4. Day 3's central claim was wrong: the invoice branch is fully predictable

Day 3 ranked `fin_invoice_matching` 7th largely because its 34.4% exception
rate looked like irreducible human judgement, with the 種別 column apparently
absent from the log.

Joining the 64 invoices that appear in **both** a screen dump and a completion
comment:

| 種別 | 差異なし承認 | 差異あり要確認 |
|---|---|---|
| 定常 | **42** | 0 |
| 調整 | 0 | **22** |

**64/64 — 100%.** The discrepancy outcome is a deterministic function of a
column that is on screen, in the log, and visible before the work starts. It
is not judgement at all.

Reclassified from `judgement` to `predictable`. `fin_invoice_matching` rises
from 7th (0.118) to **5th (0.180)**.

**The scope decision does not change**, and it is worth being clear why: it
survives on a different reason than before. Invoice matching is no longer
"unpredictable judgement" — it is now "predictable but desktop-heavy", with
only 25% of executions staying in the browser. The deferral stands; the
justification for it is now accurate.

## 5. The submit path: semantics recovered, mechanics still unknown

Day 3's "the terminal action is invisible" was based on button clicks — 7
`✓ 承認` across 20,477 events. That remains true. But the *effect* of the
submit is richly recorded: the same list appears in successive dumps with
statuses changed, and the confirmation toast names the record.

Every screen turns out to be a **two-state machine with exactly one
transition**. The eleven substantive screens are below; `contract.json` holds
13 entries in total, the extra two being low-volume fragments from truncated
dumps (350 transitions all told):

| screen | pending → done | observed | confirmation |
|---|---|---|---|
| 勤怠・休暇申請 | 申請中 → 承認 | 23 | 申請を承認しました |
| 経費精算・給与変更 | 未処理 → 登録済み | 83 | 登録確定しました |
| 請求書承認・経費精算 | 未処理 → 登録済み | 46 | 登録確定しました |
| 在庫管理 | 未処理 → 登録済み | 48 | 登録確定しました |
| 入社手続き | 照合中 → 完了 | 39 | 照合完了しました |
| 契約管理 | 処理待ち → 承認 | 28 | 申請を承認しました |
| 発注管理 | 未確認 → 完了 | 26 | 完了しました |
| IT申請 | 処理待ち → 処理完了 | 21 | 処理完了しました |
| 支払処理 | 照合中 → 完了 | 14 | 照合完了しました |
| 予算差異分析 | 処理待ち → 処理完了 | 10 | 処理完了しました |
| 福利厚生申請 | 処理待ち → 処理完了 | 7 | 処理完了しました |

So the risk is **narrower than Day 3 stated**. We know what a submit *does*
and what the system says back. What we still do not know is how to invoke it:
endpoint, payload, auth, idempotency, failure behaviour. That is an
integration unknown, not a semantic one — and it is the difference between
"we don't understand the process" and "we need an hour with the API".

Revised risk statement for the report: *the submit semantics are established
from 345 observed transitions across 11 screens; the transport is not, and
cannot be until someone can reach a running instance.*

## 6. The validator earned its place in ten seconds

`process_defs.validate()` rejected my first `fin_purchase_order_management`
definition: `exception_field: 変異` is not one of that screen's columns.

Chasing it down produced a genuine build constraint. The 発注管理 list shows
only `発注管理 PO-2026-5156` in its 項目 column — **the order type that
determines the branch is not in the list view at all.** It appears only in the
completion comment, i.e. after the worker has opened the record.

So this process needs a per-record fetch that the other two do not, to
classify each case before acting. Recorded in the definition as
`variant_source: record_detail` and flagged as a Day 5 build risk, rather than
discovered during implementation.

## 7. What exists now

| artefact | what it is |
|---|---|
| `portal/contract.json` | 11 screen contracts: columns, states, transitions, confirmations, field vocabularies |
| `portal/processes/*.json` | 3 validated process definitions for the chosen scope |
| `src/portal_contract.py` | rebuilds the contract from the dumps |
| `src/process_defs.py` | definition schema + validator |

## 8. What did not get done, and why

**The web app scaffold.** Day 4's plan had four items; the first one expanded
into the bug, the correction and the contract reconstruction, and I judged
finishing those worth more than starting the scaffold with a wrong contract
underneath it. The definitions are now evidence-backed and validated, which is
what the scaffold needs to be built against.

Day 5 therefore carries the scaffold plus the core build. That is a real
schedule risk and is recorded as one rather than absorbed quietly — the
mitigation is that the mock portal can be generated directly from
`contract.json`, which is a smaller job than designing it would have been.

## 9. Carried into Day 5

1. Generate the mock portal from `contract.json` — real columns, real status
   vocabularies, real records harvested from the dumps.
2. Scaffold the web app with the portal adapter behind an interface, so the
   mock can be swapped for a real client without touching the tool.
3. Build the review-and-approve flow for the three definitions.
4. Handle `fin_purchase_order_management`'s per-record fetch (§6).
5. Keep policy thresholds as configuration — they are still not inferable
   (every observed case was approved).
