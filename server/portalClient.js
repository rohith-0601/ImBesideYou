/**
 * The seam between the tool and the portal.
 *
 * Everything the tool knows about the portal goes through this interface.
 * Two implementations:
 *
 *   MockPortalClient - backed by the 420 real records harvested from the
 *     recorded screen dumps (portal/records.json), enforcing the real state
 *     machine recovered in portal/contract.json. This is what runs today,
 *     because the three portals are unreachable: they lived on the client's
 *     Windows machines during the July 2026 recording.
 *
 *   HttpPortalClient - a deliberate stub. Each method throws with the
 *     specific question that must be answered against a live instance, so the
 *     unknowns sit in the code rather than in a paragraph of a report.
 *
 * Day 4 established the submit *semantics* - each screen is a two-state
 * machine with one transition and a known confirmation string, over 345
 * observed transitions. It did not establish the *transport*. The mock is
 * faithful to the semantics; nothing can be faithful to a transport nobody
 * has seen.
 */

import { readFileSync, readdirSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const REPO_ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')
const PORTAL_DIR = join(REPO_ROOT, 'portal')

export class PortalError extends Error {}

export function loadDefinitions() {
  const dir = join(PORTAL_DIR, 'processes')
  const defs = {}
  for (const f of readdirSync(dir).filter((f) => f.endsWith('.json'))) {
    const d = JSON.parse(readFileSync(join(dir, f), 'utf8'))
    defs[d.label] = d
  }
  return defs
}

export class MockPortalClient {
  constructor(definitions = loadDefinitions()) {
    this.defs = definitions
    this.records = JSON.parse(
      readFileSync(join(PORTAL_DIR, 'records.json'), 'utf8'),
    )
    // In-memory only, so a restart brings the same queue back pending and a
    // run is reproducible.
    this.submitted = new Map()
  }

  _defn(process) {
    const d = this.defs[process]
    if (!d) throw new PortalError(`no process definition for '${process}'`)
    return d
  }

  _statusOf(rec) {
    return this.submitted.get(rec.ID) ?? rec['ステータス'] ?? ''
  }

  listRecords(process, pendingOnly = true) {
    const defn = this._defn(process)
    const pending = defn.states.pending
    return (this.records[process] ?? [])
      .map((rec) => ({ ...rec, 'ステータス': this._statusOf(rec) }))
      .filter((rec) => !pendingOnly || rec['ステータス'] === pending)
  }

  getRecord(process, recordId) {
    const rec = (this.records[process] ?? []).find((r) => r.ID === recordId)
    if (!rec) throw new PortalError(`${recordId} not found in ${process}`)
    return { ...rec, 'ステータス': this._statusOf(rec) }
  }

  submit(process, recordId, comment) {
    const defn = this._defn(process)
    const { pending, done } = defn.states
    const rec = this.getRecord(process, recordId)

    // Recorded transitions only ever go pending -> done. A repeat submit is
    // refused rather than silently accepted, because the real portal's
    // behaviour on one has never been observed.
    if (rec['ステータス'] !== pending) {
      throw new PortalError(
        `${recordId} is '${rec['ステータス']}', not '${pending}' - refusing to ` +
          `submit. The real portal's behaviour on a repeat submit is ` +
          `unobserved (Day 4 §5).`,
      )
    }
    if (!comment || !comment.trim()) {
      throw new PortalError('refusing to submit an empty comment')
    }

    this.submitted.set(recordId, done)
    return defn.confirmation
  }

  counts(process) {
    const defn = this._defn(process)
    const out = { [defn.states.pending]: 0, [defn.states.done]: 0 }
    for (const rec of this.records[process] ?? []) {
      const st = this._statusOf(rec)
      out[st] = (out[st] ?? 0) + 1
    }
    return out
  }
}

export class HttpPortalClient {
  static UNKNOWNS = {
    listRecords:
      'Does the SPA read its list from a JSON endpoint, or is it ' +
      'server-rendered? No XHR is visible - L3 covers 13.5% of events and ' +
      'captured no network calls.',
    getRecord:
      'Is there a per-record endpoint, or is detail already in the list ' +
      'payload? Matters most for fin_purchase_order_management, which must ' +
      'open each record to classify it.',
    submit:
      'Endpoint, method, payload shape, auth, idempotency, and the failure ' +
      'response. 345 transitions were observed as effects; the call that ' +
      'causes them has never been seen.',
  }

  constructor(baseUrl) {
    this.baseUrl = baseUrl
  }

  _blocked(method) {
    throw new Error(
      `${method} against ${this.baseUrl}: ${HttpPortalClient.UNKNOWNS[method]}`,
    )
  }

  listRecords() { this._blocked('listRecords') }
  getRecord() { this._blocked('getRecord') }
  submit() { this._blocked('submit') }
}
