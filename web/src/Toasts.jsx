export default function Toasts({ toasts }) {
  return (
    <div className="toasts" role="status" aria-live="polite">
      {toasts.map((t) => (
        <div key={t.key} className={t.error ? 'toast is-error' : 'toast'}>
          {t.id && <span className="tid mono">{t.id}</span>}
          <span className="jp">{t.msg}</span>
        </div>
      ))}
    </div>
  )
}
