const HIDDEN = new Set(['ID', 'ステータス'])

export default function RecordCard({ item, onApprove }) {
  const r = item.record
  const fields = Object.entries(r).filter(
    ([k, v]) => !HIDDEN.has(k) && !k.startsWith('_') && v,
  )

  return (
    <article className={item.needs_review ? 'card review' : 'card'}>
      <div className="card-head">
        <code>{r.ID}</code>
        {item.needs_review ? (
          <span className="badge warn">review</span>
        ) : (
          <span className="badge ok">ready</span>
        )}
      </div>

      <dl className="fields">
        {fields.map(([k, v]) => (
          <div key={k}>
            <dt className="jp">{k}</dt>
            <dd className="jp">{v}</dd>
          </div>
        ))}
      </dl>

      {item.comment ? (
        <p className="comment jp">{item.comment}</p>
      ) : (
        <p className="comment muted">No comment drafted.</p>
      )}

      {item.reasons.length > 0 && (
        <ul className="reasons">
          {item.reasons.map((x, i) => (
            <li key={i}>{x}</li>
          ))}
        </ul>
      )}

      <button
        className="approve"
        disabled={!item.comment}
        onClick={() => onApprove(item)}
      >
        {item.comment ? 'Approve with this comment' : 'Cannot submit'}
      </button>
    </article>
  )
}
