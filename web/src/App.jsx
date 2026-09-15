import { useCallback, useEffect, useRef, useState } from 'react'
import { getQueue, listProcesses, submitBatch, submitRecord } from './api.js'
import { clock } from './format.js'
import QueueList from './QueueList.jsx'
import RecordDetail from './RecordDetail.jsx'
import Sidebar from './Sidebar.jsx'
import BulkBar from './BulkBar.jsx'
import Toasts from './Toasts.jsx'

export default function App() {
  const [processes, setProcesses] = useState([])
  const [active, setActive] = useState(null)
  const [queue, setQueue] = useState(null)
  const [loading, setLoading] = useState(true)
  const [selectedId, setSelectedId] = useState(null)
  const [editing, setEditing] = useState(false)
  const [submitted, setSubmitted] = useState([])
  const [toasts, setToasts] = useState([])
  const [bulkBusy, setBulkBusy] = useState(false)
  const [bulkDone, setBulkDone] = useState(0)
  // Below 1100px the detail pane is a drawer, so selecting a record has to
  // open it explicitly. Above that the class is inert and the pane is always
  // visible.
  const [drawerOpen, setDrawerOpen] = useState(false)
  const toastSeq = useRef(0)

  const toast = useCallback((msg, { id, error } = {}) => {
    const key = ++toastSeq.current
    setToasts((t) => [...t, { key, msg, id, error }])
    setTimeout(() => setToasts((t) => t.filter((x) => x.key !== key)), 3200)
  }, [])

  useEffect(() => {
    listProcesses()
      .then((ps) => {
        // Most drafted work first: the operator should land where the tool is
        // most useful, not on whichever process sorts first alphabetically.
        const ordered = [...ps].sort((a, b) => (b.ready ?? 0) - (a.ready ?? 0))
        setProcesses(ordered)
        if (ordered.length) setActive(ordered[0].label)
      })
      .catch((e) => { toast(e.message, { error: true }); setLoading(false) })
  }, [toast])

  const refresh = useCallback(
    async (label, keepSelection) => {
      if (!label) return
      try {
        const q = await getQueue(label)
        setQueue(q)
        setProcesses((ps) =>
          ps.map((p) =>
            p.label === label
              ? { ...p, counts: q.counts, ready: q.ready,
                  pending: q.total_pending, needs_review: q.needs_review }
              : p,
          ),
        )
        setSelectedId((cur) => {
          if (keepSelection && q.items.some((i) => i.record.ID === cur)) return cur
          return q.items[0]?.record.ID ?? null
        })
      } catch (e) {
        toast(e.message, { error: true })
      } finally {
        setLoading(false)
      }
    },
    [toast],
  )

  useEffect(() => {
    if (!active) return
    setLoading(true)
    setQueue(null)
    refresh(active, false)
  }, [active, refresh])

  const items = queue?.items ?? []
  const ordered = [
    ...items.filter((i) => !i.needs_review),
    ...items.filter((i) => i.needs_review),
  ]
  const index = ordered.findIndex((i) => i.record.ID === selectedId)
  const current = index >= 0 ? ordered[index] : null

  const move = useCallback(
    (delta) => {
      if (!ordered.length) return
      const next = Math.min(Math.max(index + delta, 0), ordered.length - 1)
      setSelectedId(ordered[next].record.ID)
      setEditing(false)
    },
    [index, ordered],
  )

  const approve = useCallback(
    async (item, comment) => {
      if (!item || !comment?.trim()) return
      // Advance first so the operator is never waiting on the network to keep
      // moving; a failure rolls the selection back via the toast + refresh.
      const nextId = ordered[Math.min(index + 1, ordered.length - 1)]?.record.ID
      try {
        const r = await submitRecord(active, item.record.ID, comment)
        setSubmitted((s) => [
          { id: r.record_id, msg: r.confirmation, at: clock(new Date()) },
          ...s,
        ])
        toast(r.confirmation, { id: r.record_id })
        await refresh(active, false)
        if (nextId && nextId !== item.record.ID) setSelectedId(nextId)
      } catch (e) {
        toast(e.message, { error: true })
        refresh(active, true)
      }
    },
    [active, index, ordered, refresh, toast],
  )

  const approveAll = useCallback(
    async (readyItems) => {
      setBulkBusy(true)
      setBulkDone(0)
      try {
        const payload = readyItems.map((i) => ({
          record_id: i.record.ID,
          comment: i.comment,
        }))
        const r = await submitBatch(active, payload)
        setBulkDone(r.submitted.length)
        setSubmitted((s) => [
          ...r.submitted.map((x) => ({
            id: x.record_id, msg: x.confirmation, at: clock(new Date()),
          })).reverse(),
          ...s,
        ])
        if (r.failure) {
          toast(
            `Stopped after ${r.submitted.length}. ${r.failure.record_id}: ${r.failure.error}`,
            { error: true },
          )
        } else {
          toast(`${r.submitted.length} submitted`)
        }
        await refresh(active, false)
      } catch (e) {
        toast(e.message, { error: true })
        refresh(active, true)
      } finally {
        setBulkBusy(false)
      }
    },
    [active, refresh, toast],
  )

  useEffect(() => {
    function onKey(e) {
      if (e.metaKey || e.ctrlKey || e.altKey) return
      const tag = e.target.tagName
      if (tag === 'TEXTAREA' || tag === 'INPUT') return

      if (e.key === 'j' || e.key === 'ArrowDown') { e.preventDefault(); move(1) }
      else if (e.key === 'k' || e.key === 'ArrowUp') { e.preventDefault(); move(-1) }
      else if (e.key === 'Enter') {
        e.preventDefault()
        if (current?.comment) approve(current, current.comment)
      } else if (e.key === 'e' || e.key === 'E') {
        e.preventDefault()
        if (current?.comment) setEditing((v) => !v)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [approve, current, move])

  const activeProcess = processes.find((p) => p.label === active)

  return (
    <>
      <div className="shell">
        <Sidebar processes={processes} active={active} onPick={setActive} />

        <main className="queue-pane">
          {/* Sidebar is hidden on the narrowest layout; queues stay reachable. */}
          <nav className="mobile-queues" aria-label="Processes">
            {processes.map((p) => (
              <button
                key={p.label}
                aria-current={p.label === active}
                onClick={() => setActive(p.label)}
              >
                <span className="jp">{p.display_name}</span>{' '}
                <span className="num">{p.pending ?? 0}</span>
              </button>
            ))}
          </nav>

          <header className="queue-head">
            <div className="queue-title">
              <h2 className="jp">{queue?.display_name ?? activeProcess?.display_name ?? '—'}</h2>
              <span className="sys jp">{activeProcess?.system.name}</span>
            </div>

            <div className="stats">
              <span className="stat">
                <b className="num">{queue?.total_pending ?? '—'}</b>
                <span>pending</span>
              </span>
              <span className="stat is-ready">
                <b className="num">{queue?.ready ?? '—'}</b>
                <span>drafted</span>
              </span>
              <span className="stat is-review">
                <b className="num">{queue?.needs_review ?? '—'}</b>
                <span>needs a person</span>
              </span>
            </div>

            {queue && (
              <div className="transition">
                <span className="pill jp">{queue.states.pending}</span>
                <span aria-hidden="true">→</span>
                <span className="pill jp">{queue.states.done}</span>
                <span className="jp" style={{ marginLeft: 4 }}>
                  {queue.confirmation}
                </span>
              </div>
            )}
          </header>

          <BulkBar
            ready={ordered.filter((i) => !i.needs_review)}
            template={ordered.find((i) => i.comment)?.comment}
            onConfirm={approveAll}
            busy={bulkBusy}
            progress={bulkDone}
          />

          <QueueList
            items={ordered}
            selectedId={selectedId}
            onSelect={(id) => {
              setSelectedId(id)
              setEditing(false)
              setDrawerOpen(true)
            }}
            loading={loading}
          />
        </main>

        <RecordDetail
          item={current}
          queue={{ submitted }}
          onApprove={approve}
          editing={editing}
          setEditing={setEditing}
          open={drawerOpen}
          onClose={() => setDrawerOpen(false)}
        />
      </div>

      {drawerOpen && (
        <div className="scrim" onClick={() => setDrawerOpen(false)} />
      )}

      <Toasts toasts={toasts} />
    </>
  )
}
