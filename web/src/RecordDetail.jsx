import { useEffect, useRef, useState } from 'react'
import { subjectOf, visibleFields } from './format.js'

export default function RecordDetail({ item, queue, onApprove, editing, setEditing }) {
  const [draft, setDraft] = useState(item?.comment ?? '')
  const areaRef = useRef(null)

  useEffect(() => {
    setDraft(item?.comment ?? '')
    setEditing(false)
  }, [item?.record?.ID])

  useEffect(() => {
    if (editing) areaRef.current?.focus()
  }, [editing])

  if (!item) {
    return (
      <section className="detail-pane">
        <div className="empty" style={{ marginTop: 'auto', marginBottom: 'auto' }}>
          <strong>No record selected</strong>
          Pick one from the queue.
        </div>
      </section>
    )
  }

  const rec = item.record
  const canSubmit = Boolean(draft.trim())
  const blockers = item.blockers ?? item.reasons ?? []
  const notes = item.notes ?? []

  return (
    <section className="detail-pane" aria-label="Record detail">
      <header className="detail-head">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span className="rid mono">{rec.ID}</span>
          <span className={item.needs_review ? 'badge is-review' : 'badge is-ready'}>
            {item.needs_review ? 'Needs a person' : 'Drafted'}
          </span>
        </div>
        <h3 className="jp">{subjectOf(rec)}</h3>
      </header>

      <div className="detail-body">
        <dl className="field-grid">
          {visibleFields(rec).map(([k, v]) => (
            <div key={k} style={{ display: 'contents' }}>
              <dt className="jp">{k}</dt>
              <dd className="jp num">{v}</dd>
            </div>
          ))}
        </dl>

        {blockers.length > 0 && (
          <>
            <p className="section-label">Why this needs a person</p>
            <ul className="reasons">
              {blockers.map((r, i) => (
                <li key={i} className="jp">{r}</li>
              ))}
            </ul>
          </>
        )}

        {notes.length > 0 && (
          <>
            <p className="section-label">Before you approve</p>
            <ul className="notes">
              {notes.map((r, i) => (
                <li key={i} className="jp">{r}</li>
              ))}
            </ul>
          </>
        )}

        <p className="section-label">
          Completion comment {editing && '— editing'}
        </p>
        {item.comment || editing ? (
          <div className={editing ? 'comment-box editable' : 'comment-box'}>
            {editing ? (
              <textarea
                ref={areaRef}
                className="jp"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Escape') { setDraft(item.comment ?? ''); setEditing(false) }
                  e.stopPropagation()
                }}
                aria-label="Completion comment"
              />
            ) : (
              <span className="jp">{draft}</span>
            )}
          </div>
        ) : (
          <div className="comment-box is-empty jp">
            この案件は自動生成できません。担当者が portal で直接処理してください。
          </div>
        )}
      </div>

      <footer className="detail-foot">
        <button
          className="btn btn-primary"
          disabled={!canSubmit}
          onClick={() => onApprove(item, draft)}
        >
          Approve <kbd>↵</kbd>
        </button>
        <button
          className="btn"
          onClick={() => setEditing((v) => !v)}
          disabled={!item.comment && !editing}
        >
          {editing ? 'Done' : 'Edit'} <kbd>E</kbd>
        </button>
      </footer>

      <div className="audit" aria-live="polite">
        <div className="audit-head">
          <h4>This session</h4>
          <span style={{ fontSize: 11, color: 'var(--fg-faint)' }}>
            {queue.submitted.length} submitted
          </span>
        </div>
        <div className="audit-list">
          {queue.submitted.length === 0 ? (
            <p style={{ fontSize: 11.5, color: 'var(--fg-faint)', margin: 0 }}>
              Nothing submitted yet.
            </p>
          ) : (
            queue.submitted.map((s, i) => (
              <div key={i} className="audit-item">
                <span className="t mono">{s.at}</span>
                <span className="mono" style={{ color: 'var(--fg-muted)' }}>{s.id}</span>
                <span className="msg jp">{s.msg}</span>
              </div>
            ))
          )}
        </div>
      </div>
    </section>
  )
}
