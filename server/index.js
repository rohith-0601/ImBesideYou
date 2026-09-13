/**
 * Express API over the portal adapter.
 *
 * Routes
 *   GET  /api/processes                  the configured process definitions
 *   GET  /api/processes/:p/queue         pending records, each with a
 *                                        proposed decision and drafted comment
 *   POST /api/processes/:p/submit        {record_id, comment} -> confirmation
 *   GET  /api/health
 *
 * Nothing is submitted without an explicit POST from the operator. The tool
 * prepares; a human commits. That is not a UI preference - the submit
 * transport is unverified (Day 4 §5) and these are HR and finance records.
 */

import express from 'express'
import { buildQueue } from './assist.js'
import { MockPortalClient, PortalError } from './portalClient.js'

const PORT = process.env.PORT || 8765
const app = express()
app.use(express.json())

const client = new MockPortalClient()

app.get('/api/health', (_req, res) => {
  res.json({ ok: true, backend: 'mock', processes: Object.keys(client.defs) })
})

app.get('/api/processes', (_req, res) => {
  res.json(
    Object.values(client.defs).map((d) => ({
      label: d.label,
      display_name: d.display_name,
      system: d.system,
      states: d.states,
      variants: d.variants,
      confirmation: d.confirmation,
      counts: client.counts(d.label),
      evidence: d.evidence,
      rule: d.rule,
    })),
  )
})

app.get('/api/processes/:process/queue', (req, res) => {
  try {
    res.json(buildQueue(client, req.params.process))
  } catch (e) {
    res.status(e instanceof PortalError ? 404 : 500).json({ error: e.message })
  }
})

app.post('/api/processes/:process/submit', (req, res) => {
  const { record_id, comment } = req.body ?? {}
  if (!record_id) return res.status(400).json({ error: 'record_id is required' })
  try {
    const confirmation = client.submit(req.params.process, record_id, comment)
    res.json({
      record_id,
      confirmation,
      counts: client.counts(req.params.process),
    })
  } catch (e) {
    res.status(e instanceof PortalError ? 409 : 500).json({ error: e.message })
  }
})

app.listen(PORT, '127.0.0.1', () => {
  console.log(`portal adapter API on http://127.0.0.1:${PORT}`)
  for (const label of Object.keys(client.defs)) {
    console.log(`  ${label}: ${client.listRecords(label).length} pending`)
  }
})
