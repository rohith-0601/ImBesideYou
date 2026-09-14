import { useEffect, useRef } from 'react'
import { subjectOf, detailOf, yen } from './format.js'

function Row({ item, selected, onSelect, innerRef }) {
  const rec = item.record
  return (
    <button
      ref={innerRef}
      className="row"
      role="option"
      aria-selected={selected}
      onClick={onSelect}
      tabIndex={-1}
    >
      <span className={item.needs_review ? 'dot is-review' : 'dot is-ready'} />
      <span className="rid mono">{rec.ID}</span>
      <span>
        <span className="who jp">{subjectOf(rec)}</span>
        <span className="sub jp">{detailOf(rec) || '—'}</span>
      </span>
      <span className="amt num">{yen(item.amount) ?? ''}</span>
    </button>
  )
}

export default function QueueList({ items, selectedId, onSelect, loading }) {
  const selRef = useRef(null)

  useEffect(() => {
    selRef.current?.scrollIntoView({ block: 'nearest' })
  }, [selectedId])

  if (loading) {
    return (
      <div className="queue-list">
        {Array.from({ length: 9 }, (_, i) => (
          <div key={i} className="skel skel-row" />
        ))}
      </div>
    )
  }

  if (!items.length) {
    return (
      <div className="queue-list">
        <div className="empty">
          <strong>Queue clear</strong>
          Nothing pending on this process.
        </div>
      </div>
    )
  }

  const ready = items.filter((i) => !i.needs_review)
  const review = items.filter((i) => i.needs_review)

  return (
    <div className="queue-list" role="listbox" aria-label="Pending records">
      {ready.length > 0 && (
        <>
          <div className="group-label">Drafted — {ready.length}</div>
          {ready.map((i) => (
            <Row
              key={i.record.ID}
              item={i}
              selected={i.record.ID === selectedId}
              innerRef={i.record.ID === selectedId ? selRef : null}
              onSelect={() => onSelect(i.record.ID)}
            />
          ))}
        </>
      )}
      {review.length > 0 && (
        <>
          <div className="group-label">Needs a person — {review.length}</div>
          {review.map((i) => (
            <Row
              key={i.record.ID}
              item={i}
              selected={i.record.ID === selectedId}
              innerRef={i.record.ID === selectedId ? selRef : null}
              onSelect={() => onSelect(i.record.ID)}
            />
          ))}
        </>
      )}
    </div>
  )
}
