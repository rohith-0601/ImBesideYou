import { useState } from 'react'

/**
 * Bulk approve, behind a confirmation.
 *
 * The confirmation is not ceremony. Approving 84 payroll records in one
 * action is exactly the operation that is expensive to get wrong, and the
 * operator should see the count and the sentence that will be written on
 * every one of them before it happens.
 */
export default function BulkBar({ ready, template, onConfirm, busy, progress }) {
  const [open, setOpen] = useState(false)

  if (!ready.length) return null

  if (busy) {
    return (
      <div className="bulk is-busy" role="status" aria-live="polite">
        <span className="bulk-progress">
          <i style={{ width: `${(progress / ready.length) * 100}%` }} />
        </span>
        <span className="num">
          Submitting {progress} of {ready.length}…
        </span>
      </div>
    )
  }

  if (!open) {
    return (
      <div className="bulk">
        <span className="bulk-text">
          <b className="num">{ready.length}</b> drafted and ready
        </span>
        <button className="btn" onClick={() => setOpen(true)}>
          Approve all
        </button>
      </div>
    )
  }

  return (
    <div className="bulk is-open">
      <div className="bulk-confirm">
        <p className="bulk-q">
          Approve <b className="num">{ready.length}</b> records? Each is
          submitted individually and stops at the first failure.
        </p>
        {template && (
          <p className="bulk-sample jp">
            e.g. <span>{template}</span>
          </p>
        )}
      </div>
      <div className="bulk-actions">
        <button className="btn" onClick={() => setOpen(false)}>
          Cancel
        </button>
        <button
          className="btn btn-primary"
          style={{ flex: '0 0 auto' }}
          onClick={() => { setOpen(false); onConfirm(ready) }}
        >
          Approve {ready.length}
        </button>
      </div>
    </div>
  )
}
