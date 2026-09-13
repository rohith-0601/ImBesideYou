import { useEffect, useState, useCallback } from 'react'
import { listProcesses, getQueue, submit } from './api.js'
import ProcessPicker from './ProcessPicker.jsx'
import ReviewQueue from './ReviewQueue.jsx'

export default function App() {
  const [processes, setProcesses] = useState([])
  const [active, setActive] = useState(null)
  const [queue, setQueue] = useState(null)
  const [error, setError] = useState(null)
  const [log, setLog] = useState([])

  useEffect(() => {
    listProcesses()
      .then((ps) => {
        setProcesses(ps)
        if (ps.length) setActive(ps[0].label)
      })
      .catch((e) => setError(e.message))
  }, [])

  const refresh = useCallback(() => {
    if (!active) return
    getQueue(active).then(setQueue).catch((e) => setError(e.message))
  }, [active])

  useEffect(() => {
    setQueue(null)
    refresh()
  }, [active, refresh])

  async function onApprove(item) {
    try {
      const r = await submit(active, item.record.ID, item.comment)
      setLog((l) => [
        { id: r.record_id, msg: r.confirmation, at: new Date() },
        ...l,
      ].slice(0, 40))
      refresh()
      setProcesses((ps) =>
        ps.map((p) => (p.label === active ? { ...p, counts: r.counts } : p)),
      )
    } catch (e) {
      setError(e.message)
    }
  }

  return (
    <div className="app">
      <header>
        <h1>Back-office Assist</h1>
        <p className="sub">
          Prepares each pending case and drafts its completion comment.
          A person approves every one — nothing is submitted automatically.
        </p>
      </header>

      {error && (
        <div className="error" onClick={() => setError(null)}>
          {error} <span className="dismiss">dismiss</span>
        </div>
      )}

      <ProcessPicker
        processes={processes}
        active={active}
        onPick={setActive}
      />

      {queue ? (
        <ReviewQueue queue={queue} onApprove={onApprove} />
      ) : (
        <p className="muted">Loading queue…</p>
      )}

      {log.length > 0 && (
        <section className="log">
          <h2>Submitted this session</h2>
          <ul>
            {log.map((l, i) => (
              <li key={i}>
                <code>{l.id}</code> <span className="ok">{l.msg}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}
