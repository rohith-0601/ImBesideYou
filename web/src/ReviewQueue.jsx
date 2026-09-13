import RecordCard from './RecordCard.jsx'

export default function ReviewQueue({ queue, onApprove }) {
  const ready = queue.items.filter((i) => !i.needs_review)
  const review = queue.items.filter((i) => i.needs_review)

  return (
    <section>
      <div className="summary">
        <strong className="jp">{queue.display_name}</strong>
        <span>{queue.total_pending} pending</span>
        <span className="ok">{queue.ready} ready to approve</span>
        <span className="warn">{queue.needs_review} need review</span>
        <span className="muted">
          {queue.states.pending} → {queue.states.done}
        </span>
      </div>

      {ready.length > 0 && (
        <>
          <h2>Ready — comment drafted, awaiting your approval</h2>
          <div className="cards">
            {ready.slice(0, 25).map((i) => (
              <RecordCard key={i.record.ID} item={i} onApprove={onApprove} />
            ))}
          </div>
          {ready.length > 25 && (
            <p className="muted">…and {ready.length - 25} more ready.</p>
          )}
        </>
      )}

      {review.length > 0 && (
        <>
          <h2>Needs review — the tool will not draft these</h2>
          <div className="cards">
            {review.slice(0, 10).map((i) => (
              <RecordCard key={i.record.ID} item={i} onApprove={onApprove} />
            ))}
          </div>
          {review.length > 10 && (
            <p className="muted">…and {review.length - 10} more to review.</p>
          )}
        </>
      )}
    </section>
  )
}
